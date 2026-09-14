from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from procureai.db.models import (
    Alert,
    Category,
    Contract,
    Delivery,
    Invoice,
    Material,
    PipelineRun,
    ProcurementAction,
    ProcurementTask,
    PurchaseOrder,
    PurchaseOrderItem,
    QualityIncident,
    Supplier,
    SupplierRiskFactor,
)
from procureai.procurement.metrics import concentration


def executive_dashboard(db: Session) -> dict:
    total_spend = db.scalar(select(func.sum(PurchaseOrder.total_value))) or Decimal(0)
    supplier_spend = db.execute(
        select(Supplier.supplier_code, func.sum(PurchaseOrder.total_value))
        .join(PurchaseOrder)
        .group_by(Supplier.supplier_code)
    ).all()
    concentration_kpis = concentration({code: Decimal(value) for code, value in supplier_spend})
    delivery_total = db.scalar(select(func.count()).select_from(Delivery)) or 0
    on_time = (
        db.scalar(select(func.count()).select_from(Delivery).where(Delivery.days_late <= 0)) or 0
    )
    quality_cost = db.scalar(select(func.sum(QualityIncident.estimated_cost))) or Decimal(0)
    savings = db.scalar(
        select(
            func.sum(
                case(
                    (PurchaseOrderItem.price_variance > 0, PurchaseOrderItem.price_variance),
                    else_=0,
                )
            )
        )
    ) or Decimal(0)
    risk_exposure = db.scalar(
        select(func.sum(Alert.financial_exposure)).where(
            Alert.status == "OPEN", Alert.severity.in_(["HIGH", "CRITICAL"])
        )
    ) or Decimal(0)
    today = datetime.now(UTC).date()
    expiring = (
        db.scalar(
            select(func.count())
            .select_from(Contract)
            .where(Contract.end_date.between(today, today + timedelta(days=90)))
        )
        or 0
    )
    critical_suppliers = (
        db.scalar(
            select(func.count(func.distinct(Alert.supplier_id))).where(
                Alert.status == "OPEN", Alert.severity == "CRITICAL"
            )
        )
        or 0
    )
    return {
        "total_spend": float(total_spend),
        "savings_opportunity": float(savings),
        "risk_exposure": float(risk_exposure),
        "critical_suppliers": critical_suppliers,
        "on_time_delivery": on_time / delivery_total if delivery_total else 0,
        "quality_cost": float(quality_cost),
        "expiring_contracts": expiring,
        "top_supplier_share": float(concentration_kpis["top_supplier_share"]),
        "hhi": float(concentration_kpis["hhi"]),
    }


def dashboard_period(db: Session, months: int | None = 12) -> tuple[date | None, date | None]:
    """Return a data-anchored reporting window so demo data never appears stale/empty."""
    period_end = db.scalar(select(func.max(PurchaseOrder.order_date)))
    if not period_end:
        return None, None
    return (period_end - timedelta(days=31 * months), period_end) if months else (None, period_end)


def dashboard_kpis(db: Session, months: int | None = 12) -> dict:
    """Central deterministic KPI definitions used by both dashboard views."""
    start, end = dashboard_period(db, months)
    po_filter = [PurchaseOrder.order_date <= end] if end else []
    if start:
        po_filter.append(PurchaseOrder.order_date > start)
    spend = float(db.scalar(select(func.sum(PurchaseOrder.total_value)).where(*po_filter)) or 0)
    contracted = float(
        db.scalar(
            select(func.sum(PurchaseOrder.total_value)).where(
                *po_filter, PurchaseOrder.contract_id.is_not(None)
            )
        )
        or 0
    )
    supplier_ids = select(PurchaseOrder.supplier_id).where(*po_filter).distinct()
    countries = (
        db.scalar(
            select(func.count(func.distinct(Supplier.country))).where(
                Supplier.supplier_id.in_(supplier_ids)
            )
        )
        or 0
    )
    active_suppliers = db.scalar(select(func.count()).select_from(supplier_ids.subquery())) or 0
    single_source = (
        db.scalar(
            select(func.count())
            .select_from(Material)
            .where(Material.active.is_(True), Material.single_source_allowed.is_(True))
        )
        or 0
    )
    critical_single_source = (
        db.scalar(
            select(func.count())
            .select_from(Material)
            .where(
                Material.active.is_(True),
                Material.single_source_allowed.is_(True),
                Material.criticality.in_(["HIGH", "CRITICAL"]),
            )
        )
        or 0
    )
    open_actions = (
        db.scalar(
            select(func.count())
            .select_from(ProcurementAction)
            .where(ProcurementAction.status.in_(["OPEN", "ACKNOWLEDGED", "IN_PROGRESS"]))
        )
        or 0
    ) + (
        db.scalar(
            select(func.count())
            .select_from(ProcurementTask)
            .where(ProcurementTask.status.in_(["OPEN", "IN_PROGRESS"]))
        )
        or 0
    )
    priority_actions = (
        db.scalar(
            select(func.count())
            .select_from(ProcurementAction)
            .where(
                ProcurementAction.status.in_(["OPEN", "ACKNOWLEDGED", "IN_PROGRESS"]),
                ProcurementAction.priority.in_(["HIGH", "CRITICAL"]),
            )
        )
        or 0
    ) + (
        db.scalar(
            select(func.count())
            .select_from(ProcurementTask)
            .where(
                ProcurementTask.status.in_(["OPEN", "IN_PROGRESS"]),
                ProcurementTask.priority.in_(["HIGH", "CRITICAL"]),
            )
        )
        or 0
    )
    base = executive_dashboard(db)
    delivery = delivery_summary(db, start, end)
    quality = quality_summary(db, start, end)
    invoices = invoice_summary(db, start, end)
    return {
        **base,
        "total_spend": spend,
        "active_suppliers": active_suppliers,
        "supplier_countries": countries,
        "contract_coverage": contracted / spend if spend else 0,
        "single_source_materials": single_source,
        "critical_single_source_materials": critical_single_source,
        "open_actions": open_actions,
        "priority_actions": priority_actions,
        "on_time_delivery": delivery["otd"],
        "quality_cost": quality["cost"],
        "invoice_mismatches": invoices["mismatches"],
        "invoice_match_rate": invoices["match_rate"],
        "period_start": start.isoformat() if start else None,
        "period_end": end.isoformat() if end else None,
    }


def monthly_spend(db: Session, start: date | None = None, end: date | None = None) -> list[dict]:
    month = func.strftime("%Y-%m", PurchaseOrder.order_date)
    filters = []
    if start:
        filters.append(PurchaseOrder.order_date > start)
    if end:
        filters.append(PurchaseOrder.order_date <= end)
    return [
        {"month": m, "spend": float(v)}
        for m, v in db.execute(
            select(month, func.sum(PurchaseOrder.total_value))
            .where(*filters)
            .group_by(month)
            .order_by(month)
        ).all()
    ]


def category_spend(
    db: Session, start: date | None = None, end: date | None = None, category: str | None = None
) -> list[dict]:
    filters = []
    if start:
        filters.append(PurchaseOrder.order_date > start)
    if end:
        filters.append(PurchaseOrder.order_date <= end)
    if category and category != "All categories":
        filters.append(Category.category_name == category)
    rows = db.execute(
        select(
            Category.category_name,
            func.sum(PurchaseOrderItem.line_value),
            func.count(func.distinct(PurchaseOrder.po_id)),
        )
        .join(Material, Material.category_id == Category.category_id)
        .join(PurchaseOrderItem, PurchaseOrderItem.material_id == Material.material_id)
        .join(PurchaseOrder, PurchaseOrder.po_id == PurchaseOrderItem.po_id)
        .where(*filters)
        .group_by(Category.category_name)
        .order_by(desc(func.sum(PurchaseOrderItem.line_value)))
    ).all()
    return [
        {"category": name, "spend": float(value), "po_count": count} for name, value, count in rows
    ]


def risk_distribution(db: Session) -> list[dict]:
    rows = supplier_scorecards(db)
    result = []
    for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        matching = [row for row in rows if row["risk_level"] == level]
        result.append(
            {"level": level, "count": len(matching), "spend": sum(row["spend"] for row in matching)}
        )
    return result


def delivery_trend(db: Session, start: date | None = None, end: date | None = None) -> list[dict]:
    month = func.strftime("%Y-%m", Delivery.actual_delivery_date)
    filters = []
    if start:
        filters.append(Delivery.actual_delivery_date > start)
    if end:
        filters.append(Delivery.actual_delivery_date <= end)
    rows = db.execute(
        select(month, func.count(), func.sum(case((Delivery.days_late <= 0, 1), else_=0)))
        .where(*filters)
        .group_by(month)
        .order_by(month)
    ).all()
    return [
        {
            "month": m,
            "total": total,
            "on_time": on_time / total if total else 0,
            "late": (total - on_time) / total if total else 0,
        }
        for m, total, on_time in rows
    ]


def supplier_scorecards(db: Session, limit: int = 80) -> list[dict]:
    spend = dict(
        db.execute(
            select(PurchaseOrder.supplier_id, func.sum(PurchaseOrder.total_value)).group_by(
                PurchaseOrder.supplier_id
            )
        ).all()
    )
    delivery = dict(
        db.execute(
            select(
                Delivery.supplier_id, func.avg(case((Delivery.days_late <= 0, 1.0), else_=0.0))
            ).group_by(Delivery.supplier_id)
        ).all()
    )
    incidents = dict(
        db.execute(
            select(QualityIncident.supplier_id, func.count()).group_by(QualityIncident.supplier_id)
        ).all()
    )
    risk_sub = (
        select(
            SupplierRiskFactor.supplier_id, func.max(SupplierRiskFactor.risk_date).label("latest")
        )
        .group_by(SupplierRiskFactor.supplier_id)
        .subquery()
    )
    risks = dict(
        db.execute(
            select(SupplierRiskFactor.supplier_id, SupplierRiskFactor.overall_risk).join(
                risk_sub,
                (SupplierRiskFactor.supplier_id == risk_sub.c.supplier_id)
                & (SupplierRiskFactor.risk_date == risk_sub.c.latest),
            )
        ).all()
    )
    rows = []
    for supplier in db.scalars(select(Supplier).order_by(Supplier.supplier_code).limit(limit)):
        otd = float(delivery.get(supplier.supplier_id, 0))
        risk = float(risks.get(supplier.supplier_id, 0))
        incident_count = incidents.get(supplier.supplier_id, 0)
        quality = max(0, 100 - incident_count * 1.8)
        cost = max(0, 100 - abs(supplier.base_price_competitiveness - 1) * 120)
        score = (
            0.25 * quality
            + 0.25 * otd * 100
            + 0.20 * cost
            + 0.20 * (100 - risk)
            + 0.10 * (95 if supplier.preferred_supplier else 70)
        )
        rows.append(
            {
                "supplier_id": str(supplier.supplier_id),
                "code": supplier.supplier_code,
                "name": supplier.supplier_name,
                "country": supplier.country,
                "spend": float(spend.get(supplier.supplier_id, 0)),
                "otd": otd,
                "incidents": incident_count,
                "quality_score": round(quality, 1),
                "risk": round(risk, 1),
                "risk_level": "CRITICAL"
                if risk >= 80
                else "HIGH"
                if risk >= 60
                else "MEDIUM"
                if risk >= 30
                else "LOW",
                "score": round(score, 1),
            }
        )
    return sorted(rows, key=lambda row: row["spend"], reverse=True)


def top_suppliers_by_spend(
    db: Session,
    start: date | None = None,
    end: date | None = None,
    category: str | None = None,
    limit: int = 5,
) -> list[dict]:
    filters = []
    if start:
        filters.append(PurchaseOrder.order_date > start)
    if end:
        filters.append(PurchaseOrder.order_date <= end)
    statement = (
        select(PurchaseOrder.supplier_id, func.sum(PurchaseOrderItem.line_value))
        .join(PurchaseOrderItem, PurchaseOrderItem.po_id == PurchaseOrder.po_id)
        .join(Material, Material.material_id == PurchaseOrderItem.material_id)
        .join(Category, Category.category_id == Material.category_id)
        .where(*filters)
    )
    if category and category != "All categories":
        statement = statement.where(Category.category_name == category)
    spend = {
        str(supplier_id): value
        for supplier_id, value in db.execute(statement.group_by(PurchaseOrder.supplier_id)).all()
    }
    rows = supplier_scorecards(db)
    for row in rows:
        row["spend"] = float(spend.get(row["supplier_id"], 0))
    return sorted(
        (row for row in rows if row["spend"] > 0),
        key=lambda row: row["spend"],
        reverse=True,
    )[:limit]


def alerts(db: Session) -> list[dict]:
    rows = db.execute(
        select(Alert, Supplier.supplier_code)
        .outerjoin(Supplier)
        .where(Alert.status == "OPEN")
        .order_by(
            case((Alert.severity == "CRITICAL", 1), (Alert.severity == "HIGH", 2), else_=3),
            desc(Alert.financial_exposure),
        )
    ).all()
    return [
        {
            "id": str(alert.alert_id),
            "type": alert.alert_type,
            "severity": alert.severity,
            "supplier": code or "Portfolio",
            "exposure": float(alert.financial_exposure),
            "description": alert.description,
            "status": alert.status,
        }
        for alert, code in rows
    ]


def cost_anomalies(db: Session, limit: int = 30) -> list[dict]:
    rows = db.execute(
        select(
            Material.material_code,
            Material.material_name,
            Supplier.supplier_code,
            PurchaseOrderItem.unit_price,
            PurchaseOrderItem.expected_unit_price,
            PurchaseOrderItem.quantity,
            PurchaseOrderItem.price_variance,
        )
        .join(Material, PurchaseOrderItem.material_id == Material.material_id)
        .join(PurchaseOrder, PurchaseOrderItem.po_id == PurchaseOrder.po_id)
        .join(Supplier, PurchaseOrder.supplier_id == Supplier.supplier_id)
        .where(PurchaseOrderItem.price_variance > 5000)
        .order_by(desc(PurchaseOrderItem.price_variance))
        .limit(limit)
    ).all()
    return [
        {
            "material": code,
            "description": name,
            "supplier": supplier,
            "actual": float(actual),
            "expected": float(expected),
            "quantity": float(qty),
            "impact": float(impact),
            "confidence": "HIGH" if float(impact) > 50_000 else "MEDIUM",
        }
        for code, name, supplier, actual, expected, qty, impact in rows
    ]


def quality_summary(db: Session, start: date | None = None, end: date | None = None) -> dict:
    filters = []
    if start:
        filters.append(QualityIncident.incident_date > start)
    if end:
        filters.append(QualityIncident.incident_date <= end)
    severity_rows = db.execute(
        select(QualityIncident.severity, func.count(), func.sum(QualityIncident.estimated_cost))
        .where(*filters)
        .group_by(QualityIncident.severity)
    ).all()
    return {
        "incidents": sum(row[1] for row in severity_rows),
        "cost": sum(float(row[2] or 0) for row in severity_rows),
        "mean_close_days": float(
            db.scalar(select(func.avg(QualityIncident.days_to_close)).where(*filters)) or 0
        ),
        "by_severity": [
            {"severity": sev, "count": count, "cost": float(cost or 0)}
            for sev, count, cost in severity_rows
        ],
    }


def delivery_summary(db: Session, start: date | None = None, end: date | None = None) -> dict:
    filters = []
    if start:
        filters.append(Delivery.actual_delivery_date > start)
    if end:
        filters.append(Delivery.actual_delivery_date <= end)
    total = db.scalar(select(func.count()).select_from(Delivery).where(*filters)) or 0
    late = (
        db.scalar(
            select(func.count()).select_from(Delivery).where(*filters, Delivery.days_late > 0)
        )
        or 0
    )
    return {
        "total": total,
        "late": late,
        "otd": (total - late) / total if total else 0,
        "average_lateness": float(
            db.scalar(select(func.avg(Delivery.days_late)).where(*filters, Delivery.days_late > 0))
            or 0
        ),
    }


def invoice_summary(db: Session, start: date | None = None, end: date | None = None) -> dict:
    filters = []
    if start:
        filters.append(Invoice.invoice_date > start)
    if end:
        filters.append(Invoice.invoice_date <= end)
    total = db.scalar(select(func.count()).select_from(Invoice).where(*filters)) or 0
    mismatches = (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(*filters, Invoice.po_match_status == "MISMATCH")
        )
        or 0
    )
    duplicates = (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(*filters, Invoice.duplicate_flag.is_(True))
        )
        or 0
    )
    variance = db.scalar(select(func.sum(func.abs(Invoice.variance_amount))).where(*filters)) or 0
    return {
        "total": total,
        "mismatches": mismatches,
        "duplicates": duplicates,
        "match_rate": (total - mismatches) / total if total else 0,
        "variance": float(variance),
    }


def pipeline_runs(db: Session) -> list[dict]:
    return [
        {
            "run_id": str(r.run_id),
            "pipeline": r.pipeline_name,
            "status": r.status,
            "started": r.started_at.isoformat(),
            "records": r.records_inserted,
            "duration": round((r.finished_at - r.started_at).total_seconds(), 1)
            if r.finished_at
            else None,
        }
        for r in db.scalars(select(PipelineRun).order_by(desc(PipelineRun.started_at)).limit(10))
    ]


def sourcing_rank(
    db: Session, material_code: str, quantity: float, maximum_risk: float = 80
) -> list[dict]:
    material = db.scalar(select(Material).where(Material.material_code == material_code))
    if not material:
        return []
    candidates = [row for row in supplier_scorecards(db) if row["risk"] <= maximum_risk]
    ranked = []
    for row in candidates[:20]:
        supplier = db.scalar(select(Supplier).where(Supplier.supplier_code == row["code"]))
        unit = float(material.standard_cost) * supplier.base_price_competitiveness
        decision = (
            0.35 * (100 / supplier.base_price_competitiveness)
            + 0.25 * row["quality_score"]
            + 0.20 * row["otd"] * 100
            + 0.20 * (100 - row["risk"])
        )
        ranked.append(
            {
                **row,
                "unit_price": round(unit, 2),
                "total_cost": round(unit * quantity, 2),
                "decision_score": round(decision, 1),
            }
        )
    return sorted(ranked, key=lambda row: row["decision_score"], reverse=True)[:5]
