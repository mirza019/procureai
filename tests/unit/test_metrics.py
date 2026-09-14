from decimal import Decimal

import pytest

from procureai.procurement.metrics import (
    SupplierScoreInput,
    concentration,
    on_time_delivery,
    purchase_price_variance,
    supplier_risk,
    supplier_score,
)


def test_concentration_is_deterministic():
    result = concentration({"A": Decimal(60), "B": Decimal(40)})
    assert result["top_supplier_share"] == Decimal("0.6")
    assert result["hhi"] == Decimal("5200.00")


def test_kpis():
    assert purchase_price_variance(Decimal(10000), Decimal(134), Decimal(105)) == Decimal(290000)
    assert on_time_delivery([(10, 9), (10, 10), (10, 12)]) == Decimal(2) / Decimal(3)


def test_scores_are_explainable_and_validated():
    assert supplier_score(SupplierScoreInput(80, 90, 70, 60, 100)) == 78.5
    result = supplier_risk({"delivery": 90, "quality": 80}, {"delivery": 0.6, "quality": 0.4})
    assert result["score"] == 86 and result["level"] == "CRITICAL"
    with pytest.raises(ValueError):
        supplier_score(SupplierScoreInput(1, 1, 1, 1, 1), {"quality": 0.5})
