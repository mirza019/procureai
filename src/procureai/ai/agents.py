from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass

import httpx

from procureai.ai.base import LLMProvider
from procureai.ai.prompts import system_prompt
from procureai.ai.tools import ToolContext, ToolRegistry
from procureai.procurement.action_engine import cost_actions, supplier_actions
from procureai.schemas.agents import (
    EntityReference,
    EvidenceItem,
    ProcurementAgentResponse,
    ToolEvidence,
)


def _facts(evidence: list[ToolEvidence]) -> list[EvidenceItem]:
    facts: list[EvidenceItem] = []
    for item in evidence:
        data = item.data
        if "scorecard" in data:
            score = data["scorecard"]
            facts.extend(
                [
                    EvidenceItem(
                        label="Supplier risk",
                        value=f"{score['risk']:.1f} / 100 ({score['risk_level']})",
                        source_tool=item.tool,
                        entity=item.entity,
                    ),
                    EvidenceItem(
                        label="On-time delivery",
                        value=f"{data['delivery']['previous_otd']:.1%} → {data['delivery']['current_otd']:.1%}",
                        source_tool=item.tool,
                        entity=item.entity,
                    ),
                    EvidenceItem(
                        label="Quality incidents",
                        value=f"{data['quality']['previous_incidents']} → {data['quality']['current_incidents']}",
                        source_tool=item.tool,
                        entity=item.entity,
                    ),
                    EvidenceItem(
                        label="Price index change",
                        value=f"{data['price']['change']:+.1%}",
                        source_tool=item.tool,
                        entity=item.entity,
                    ),
                ]
            )
        elif "opportunities" in data:
            facts.append(
                EvidenceItem(
                    label="Validated potential savings",
                    value=f"€{data['total_potential_savings']:,.0f}",
                    source_tool=item.tool,
                    entity=item.entity,
                )
            )
        elif "ranking" in data:
            top = data["ranking"][0]
            facts.append(
                EvidenceItem(
                    label="Top deterministic candidate",
                    value=f"{top['code']} · score {top['decision_score']:.1f} · €{top['total_cost']:,.0f}",
                    source_tool=item.tool,
                    entity=item.entity,
                )
            )
        elif "rows" in data and data.get("metric"):
            metric = data["metric"]
            for rank, row in enumerate(data["rows"], 1):
                value = row[metric]
                display = (
                    f"{value:.1%}"
                    if metric == "otd"
                    else f"€{value:,.0f}"
                    if metric in {"spend", "quality_cost"}
                    else f"{value:.1f}"
                )
                facts.append(
                    EvidenceItem(
                        label=f"#{rank} {row['code']} · {metric.replace('_', ' ').title()}",
                        value=f"{display} · {row['risk_level']}",
                        source_tool=item.tool,
                        entity=EntityReference(type="supplier", id=row["code"]),
                    )
                )
        elif "total_spend" in data:
            facts.extend(
                [
                    EvidenceItem(
                        label="Total spend",
                        value=f"€{data['total_spend']:,.0f}",
                        source_tool=item.tool,
                        entity=item.entity,
                    ),
                    EvidenceItem(
                        label="On-time delivery",
                        value=f"{data['on_time_delivery']:.1%}",
                        source_tool=item.tool,
                        entity=item.entity,
                    ),
                ]
            )
        elif "alerts" in data:
            facts.append(
                EvidenceItem(
                    label="Open procurement alerts",
                    value=str(len(data["alerts"])),
                    source_tool=item.tool,
                    entity=item.entity,
                )
            )
    return facts


def _unsupported_money(narrative: str, evidence: list[ToolEvidence]) -> list[str]:
    source = json.dumps([item.model_dump(mode="json") for item in evidence], default=str)
    warnings = []
    for token in re.findall(r"[€$£]\s?([\d,.]+)", narrative):
        normalized = token.replace(",", "")
        if token not in source and normalized not in source:
            warnings.append(f"Unsupported monetary value detected in AI narrative: {token}")
    return warnings


def _fallback_narrative(question: str, evidence: list[ToolEvidence]) -> str:
    """Produce a useful grounded answer when the optional LLM is unavailable."""
    text = question.lower()
    if not evidence:
        if any(
            greeting in text
            for greeting in ("hi", "hello", "hey", "good morning", "good afternoon", "good evening")
        ):
            return "Hello! I’m Ask Taulack, your procurement intelligence assistant. Ask me about supplier risk, spend, delivery, quality, contracts, savings, sourcing, alerts, or procurement actions."
        if "thank" in text:
            return "You’re welcome. What would you like to investigate next in ProcureAI?"
        return "I don't have verified ProcureAI data to answer that question yet."
    data = evidence[0].data
    if data.get("rows"):
        rows = data["rows"]
        metric = data["metric"]
        direction = data["direction"]
        label = {
            "risk": "risk score",
            "spend": "approved PO spend",
            "otd": "on-time delivery",
            "quality_score": "quality score",
            "quality_cost": "quality cost",
        }[metric]
        rendered = []
        for row in rows:
            value = row[metric]
            display = (
                f"{value:.1%}"
                if metric == "otd"
                else f"€{value:,.0f}"
                if metric in {"spend", "quality_cost"}
                else f"{value:.1f} / 100"
            )
            rendered.append(f"**{row['code']}** — {label}: **{display}** · {row['risk_level']}")
        lead = "lowest" if direction == "asc" else "highest"
        if len(rows) == 1:
            row = rows[0]
            value = row[metric]
            display = (
                f"{value:.1%}"
                if metric == "otd"
                else f"€{value:,.0f}"
                if metric in {"spend", "quality_cost"}
                else f"{value:.1f} / 100"
            )
            return (
                f"**{row['code']}** has the {lead} {label} in the current eligible supplier "
                f"portfolio: **{display}** ({row['risk_level']})."
            )
        action = (
            "Prioritize continuity review, dependency reduction, and corrective actions for the highest-risk suppliers."
            if metric == "risk" and direction == "desc"
            else "Use this ranking as the verified starting point for procurement review."
        )
        return (
            f"**Supplier ranking by {label} — {lead} first**\n\n"
            + "\n\n".join(rendered)
            + f"\n\n**Procurement implication:** {action}"
        )
    if data.get("ranking"):
        top = data["ranking"][0]
        return (
            f"The strongest evaluated sourcing candidate is **{top['code']}**, with a deterministic decision score of **{top['decision_score']:.1f}** "
            f"and evaluated total cost of **€{top['total_cost']:,.0f}**. This is a recommendation for procurement evaluation—not supplier approval."
        )
    if data.get("opportunities") is not None:
        return f"ProcureAI identified **€{data['total_potential_savings']:,.0f}** in validated price-variance opportunities. Review the largest lines first for negotiation, benchmark validation, or alternate sourcing."
    if data.get("scorecard"):
        row = data["scorecard"]
        if any(term in text for term in ("why", "changed", "investigate", "problem")):
            delivery = data.get("delivery", {})
            quality = data.get("quality", {})
            price = data.get("price", {})
            return (
                f"**Why {row['code']} requires investigation**\n\n"
                f"Risk is **{row['risk']:.1f} / 100 ({row['risk_level']})**. OTD moved from "
                f"**{delivery.get('previous_otd', 0):.1%}** to **{delivery.get('current_otd', 0):.1%}**, "
                f"quality incidents moved from **{quality.get('previous_incidents', 0)}** to "
                f"**{quality.get('current_incidents', 0)}**, and the purchase-price index changed "
                f"**{price.get('change', 0):+.1%}**.\n\n"
                "**Next action:** validate delivery constraints, review incident root causes, and assess dependency before corrective or alternate-sourcing decisions."
            )
        return f"**{row['code']}** currently has a risk score of **{row['risk']:.1f} / 100 ({row['risk_level']})**, on-time delivery of **{row['otd']:.1%}**, and a quality score of **{row['quality_score']:.1f} / 100**. The supporting delivery, quality, price, dependency, and contract evidence should guide the investigation."
    if data.get("total_spend") is not None:
        if any(term in text for term in ("focus", "priority", "attention", "management")):
            return (
                "**Management priorities**\n\n"
                f"1. Address high-risk exposure of **€{data['risk_exposure']:,.0f}**.\n\n"
                f"2. Progress savings opportunities worth **€{data['savings_opportunity']:,.0f}**.\n\n"
                f"3. Improve on-time delivery from **{data['on_time_delivery']:.1%}**.\n\n"
                f"4. Reduce quality cost of **€{data['quality_cost']:,.0f}**."
            )
        return f"Current portfolio spend is **€{data['total_spend']:,.0f}**, on-time delivery is **{data['on_time_delivery']:.1%}**, and deterministic savings opportunity is **€{data['savings_opportunity']:,.0f}**. Focus first on open critical exposure and the largest validated savings opportunities."
    return "I found verified procurement evidence for this question. Review the evidence metrics below to support the next procurement decision."


@dataclass
class SpecialistResult:
    response: ProcurementAgentResponse
    tool_latency_ms: int
    llm_latency_ms: int


class ProcurementSpecialist:
    name = "ProcurementSpecialist"

    def __init__(self, registry: ToolRegistry, provider: LLMProvider):
        self.registry = registry
        self.provider = provider

    async def execute(
        self,
        question: str,
        context: ToolContext,
        *,
        supplier_code: str | None = None,
        material_code: str | None = None,
        quantity: float | None = None,
        maximum_risk: float = 80,
        query_plan: dict | None = None,
    ) -> SpecialistResult:
        started = time.perf_counter()
        evidence = self.collect(
            context,
            supplier_code=supplier_code,
            material_code=material_code,
            quantity=quantity,
            maximum_risk=maximum_risk,
            query_plan=query_plan,
        )
        tool_ms = round((time.perf_counter() - started) * 1000)
        recommendations = self.actions(evidence)
        if not evidence:
            narrative = _fallback_narrative(question, evidence)
            return SpecialistResult(
                ProcurementAgentResponse(
                    agent_request_id=uuid.uuid4(),
                    agent=self.name,
                    model_provider="deterministic",
                    model_name="procureai-conversation",
                    answer=narrative,
                    interpretation=narrative,
                    confidence="HIGH",
                    ai_available=True,
                ),
                tool_ms,
                0,
            )
        prompt = (
            f"{system_prompt(self.name)}\n\nUSER QUESTION:\n{question}\n\n"
            "Adapt the format to the question: one or two sentences for a single fact; a compact ranked list for top/bottom requests; "
            "a side-by-side structure for comparisons; and evidence, business implication, and next actions for analytical questions. "
            "Answer directly, never repeat a fixed template, and do not introduce any number absent from evidence."
        )
        llm_started = time.perf_counter()
        ai_available = True
        warnings: list[str] = []
        provider_name = type(self.provider).__name__.replace("Provider", "").lower()
        model_name = "unavailable"
        try:
            llm = await self.provider.generate(
                prompt, {"tool_outputs": [item.model_dump(mode="json") for item in evidence]}
            )
            narrative = llm.text
            provider_name = llm.provider
            model_name = llm.model
            warnings = _unsupported_money(narrative, evidence)
            if warnings:
                narrative = _fallback_narrative(question, evidence)
                ai_available = False
        except (RuntimeError, httpx.HTTPError, KeyError, ValueError):
            narrative = _fallback_narrative(question, evidence)
            ai_available = False
            warnings.append("LLM provider unavailable; grounded deterministic response generated.")
        llm_ms = round((time.perf_counter() - llm_started) * 1000)
        priority = max(
            (r.priority for r in recommendations),
            key=["LOW", "MEDIUM", "HIGH", "CRITICAL"].index,
            default=None,
        )
        response = ProcurementAgentResponse(
            agent_request_id=uuid.uuid4(),
            agent=self.name,
            model_provider=provider_name,
            model_name=model_name,
            answer=narrative,
            priority=priority,
            verified_facts=_facts(evidence),
            interpretation=narrative,
            recommendations=recommendations,
            tools_used=[item.tool for item in evidence],
            entities=list({(e.entity.type, e.entity.id): e.entity for e in evidence}.values()),
            confidence="HIGH" if evidence else "LOW",
            warnings=warnings,
            ai_available=ai_available,
        )
        return SpecialistResult(response, tool_ms, llm_ms)

    def collect(self, context: ToolContext, **kwargs) -> list[ToolEvidence]:
        raise NotImplementedError

    def actions(self, evidence: list[ToolEvidence]):
        return []


class SupplierRiskActionAgent(ProcurementSpecialist):
    name = "SupplierRiskActionAgent"

    def collect(self, context, **kwargs):
        return [
            self.registry.execute(
                "get_supplier_investigation",
                context,
                supplier_code=kwargs.get("supplier_code") or "SUP-DE-014",
            ),
            self.registry.execute("get_procurement_alerts", context),
        ]

    def actions(self, evidence):
        return supplier_actions(evidence[0])


class SupplierInvestigationAgent(SupplierRiskActionAgent):
    name = "SupplierInvestigationAgent"


class CostValueAgent(ProcurementSpecialist):
    name = "CostValueAgent"

    def collect(self, context, **kwargs):
        return [
            self.registry.execute(
                "get_cost_opportunities", context, material_code=kwargs.get("material_code")
            )
        ]

    def actions(self, evidence):
        return cost_actions(evidence[0])


class StrategicSourcingAgent(ProcurementSpecialist):
    name = "StrategicSourcingAgent"

    def collect(self, context, **kwargs):
        return [
            self.registry.execute(
                "rank_sourcing_candidates",
                context,
                material_code=kwargs.get("material_code") or "MAT-0078",
                quantity=kwargs.get("quantity") or 1000,
                maximum_risk=kwargs.get("maximum_risk", 80),
            )
        ]


class ExecutiveProcurementAgent(ProcurementSpecialist):
    name = "ExecutiveProcurementAgent"

    def collect(self, context, **kwargs):
        return [
            self.registry.execute("get_executive_overview", context),
            self.registry.execute("get_procurement_alerts", context),
        ]


class RankingAgent(ProcurementSpecialist):
    name = "RankingAgent"

    def collect(self, context, **kwargs):
        plan = kwargs.get("query_plan") or {}
        return [self.registry.execute("rank_entities", context, **plan)]


class ConversationAgent(ProcurementSpecialist):
    name = "ConversationAgent"

    def collect(self, context, **kwargs):
        return []
