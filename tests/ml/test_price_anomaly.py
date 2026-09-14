from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from procureai.db.base import Base
from procureai.ml.price_anomaly import predict_price_anomaly, train_price_anomaly_model
from procureai.synthetic.demo import load_demo_data


def test_price_model_training_and_inference(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    path = tmp_path / "model.joblib"
    with Session(engine) as db:
        load_demo_data(db, po_count=100)
        metrics = train_price_anomaly_model(db, path)
    assert metrics["training_records"] > 100
    prediction = predict_price_anomaly(134, 105, 10_000, path)
    assert prediction["potential_financial_impact"] == 290_000
