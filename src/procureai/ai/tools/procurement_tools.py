from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from procureai.db.models import (
    Contract,
    Delivery,
    PurchaseOrder,
    PurchaseOrderItem,
    QualityIncident,
    Supplier,
    SupplierRiskFactor,
)
from procureai.schemas.agents import EntityReference, EvidencePeriod, ToolEvidence
from procureai.services.analytics import (
    alerts,
    cost_anomalies,
    executive_dashboard,
    sourcing_rank,
    supplier_scorecards,
)

ALLOWED_RANK_METRICS = {"risk", "spend", "otd", "quality_score", "quality_cost"}


def rank_entities(
    db: Session,
    entity_type: str,
    metric: str,
    direction: str = "desc",
    filters: dict | None = None,
    period: tuple[date, date] | None = None,
    limit: int = 1,
) -> ToolEvidence:
    """Allow-listed read-only ranking; no SQL or schema names come from the LLM."""
    if entity_type != "supplier" or metric not in ALLOWED_RANK_METRICS:
        raise ValueError("Unsupported entity or ranking metric")
    if direction not in {"asc", "desc"} or not 1 <= limit <= 20:
        raise ValueError("Invalid ranking direction or limit")
    if filters:
        unknown = set(filters) - {"country", "risk_level", "minimum_spend", "maximum_otd"}
        if unknown:
            raise ValueError(f"Unsupported filters: {', '.join(sorted(unknown))}")
    rows = supplier_scorecards(db)
    quality_costs = dict(
        db.execute(
            select(QualityIncident.supplier_id, func.sum(QualityIncident.estimated_cost)).group_by(
                QualityIncident.supplier_id
            )
        ).all()
    )
    supplier_ids = {
        supplier.supplier_code: supplier.supplier_id for supplier in db.scalars(select(Supplier))
    }
    for row in rows:
        row["quality_cost"] = float(quality_costs.get(supplier_ids[row["code"]], 0) or 0)
    filters = filters or {}
    if filters.get("country"):
        rows = [row for row in rows if row["country"].lower() == str(filters["country"]).lower()]
    if filters.get("risk_level"):
        rows = [row for row in rows if row["risk_level"] == filters["risk_level"]]
    if filters.get("minimum_spend") is not None:
        rows = [row for row in rows if row["spend"] >= float(filters["minimum_spend"])]
    if filters.get("maximum_otd") is not None:
        rows = [row for row in rows if row["otd"] <= float(filters["maximum_otd"])]
    ranked = sorted(rows, key=lambda row: row[metric], reverse=direction == "desc")[:limit]
    return _evidence(
        "rank_entities",
        "portfolio",
        "SUPPLIER_RANKING",
        {
            "entity_type": entity_type,
            "metric": metric,
            "direction": direction,
            "filters": filters,
            "period": period,
            "rows": ranked,
        },
        metadata={metric: SEMANTIC_METRIC_DEFINITIONS[metric]},
    )


SEMANTIC_METRIC_DEFINITIONS = {
    "risk": "Current deterministic supplier overall risk score",
    "spend": "Approved purchase-order value",
    "otd": "Share of deliveries received on or before planned date",
    "quality_score": "Deterministic quality score derived from recorded incidents",
    "quality_cost": "Sum of recorded estimated quality-incident cost",
}


def _period(months: int = 6) -> EvidencePeriod:
    end = datetime.now(UTC).date()
    return EvidencePeriod(start=end - timedelta(days=months * 30), end=end)


def _evidence(
    tool: str,
    entity_type: str,
    entity_id: str,
    data: dict,
    *,
    months: int = 6,
    metadata: dict[str, str] | None = None,
) -> ToolEvidence:
    return ToolEvidence(
        tool=tool,
        entity=EntityReference(type=entity_type, id=entity_id),
        period=_period(months),
        data=data,
        calculated_at=datetime.now(UTC),
        metric_metadata=metadata or {},
    )


def get_executive_overview(db: Session) -> ToolEvidence:
    return _evidence(
        "get_executive_overview",
        "portfolio",
        "PROCUREAI",
        executive_dashboard(db),
        months=12,
        metadata={
            "spend": "Sum of approved PO total values",
            "otd": "Actual date on/before planned date",
        },
    )


def get_procurement_alerts(db: Session) -> ToolEvidence:
    return _evidence(
        "get_procurement_alerts",
        "portfolio",
        "PROCUREAI",
        {"alerts": alerts(db)},
        months=3,
        metadata={"financial_exposure": "Stored deterministic alert exposure"},
    )


def _supplier_or_raise(db: Session, supplier_code: str) -> Supplier:
    supplier = db.scalar(select(Supplier).where(Supplier.supplier_code == supplier_code))
    if not supplier:
        raise ValueError(f"Supplier not found: {supplier_code}")
    return supplier


def get_supplier_investigation(db: Session, supplier_code: str) -> ToolEvidence:
    supplier = _supplier_or_raise(db, supplier_code)
    end = datetime.now(UTC).date()
    split = end - timedelta(days=180)
    previous = split - timedelta(days=180)

    def otd(start: date, finish: date) -> float:
        total = (
            db.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(
                    Delivery.supplier_id == supplier.supplier_id,
                    Delivery.actual_delivery_date.between(start, finish),
                )
            )
            or 0
        )
        on_time = (
            db.scalar(
                select(func.count())
                .select_from(Delivery)
                .where(
                    Delivery.supplier_id == supplier.supplier_id,
                    Delivery.actual_delivery_date.between(start, finish),
                    Delivery.days_late <= 0,
                )
            )
            or 0
        )
        return on_time / total if total else 0

    def incident_stats(start: date, finish: date) -> tuple[int, float, float]:
        count, cost, severity = db.execute(
            select(
                func.count(),
                func.sum(QualityIncident.estimated_cost),
                func.sum(
                    case(
                        (QualityIncident.severity == "CRITICAL", 4),
                        (QualityIncident.severity == "HIGH", 3),
                        (QualityIncident.severity == "MEDIUM", 2),
                        else_=1,
                    )
                ),
            ).where(
                QualityIncident.supplier_id == supplier.supplier_id,
                QualityIncident.incident_date.between(start, finish),
            )
        ).one()
        return count or 0, float(cost or 0), float(severity or 0)

    current_incidents, current_quality_cost, current_severity = incident_stats(split, end)
    previous_incidents, previous_quality_cost, previous_severity = incident_stats(previous, split)
    current_price = (
        db.scalar(
            select(func.avg(PurchaseOrderItem.unit_price / PurchaseOrderItem.expected_unit_price))
            .join(PurchaseOrder)
            .where(
                PurchaseOrder.supplier_id == supplier.supplier_id,
                PurchaseOrder.order_date.between(split, end),
            )
        )
        or 1
    )
    previous_price = (
        db.scalar(
            select(func.avg(PurchaseOrderItem.unit_price / PurchaseOrderItem.expected_unit_price))
            .join(PurchaseOrder)
            .where(
                PurchaseOrder.supplier_id == supplier.supplier_id,
                PurchaseOrder.order_date.between(previous, split),
            )
        )
        or 1
    )
    risk_rows = db.execute(
        select(
            SupplierRiskFactor.risk_date,
            SupplierRiskFactor.overall_risk,
            SupplierRiskFactor.delivery_risk,
            SupplierRiskFactor.quality_risk,
            SupplierRiskFactor.dependency_risk,
        )
        .where(SupplierRiskFactor.supplier_id == supplier.supplier_id)
        .order_by(SupplierRiskFactor.risk_date.desc())
        .limit(7)
    ).all()
    contract = db.scalar(
        select(Contract)
        .where(Contract.supplier_id == supplier.supplier_id, Contract.status == "ACTIVE")
        .order_by(Contract.end_date)
        .limit(1)
    )
    scorecard = next(row for row in supplier_scorecards(db) if row["code"] == supplier_code)
    data = {
        "supplier": {
            "code": supplier.supplier_code,
            "name": supplier.supplier_name,
            "country": supplier.country,
            "strategic": supplier.strategic_supplier,
        },
        "scorecard": scorecard,
        "delivery": {"previous_otd": otd(previous, split), "current_otd": otd(split, end)},
        "quality": {
            "previous_incidents": previous_incidents,
            "current_incidents": current_incidents,
            "previous_severity_weighted": previous_severity,
            "current_severity_weighted": current_severity,
            "previous_cost": previous_quality_cost,
            "current_cost": current_quality_cost,
        },
        "price": {
            "previous_index": float(previous_price),
            "current_index": float(current_price),
            "change": float(current_price / previous_price - 1) if previous_price else 0,
        },
        "risk_history": [
            {
                "date": row[0].isoformat(),
                "overall": round(row[1], 1),
                "delivery": round(row[2], 1),
                "quality": round(row[3], 1),
                "dependency": round(row[4], 1),
            }
            for row in risk_rows
        ],
        "contract": {
            "number": contract.contract_number,
            "days_remaining": (contract.end_date - end).days,
        }
        if contract
        else None,
    }
    return _evidence(
        "get_supplier_investigation",
        "supplier",
        supplier_code,
        data,
        months=12,
        metadata={
            "price_index": "Average actual unit price divided by expected unit price",
            "severity_weighted": "LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4",
        },
    )


def compare_suppliers(db: Session, supplier_codes: list[str]) -> ToolEvidence:
    if not 2 <= len(supplier_codes) <= 5:
        raise ValueError("Compare between 2 and 5 suppliers")
    rows = {row["code"]: row for row in supplier_scorecards(db)}
    missing = [code for code in supplier_codes if code not in rows]
    if missing:
        raise ValueError(f"Suppliers not found: {', '.join(missing)}")
    return _evidence(
        "compare_suppliers",
        "portfolio",
        "SUPPLIER_COMPARISON",
        {"suppliers": [rows[code] for code in supplier_codes]},
        months=12,
    )


def get_cost_opportunities(db: Session, material_code: str | None = None) -> ToolEvidence:
    rows = cost_anomalies(db, limit=50)
    if material_code:
        rows = [row for row in rows if row["material"] == material_code]
    return _evidence(
        "get_cost_opportunities",
        "material" if material_code else "portfolio",
        material_code or "COST_PORTFOLIO",
        {
            "opportunities": rows,
            "total_potential_savings": round(sum(row["impact"] for row in rows), 2),
        },
        months=12,
        metadata={"impact": "quantity × max(actual price − expected price, 0)"},
    )


def rank_sourcing_candidates(
    db: Session, material_code: str, quantity: float, maximum_risk: float = 80
) -> ToolEvidence:
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    rows = sourcing_rank(db, material_code, quantity, maximum_risk)
    if not rows:
        raise ValueError("No qualified sourcing candidates found")
    return _evidence(
        "rank_sourcing_candidates",
        "material",
        material_code,
        {
            "quantity": quantity,
            "maximum_risk": maximum_risk,
            "ranking": rows,
            "decision_status": "Recommended for procurement evaluation; no supplier approval performed.",
        },
        months=12,
        metadata={"decision_score": "Price 35% + Quality 25% + Delivery 20% + inverse Risk 20%"},
    )
