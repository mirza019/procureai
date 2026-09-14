from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from procureai.db.models import Role


class ReportType(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


class ReportStatus(StrEnum):
    DRAFT = "DRAFT"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class KpiEvidence(BaseModel):
    metric: str
    label: str
    current: float | int
    previous: float | int | None = None
    change: float | None = None
    unit: str
    target: float | None = None
    status: str
    calculation_service: str


class RankedFinding(BaseModel):
    finding_id: str
    category: str
    title: str
    description: str
    entity: str
    priority: str
    financial_impact: float
    score: float = Field(ge=0, le=100)
    evidence_metrics: list[str]


class ReportRecommendationData(BaseModel):
    action: str
    reason: str
    expected_benefit: str
    evidence_metrics: list[str]
    priority: str
    suggested_owner: str
    suggested_due: str
    confidence: str


class ReportNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executive_summary: str
    key_findings: list[str]
    positive_developments: list[str]
    risks: list[str]
    opportunities: list[str]
    recommendations: list[ReportRecommendationData]
    suggested_tasks: list[str]
    next_period_priorities: list[str]


class ReportRequest(BaseModel):
    report_type: ReportType
    audience_role: Role
    period_start: date
    period_end: date
    ai_analysis: bool = True
    sections: list[str] | None = None


class ReportResult(BaseModel):
    report_id: str
    report_type: ReportType
    audience_role: Role
    period_start: date
    period_end: date
    generated_at: datetime
    data_snapshot_at: datetime
    status: ReportStatus
    version: str
    template_version: str
    pdf_location: str | None
    excel_location: str | None
    snapshot: dict[str, Any]
    narrative: ReportNarrative
    warnings: list[str]


class TaskCreate(BaseModel):
    title: str
    description: str
    action_type: str
    priority: str
    source_type: str = "MANUAL"
    source_id: str | None = None
    financial_exposure: float = 0
    assigned_role: Role
    due_date: date | None = None
    ai_suggested: bool = False
    approval_status: str = "APPROVED"
    evidence_bundle: list[dict[str, Any]] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    status: TaskStatus
    assigned_to: str | None = None
    due_date: date | None = None


class TaskOutcome(BaseModel):
    description: str
    previous_unit_price: float | None = None
    new_unit_price: float | None = None
    annual_quantity: float | None = None


class ScheduleCreate(BaseModel):
    report_type: ReportType
    audience_role: Role
    cron_expression: str
    timezone: str = "Europe/Berlin"
    enabled: bool = True
