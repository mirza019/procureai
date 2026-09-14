from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from procureai.ai.agents import (
    ConversationAgent,
    CostValueAgent,
    ExecutiveProcurementAgent,
    RankingAgent,
    StrategicSourcingAgent,
    SupplierInvestigationAgent,
    SupplierRiskActionAgent,
)
from procureai.ai.base import LLMProvider
from procureai.ai.semantic import plan_question
from procureai.ai.tasks import provider_from_settings
from procureai.ai.tools import ToolContext, build_tool_registry
from procureai.db.models import AgentInteraction, Role
from procureai.schemas.agents import (
    AgentContext,
    AgentRequest,
    EntityReference,
    ProcurementAgentResponse,
    RoutingDecision,
)

SUPPLIER_PATTERN = re.compile(r"\bSUP-[A-Z]{2}-\d{3}\b", re.IGNORECASE)
MATERIAL_PATTERN = re.compile(r"\bMAT-\d{4,5}\b", re.IGNORECASE)


@dataclass
class SessionContextStore:
    """Bounded, process-local entity context; conversations are not persisted."""

    maximum_sessions: int = 100
    _contexts: dict[str, list[EntityReference]] = field(default_factory=dict)

    def get(self, session_id: str) -> list[EntityReference]:
        return list(self._contexts.get(session_id, []))

    def update(self, session_id: str, entities: list[EntityReference]) -> None:
        merged = {(e.type, e.id): e for e in [*self.get(session_id), *entities]}
        self._contexts[session_id] = list(merged.values())[-5:]
        while len(self._contexts) > self.maximum_sessions:
            self._contexts.pop(next(iter(self._contexts)))


SESSION_CONTEXT = SessionContextStore()


def route_question(
    question: str, context_entities: list[EntityReference] | None = None
) -> RoutingDecision:
    """Deterministic intent routing prevents the orchestrator from querying arbitrary data."""
    text = question.lower()
    normalized = re.sub(r"[^a-z0-9\s]", "", text).strip()
    entities: list[EntityReference] = []
    entities.extend(
        EntityReference(type="supplier", id=match.upper())
        for match in SUPPLIER_PATTERN.findall(question)
    )
    entities.extend(
        EntityReference(type="material", id=match.upper())
        for match in MATERIAL_PATTERN.findall(question)
    )
    semantic = plan_question(question, entities, list(context_entities or []))
    if semantic:
        return semantic
    if not entities:
        entities = list(context_entities or [])
    if normalized in {
        "hi",
        "hello",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "thanks",
        "thank you",
    }:
        return RoutingDecision(
            agents=["ConversationAgent"], intent="conversation", scope="GLOBAL", entities=[]
        )
    if any(word in text for word in ["source", "sourcing", "alternative", "which supplier should"]):
        return RoutingDecision(
            agents=["StrategicSourcingAgent"], intent="strategic_sourcing", entities=entities
        )
    if any(
        word in text
        for word in ["overpay", "saving", "price anomaly", "expensive", "cost opportunity"]
    ):
        if any(word in text for word in ["quality", "delivery", "risk"]):
            return RoutingDecision(
                agents=["SupplierRiskActionAgent", "CostValueAgent"],
                intent="multi_domain_risk_cost",
                entities=entities,
            )
        return RoutingDecision(agents=["CostValueAgent"], intent="cost_value", entities=entities)
    if any(word in text for word in ["why", "investigate", "what changed", "compare"]) and any(
        e.type == "supplier" for e in entities
    ):
        return RoutingDecision(
            agents=["SupplierInvestigationAgent"],
            intent="supplier_investigation",
            entities=entities,
        )
    if any(
        word in text
        for word in ["risk", "attention", "quality", "delivery", "single-source", "contract"]
    ):
        return RoutingDecision(
            agents=["SupplierRiskActionAgent"], intent="supplier_risk_action", entities=entities
        )
    if any(
        word in text
        for word in [
            "spend",
            "portfolio",
            "kpi",
            "management",
            "procurement",
            "overview",
            "performance",
        ]
    ):
        return RoutingDecision(
            agents=["ExecutiveProcurementAgent"], intent="executive_procurement", entities=entities
        )
    return RoutingDecision(
        agents=["ConversationAgent"], intent="conversation", scope="GLOBAL", entities=[]
    )


class AgentOrchestrator:
    def __init__(self, provider: LLMProvider | None = None):
        registry = build_tool_registry()
        provider = provider or provider_from_settings()
        self.agents = {
            agent.name: agent
            for agent in [
                SupplierRiskActionAgent(registry, provider),
                SupplierInvestigationAgent(registry, provider),
                CostValueAgent(registry, provider),
                ConversationAgent(registry, provider),
                StrategicSourcingAgent(registry, provider),
                ExecutiveProcurementAgent(registry, provider),
                RankingAgent(registry, provider),
            ]
        }

    async def execute(
        self, db: Session, request: AgentRequest, *, role: Role, user_id: UUID | None = None
    ) -> ProcurementAgentResponse:
        started = time.perf_counter()
        previous = SESSION_CONTEXT.get(request.session_id)
        routing = route_question(request.question, previous)
        supplier_code = request.supplier_code or next(
            (e.id for e in routing.entities if e.type == "supplier"), None
        )
        material_code = request.material_code or next(
            (e.id for e in routing.entities if e.type == "material"), None
        )
        context = ToolContext(db=db, role=role, user_id=str(user_id) if user_id else None)
        results = []
        try:
            for name in routing.agents:
                results.append(
                    await self.agents[name].execute(
                        request.question,
                        context,
                        supplier_code=supplier_code,
                        material_code=material_code,
                        quantity=request.quantity,
                        maximum_risk=request.maximum_risk,
                        query_plan=routing.query_plan,
                    )
                )
            response = results[0].response
            if len(results) > 1:
                response.agent = "ProcurementOrchestrator"
                response.verified_facts = [
                    fact for result in results for fact in result.response.verified_facts
                ]
                response.recommendations = [
                    action for result in results for action in result.response.recommendations
                ]
                response.tools_used = list(
                    dict.fromkeys(tool for result in results for tool in result.response.tools_used)
                )
                response.entities = list(
                    {
                        (entity.type, entity.id): entity
                        for result in results
                        for entity in result.response.entities
                    }.values()
                )
                response.answer = "Multi-domain investigation completed. Specialist assessments are grounded in the verified evidence below."
            SESSION_CONTEXT.update(request.session_id, response.entities)
            response.suggested_followups = self._suggestions(routing, response)
            self._audit(db, request, user_id, response, results, started, "SUCCESS")
            return response
        except (PermissionError, KeyError, ValueError) as exc:
            self._audit_failure(db, request, user_id, routing.agents[0], started, exc)
            raise

    @staticmethod
    def _suggestions(routing: RoutingDecision, response: ProcurementAgentResponse) -> list[str]:
        entity = next((item.id for item in response.entities if item.type == "supplier"), None)
        if routing.intent == "ranking" and routing.query_plan.get("metric") == "risk":
            return [
                f"Why is {entity} at this risk level?"
                if entity
                else "Why is the top supplier risky?",
                "Compare with the safest supplier",
                "What procurement actions should we prioritize?",
            ]
        if routing.intent == "cost_value":
            return [
                "Show the top 5 savings opportunities",
                "Which suppliers should we negotiate with?",
                "Explain the largest price anomaly",
            ]
        return [
            "Which suppliers require immediate attention?",
            "Where can we reduce sourcing risk?",
            "What actions are overdue?",
        ]

    @staticmethod
    def _audit(db, request, user_id, response, results, started, status):
        tool_ms = sum(result.tool_latency_ms for result in results)
        llm_ms = sum(result.llm_latency_ms for result in results)
        db.add(
            AgentInteraction(
                agent_request_id=response.agent_request_id,
                session_id=request.session_id,
                user_id=user_id,
                agent_name=response.agent,
                question=request.question,
                tools_called=response.tools_used,
                entity_ids=[e.id for e in response.entities],
                model_provider=response.model_provider,
                model_name=response.model_name,
                status=status,
                total_latency_ms=round((time.perf_counter() - started) * 1000),
                tool_latency_ms=tool_ms,
                llm_latency_ms=llm_ms,
            )
        )
        db.commit()

    @staticmethod
    def _audit_failure(db, request, user_id, agent, started, exc):
        db.add(
            AgentInteraction(
                session_id=request.session_id,
                user_id=user_id,
                agent_name=agent,
                question=request.question,
                tools_called=[],
                entity_ids=[],
                model_provider="configured",
                model_name="configured",
                status="FAILED",
                total_latency_ms=round((time.perf_counter() - started) * 1000),
                tool_latency_ms=0,
                llm_latency_ms=0,
                error_type=type(exc).__name__,
            )
        )
        db.commit()


def build_agent_context(
    request: AgentRequest, role: Role, user_id: UUID | None = None
) -> AgentContext:
    return AgentContext(
        session_id=request.session_id,
        role=role.value,
        user_id=user_id,
        recent_entities=SESSION_CONTEXT.get(request.session_id),
    )
