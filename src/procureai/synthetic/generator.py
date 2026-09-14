import random
from dataclasses import asdict, dataclass

CATEGORIES = [
    "Electrical Components",
    "Mechanical Components",
    "Steel & Metals",
    "Copper & Conductors",
    "Electronics",
    "Industrial Services",
    "Logistics",
    "Software & IT",
    "Engineering Services",
    "Safety Equipment",
]
COUNTRIES = [
    ("DE", "Europe"),
    ("PL", "Europe"),
    ("US", "Americas"),
    ("MX", "Americas"),
    ("IN", "Asia"),
    ("JP", "Asia"),
]


@dataclass(frozen=True)
class SyntheticSupplier:
    supplier_code: str
    supplier_name: str
    country: str
    region: str
    category: str
    base_price_competitiveness: float
    base_quality: float
    base_delivery_reliability: float
    capacity: float
    financial_stability: float
    country_risk: float
    risk_level: float


def generate_suppliers(count: int = 80, seed: int = 42) -> list[dict[str, object]]:
    """Generate reproducible correlated supplier profiles without confidential source data."""
    rng = random.Random(seed)
    rows = []
    for number in range(1, count + 1):
        country, region = rng.choice(COUNTRIES)
        financial = rng.betavariate(7, 2) * 100
        country_risk = rng.uniform(5, 45)
        quality = min(99, max(55, rng.gauss(86 + financial * 0.05, 5)))
        delivery = min(0.99, max(0.55, rng.gauss(0.86 + financial / 1000, 0.06)))
        risk = min(
            100, max(0, (100 - financial) * 0.45 + country_risk * 0.35 + (1 - delivery) * 100 * 0.2)
        )
        row = SyntheticSupplier(
            f"SUP-{country}-{number:03d}",
            f"Synthetic {CATEGORIES[number % 10].split()[0]} Works {number:03d}",
            country,
            region,
            CATEGORIES[number % 10],
            round(rng.uniform(0.75, 1.25), 3),
            round(quality, 2),
            round(delivery, 4),
            round(rng.uniform(0.5, 1.5), 3),
            round(financial, 2),
            round(country_risk, 2),
            round(risk, 2),
        )
        rows.append(asdict(row))
    return rows


def inject_deterioration(
    rows: list[dict[str, object]], supplier_code: str = "SUP-DE-014"
) -> dict[str, object]:
    """Return explicit scenario ground truth used to evaluate downstream detection."""
    return {
        "scenario": "supplier_deterioration",
        "supplier_code": supplier_code,
        "before": {"otd": 0.94, "defect_rate": 0.012},
        "after": {"otd": 0.78, "defect_rate": 0.054},
        "price_change": 0.137,
        "lead_time_days_change": 15,
        "injected": any(r["supplier_code"] == supplier_code for r in rows),
    }
