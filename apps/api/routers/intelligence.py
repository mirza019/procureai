from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from apps.api.dependencies import DbSession, current_user
from procureai.ai.guardrails import SYSTEM_GUARDRAIL, validate_evidence
from procureai.ai.tasks import AgentTask, available_tasks, run_agent_task
from procureai.config.settings import get_settings
from procureai.db.models import User
from procureai.reporting.executive import executive_pdf, supplier_excel
from procureai.services.analytics import (
    alerts,
    category_spend,
    cost_anomalies,
    dashboard_kpis,
    dashboard_period,
    delivery_summary,
    delivery_trend,
    invoice_summary,
    monthly_spend,
    pipeline_runs,
    quality_summary,
    risk_distribution,
    sourcing_rank,
    supplier_scorecards,
    top_suppliers_by_spend,
)
from procureai.services.projections import procurement_projections

router = APIRouter(prefix="/intelligence", tags=["procurement intelligence"])
Authenticated = Annotated[User, Depends(current_user)]


@router.get("/agent/tasks")
def agent_tasks(_: Authenticated):
    return available_tasks()


@router.post("/agent/tasks/{task}")
async def execute_agent_task(
    task: AgentTask,
    db: DbSession,
    _: Authenticated,
    supplier_code: str = "SUP-DE-014",
):
    try:
        return await run_agent_task(db, task, supplier_code)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard(db: DbSession, _: Authenticated):
    start, end = dashboard_period(db, 12)
    return {
        "period": {"start": start, "end": end},
        "kpis": dashboard_kpis(db, 12),
        "monthly_spend": monthly_spend(db, start, end),
        "risk_distribution": risk_distribution(db),
        "top_alerts": alerts(db)[:5],
    }


@router.get("/dashboard/procurement")
def procurement_dashboard(
    db: DbSession, _: Authenticated, months: int = 3, category: str = "All categories"
):
    start, end = dashboard_period(db, months or None)
    return {
        "period": {"start": start, "end": end},
        "filters": {"months": months, "category": category},
        "kpis": dashboard_kpis(db, months or None),
        "category_spend": category_spend(db, start, end, category),
        "delivery_trend": delivery_trend(db, start, end),
        "top_suppliers": top_suppliers_by_spend(db, start, end, category),
    }


@router.get("/suppliers")
def scorecards(db: DbSession, _: Authenticated):
    return supplier_scorecards(db)


@router.get("/cost-anomalies")
def anomalies(db: DbSession, _: Authenticated):
    return cost_anomalies(db)


@router.get("/operations")
def operations(db: DbSession, _: Authenticated):
    return {
        "delivery": delivery_summary(db),
        "quality": quality_summary(db),
        "invoices": invoice_summary(db),
    }


@router.get("/projections")
def projections(db: DbSession, _: Authenticated, horizon: int = 6):
    return procurement_projections(db, horizon)


@router.get("/alerts")
def current_alerts(db: DbSession, _: Authenticated):
    return alerts(db)


@router.get("/pipelines")
def runs(db: DbSession, _: Authenticated):
    return pipeline_runs(db)


@router.get("/sourcing/{material_code}")
def sourcing(
    material_code: str,
    db: DbSession,
    _: Authenticated,
    quantity: float = 100,
    maximum_risk: float = 80,
):
    rows = sourcing_rank(db, material_code, quantity, maximum_risk)
    if not rows:
        raise HTTPException(status_code=404, detail="Material or qualified suppliers not found")
    return rows


@router.get("/advisor/{supplier_code}")
def advisor(supplier_code: str, db: DbSession, _: Authenticated):
    evidence = next((row for row in supplier_scorecards(db) if row["code"] == supplier_code), None)
    if not evidence:
        raise HTTPException(status_code=404, detail="Supplier not found")
    validate_evidence(evidence)
    return {
        "facts": evidence,
        "model_predictions": {"risk_level": evidence["risk_level"]},
        "recommendations": [
            "Initiate a supplier performance review",
            "Validate delivery and quality root causes",
            "Review commercial pricing",
            "Assess qualified alternatives",
        ],
        "disclaimer": SYSTEM_GUARDRAIL,
        "provider_configured": bool(get_settings().gemini_api_key),
    }


@router.get("/reports/executive.pdf", response_class=FileResponse)
def pdf_report(db: DbSession, _: Authenticated):
    return FileResponse(
        executive_pdf(db), media_type="application/pdf", filename="executive_procurement_report.pdf"
    )


@router.get("/reports/suppliers.xlsx", response_class=FileResponse)
def excel_report(db: DbSession, _: Authenticated):
    return FileResponse(supplier_excel(db), filename="supplier_scorecards.xlsx")
