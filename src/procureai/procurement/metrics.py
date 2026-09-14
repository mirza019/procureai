from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal


def concentration(spend: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """Calculate transparent supplier concentration metrics from non-negative spend."""
    values = sorted((Decimal(v) for v in spend.values() if v > 0), reverse=True)
    total = sum(values, Decimal(0))
    if total == 0:
        return {
            "total": Decimal(0),
            "top_supplier_share": Decimal(0),
            "top_5_share": Decimal(0),
            "hhi": Decimal(0),
        }
    shares = [v / total for v in values]
    return {
        "total": total,
        "top_supplier_share": shares[0],
        "top_5_share": sum(shares[:5], Decimal(0)),
        "hhi": sum((s * s for s in shares), Decimal(0)) * 10_000,
    }


def purchase_price_variance(quantity: Decimal, actual: Decimal, expected: Decimal) -> Decimal:
    return (actual - expected) * quantity


def on_time_delivery(planned_actual_days: Iterable[tuple[int, int]]) -> Decimal:
    rows = list(planned_actual_days)
    return (
        Decimal(sum(actual <= planned for planned, actual in rows)) / Decimal(len(rows))
        if rows
        else Decimal(0)
    )


@dataclass(frozen=True)
class SupplierScoreInput:
    quality: float
    delivery: float
    cost: float
    risk: float
    commercial: float


DEFAULT_WEIGHTS = {
    "quality": 0.25,
    "delivery": 0.25,
    "cost": 0.20,
    "risk": 0.20,
    "commercial": 0.10,
}


def supplier_score(
    values: SupplierScoreInput, weights: Mapping[str, float] = DEFAULT_WEIGHTS
) -> float:
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("Supplier score weights must sum to 1")
    score = sum(getattr(values, name) * weight for name, weight in weights.items())
    return round(max(0.0, min(100.0, score)), 2)


def supplier_risk(
    factors: Mapping[str, float], weights: Mapping[str, float] | None = None
) -> dict[str, object]:
    """Return a bounded, explainable risk score and category."""
    selected = weights or {name: 1 / len(factors) for name in factors}
    if set(selected) != set(factors) or abs(sum(selected.values()) - 1) > 1e-9:
        raise ValueError("Risk factors and normalized weights must match")
    score = round(max(0.0, min(100.0, sum(factors[name] * selected[name] for name in factors))), 2)
    level = (
        "LOW" if score < 30 else "MEDIUM" if score < 60 else "HIGH" if score < 80 else "CRITICAL"
    )
    contributions = sorted(
        (
            {
                "factor": name,
                "value": value,
                "weighted_contribution": round(value * selected[name], 2),
            }
            for name, value in factors.items()
        ),
        key=lambda row: row["weighted_contribution"],
        reverse=True,
    )
    return {"score": score, "level": level, "factors": contributions}
