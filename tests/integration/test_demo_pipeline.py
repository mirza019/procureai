from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from procureai.db.base import Base
from procureai.pipelines.validation import data_quality_report
from procureai.services.analytics import executive_dashboard, supplier_scorecards
from procureai.synthetic.demo import load_demo_data


def test_demo_load_is_connected_and_idempotent():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = load_demo_data(db, seed=7, po_count=80)
        second = load_demo_data(db, seed=7, po_count=80)
        assert first == second
        assert first["purchase_orders"] == 80
        assert first["po_lines"] == first["deliveries"]
        assert data_quality_report(db)["status"] == "PASS"
        assert executive_dashboard(db)["total_spend"] > 0
        assert len(supplier_scorecards(db)) == 80
