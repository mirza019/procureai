from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from apps.api.dependencies import DbSession, current_user, require_roles
from procureai.db.models import (
    ProcurementTask,
    Report,
    ReportRecommendation,
    ReportSchedule,
    Role,
    User,
)
from procureai.reporting.intelligent import generate_report, role_sections
from procureai.schemas.reporting import (
    ReportRequest,
    ScheduleCreate,
    TaskCreate,
    TaskOutcome,
    TaskUpdate,
)

router = APIRouter(prefix="/reports", tags=["reports"])
Authenticated = Annotated[User, Depends(current_user)]


def _allowed_audiences(user: User) -> set[Role]:
    if user.role == Role.ADMIN:
        return set(Role)
    if user.role == Role.PROCUREMENT_MANAGER:
        return {Role.PROCUREMENT_ANALYST, Role.PROCUREMENT_MANAGER, Role.EXECUTIVE}
    return {user.role}


@router.post("/generate")
async def create_report(payload: ReportRequest, db: DbSession, user: Authenticated):
    if payload.audience_role not in _allowed_audiences(user):
        raise HTTPException(status_code=403, detail="Unauthorized report audience")
    return await generate_report(db, payload, generated_by=user.id)


@router.get("")
def list_reports(db: DbSession, user: Authenticated):
    allowed = [role.value for role in _allowed_audiences(user)]
    reports = db.scalars(
        select(Report).where(Report.audience_role.in_(allowed)).order_by(Report.generated_at.desc())
    )
    return [
        {
            "report_id": item.report_id,
            "type": item.report_type,
            "audience": item.audience_role,
            "period": f"{item.period_start}/{item.period_end}",
            "generated_at": item.generated_at,
            "version": item.version,
            "status": item.status,
        }
        for item in reports
    ]


@router.get("/{report_id}")
def report_detail(report_id: str, db: DbSession, user: Authenticated):
    report = db.get(Report, report_id)
    if not report or Role(report.audience_role) not in _allowed_audiences(user):
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/{report_id}/download/{format_name}")
def download_report(report_id: str, format_name: str, db: DbSession, user: Authenticated):
    report = db.get(Report, report_id)
    if not report or Role(report.audience_role) not in _allowed_audiences(user):
        raise HTTPException(status_code=404, detail="Report not found")
    location = report.pdf_location if format_name == "pdf" else report.excel_location
    if format_name not in {"pdf", "excel"} or not location or not Path(location).exists():
        raise HTTPException(status_code=404, detail="Report artifact not found")
    return FileResponse(location, filename=Path(location).name)


@router.post("/{report_id}/archive")
def archive_report(
    report_id: str,
    db: DbSession,
    _: Annotated[User, Depends(require_roles(Role.ADMIN, Role.PROCUREMENT_MANAGER))],
):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = "ARCHIVED"
    db.commit()
    return {"report_id": report_id, "status": report.status}


@router.post("/tasks")
def create_task(payload: TaskCreate, db: DbSession, user: Authenticated):
    task = ProcurementTask(
        **payload.model_dump(exclude={"assigned_role"}),
        assigned_role=payload.assigned_role.value,
        created_by=user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/recommendations/{recommendation_id}/{decision}")
def decide_recommendation(
    recommendation_id: uuid.UUID,
    decision: str,
    db: DbSession,
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.PROCUREMENT_MANAGER))],
):
    recommendation = db.get(ReportRecommendation, recommendation_id)
    if not recommendation or decision not in {"accept", "dismiss"}:
        raise HTTPException(status_code=404, detail="Recommendation or decision not found")
    recommendation.disposition = decision.upper()
    if decision == "accept":
        db.add(
            ProcurementTask(
                title=recommendation.action,
                description=recommendation.reason,
                action_type="REPORT_RECOMMENDATION",
                priority=recommendation.priority,
                source_type="AI_ASSISTED_RECOMMENDATION",
                source_id=str(recommendation.recommendation_id),
                financial_exposure=0,
                assigned_role=recommendation.suggested_owner.upper().replace(" ", "_"),
                status="OPEN",
                created_by=user.id,
                ai_suggested=True,
                approval_status="APPROVED",
                evidence_bundle=[{"evidence_ids": recommendation.evidence_ids}],
            )
        )
    db.commit()
    return {"recommendation_id": str(recommendation_id), "decision": decision.upper()}


@router.patch("/tasks/{task_id}")
def update_task(task_id: uuid.UUID, payload: TaskUpdate, db: DbSession, user: Authenticated):
    task = db.get(ProcurementTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = payload.status.value
    task.due_date = payload.due_date or task.due_date
    if payload.assigned_to:
        task.assigned_to = uuid.UUID(payload.assigned_to)
    if payload.status.value == "COMPLETED":
        from datetime import UTC, datetime

        task.completed_at = datetime.now(UTC)
    db.commit()
    return task


@router.post("/tasks/{task_id}/outcome")
def record_task_outcome(
    task_id: uuid.UUID, payload: TaskOutcome, db: DbSession, user: Authenticated
):
    task = db.get(ProcurementTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    saving = None
    if (
        payload.previous_unit_price is not None
        and payload.new_unit_price is not None
        and payload.annual_quantity is not None
    ):
        saving = (
            max(payload.previous_unit_price - payload.new_unit_price, 0) * payload.annual_quantity
        )
    task.outcome = {**payload.model_dump(), "estimated_annualized_saving": saving}
    db.commit()
    return {"task_id": str(task_id), "outcome": task.outcome}


@router.post("/schedules")
def create_schedule(
    payload: ScheduleCreate,
    db: DbSession,
    user: Annotated[User, Depends(require_roles(Role.ADMIN, Role.PROCUREMENT_MANAGER))],
):
    schedule = ReportSchedule(
        **payload.model_dump(exclude={"report_type", "audience_role"}),
        report_type=payload.report_type.value,
        audience_role=payload.audience_role.value,
        created_by=user.id,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.get("/templates/{role}")
def template(role: Role, _: Authenticated):
    return {"role": role.value, "sections": role_sections(role)}
