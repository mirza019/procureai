from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

Priority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class EntityReference(BaseModel):
    type: Literal["supplier", "material", "category", "contract", "portfolio"]
    id: str


class EvidencePeriod(BaseModel):
    start: date
    end: date


class ToolEvidence(BaseModel):
    tool: str
    entity: EntityReference
    period: EvidencePeriod
    data: dict[str, Any]
    calculated_at: datetime
    source: str = "ProcureAI deterministic analytics engine"
    metric_metadata: dict[str, str] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    label: str
    value: str
    source_tool: str
    entity: EntityReference | None = None


class PredictionItem(BaseModel):
    label: str
    value: str
    model_name: str
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None


class Recommendation(BaseModel):
    action_type: str
    title: str
    reason: str
    priority: Priority
    suggested_owner: str
    financial_exposure: float = Field(default=0, ge=0)
    supplier_code: str | None = None
    material_code: str | None = None


class ProcurementAgentResponse(BaseModel):
    agent_request_id: UUID
    agent: str
    model_provider: str
    model_name: str
    answer: str
    priority: Priority | None = None
    verified_facts: list[EvidenceItem] = Field(default_factory=list)
    predictions: list[PredictionItem] = Field(default_factory=list)
    interpretation: str = ""
    recommendations: list[Recommendation] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    entities: list[EntityReference] = Field(default_factory=list)
    confidence: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    warnings: list[str] = Field(default_factory=list)
    ai_available: bool = True
    suggested_followups: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("answer", "interpretation")
    @classmethod
    def no_approval_language(cls, value: str) -> str:
        forbidden = ["approve supplier", "supplier is approved", "place the purchase order"]
        if any(phrase in value.lower() for phrase in forbidden):
            raise ValueError("Agent output contains unauthorized purchasing language")
        return value


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    supplier_code: str | None = Field(default=None, pattern=r"^SUP-[A-Z]{2}-\d{3}$")
    material_code: str | None = Field(default=None, pattern=r"^MAT-\d{4,5}$")
    quantity: float | None = Field(default=None, gt=0)
    maximum_risk: float = Field(default=80, ge=0, le=100)


class RoutingDecision(BaseModel):
    agents: list[str]
    intent: str
    scope: Literal[
        "GLOBAL", "ENTITY", "COMPARISON", "FILTERED", "TIME_PERIOD", "CONVERSATIONAL_FOLLOWUP"
    ] = "GLOBAL"
    entities: list[EntityReference] = Field(default_factory=list)
    query_plan: dict[str, Any] = Field(default_factory=dict)


class AgentContext(BaseModel):
    session_id: str
    user_id: UUID | None = None
    role: str
    recent_entities: list[EntityReference] = Field(default_factory=list)
