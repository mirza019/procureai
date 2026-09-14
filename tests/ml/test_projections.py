from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from procureai.db.base import Base
from procureai.services.projections import procurement_projections
from procureai.synthetic.demo import load_demo_data


def test_procurement_projections_are_bounded_and_labelled():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        load_demo_data(db, po_count=180)
        result = procurement_projections(db, horizon=3)
    assert len(result["spend_projection"]) == 3
    assert len(result["delivery_projection"]) == 3
    assert all(0 <= row["otd"] <= 100 for row in result["delivery_projection"])
    assert result["priority_predictions"]
    assert all("model" in item for item in result["priority_predictions"])
    assert "not guaranteed" in result["disclaimer"]


def test_projection_horizon_is_bounded():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        load_demo_data(db, po_count=20)
        try:
            procurement_projections(db, horizon=24)
        except ValueError as exc:
            assert "between 1 and 12" in str(exc)
        else:
            raise AssertionError("Expected bounded horizon validation")
