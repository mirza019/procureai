from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sklearn.linear_model import LinearRegression
from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.db.models import Supplier, SupplierRiskFactor
from procureai.services.analytics import cost_anomalies, delivery_trend, monthly_spend


def _next_month(label: str, offset: int) -> str:
    year, month = (int(part) for part in label.split("-"))
    index = year * 12 + month - 1 + offset
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _linear_projection(
    values: list[float], horizon: int, *, floor: float = 0, ceiling: float | None = None
) -> tuple[list[float], float]:
    if len(values) < 3:
        return [], 0
    x = np.arange(len(values)).reshape(-1, 1)
    model = LinearRegression().fit(x, values)
    predicted = model.predict(np.arange(len(values), len(values) + horizon).reshape(-1, 1))
    result = [
        max(floor, min(float(value), ceiling)) if ceiling is not None else max(floor, float(value))
        for value in predicted
    ]
    return result, max(0.0, min(1.0, float(model.score(x, values))))


def procurement_projections(db: Session, horizon: int = 6) -> dict:
    """Bounded decision-support projections derived from existing ProcureAI observations."""
    if not 1 <= horizon <= 12:
        raise ValueError("Projection horizon must be between 1 and 12 months")
    spend_history = monthly_spend(db)[-18:]
    spend_values = [row["spend"] for row in spend_history]
    spend_forecast, spend_fit = _linear_projection(spend_values, horizon)
    last_month = (
        spend_history[-1]["month"] if spend_history else datetime.now(UTC).strftime("%Y-%m")
    )
    spend_projection = [
        {"month": _next_month(last_month, index), "spend": round(value, 2), "kind": "forecast"}
        for index, value in enumerate(spend_forecast, 1)
    ]

    delivery_history = delivery_trend(db)[-18:]
    otd_values = [row["on_time"] * 100 for row in delivery_history]
    otd_forecast, delivery_fit = _linear_projection(otd_values, horizon, ceiling=100)
    delivery_last = delivery_history[-1]["month"] if delivery_history else last_month
    delivery_projection = [
        {"month": _next_month(delivery_last, index), "otd": round(value, 2), "kind": "forecast"}
        for index, value in enumerate(otd_forecast, 1)
    ]

    suppliers = {row.supplier_id: row.supplier_code for row in db.scalars(select(Supplier))}
    risk_outlook = []
    for supplier_id, code in suppliers.items():
        history = list(
            db.scalars(
                select(SupplierRiskFactor)
                .where(SupplierRiskFactor.supplier_id == supplier_id)
                .order_by(SupplierRiskFactor.risk_date.desc())
                .limit(6)
            )
        )[::-1]
        values = [row.overall_risk for row in history]
        predicted, fit = _linear_projection(values, 1, ceiling=100)
        if predicted:
            current = float(values[-1])
            risk_outlook.append(
                {
                    "supplier": code,
                    "current": round(current, 1),
                    "projected": round(predicted[0], 1),
                    "change": round(predicted[0] - current, 1),
                    "confidence": round(fit, 2),
                }
            )
    risk_outlook.sort(key=lambda row: (row["projected"], row["change"]), reverse=True)

    anomalies = cost_anomalies(db, limit=5)
    alerts = []
    if risk_outlook:
        riskiest = risk_outlook[0]
        alerts.append(
            {
                "priority": "HIGH" if riskiest["projected"] >= 60 else "MEDIUM",
                "title": f"{riskiest['supplier']} has the highest projected supplier risk",
                "evidence": f"{riskiest['current']:.1f} → {riskiest['projected']:.1f} projected risk score",
                "model": "supplier-risk-linear-trend-v1",
            }
        )
    if otd_forecast:
        alerts.append(
            {
                "priority": "HIGH" if otd_forecast[-1] < 85 else "MEDIUM",
                "title": "Portfolio delivery outlook",
                "evidence": f"Projected OTD reaches {otd_forecast[-1]:.1f}% in {horizon} months",
                "model": "delivery-trend-linear-v1",
            }
        )
    if anomalies:
        alerts.append(
            {
                "priority": "HIGH",
                "title": f"Price anomaly attention: {anomalies[0]['material']}",
                "evidence": f"Detected impact €{anomalies[0]['impact']:,.0f} with {anomalies[0]['confidence'].lower()} evidence confidence",
                "model": "purchase-price-anomaly-v1",
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "horizon_months": horizon,
        "spend_history": spend_history,
        "spend_projection": spend_projection,
        "delivery_history": delivery_history,
        "delivery_projection": delivery_projection,
        "supplier_risk_outlook": risk_outlook[:8],
        "price_anomalies": anomalies,
        "priority_predictions": alerts,
        "model_quality": {"spend_fit": round(spend_fit, 2), "delivery_fit": round(delivery_fit, 2)},
        "models": [
            "spend-linear-trend-v1",
            "delivery-trend-linear-v1",
            "supplier-risk-linear-trend-v1",
            "purchase-price-anomaly-v1",
        ],
        "disclaimer": "Projections are decision-support estimates based on synthetic historical data; they are not guaranteed outcomes.",
    }
