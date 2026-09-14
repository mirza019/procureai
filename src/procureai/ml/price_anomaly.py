from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from sqlalchemy.orm import Session

from procureai.db.models import PurchaseOrderItem

MODEL_PATH = Path("models/trained/price_anomaly.joblib")


def train_price_anomaly_model(db: Session, model_path: Path = MODEL_PATH) -> dict[str, float | int]:
    """Train an unsupervised price anomaly model on deterministic pricing features."""
    rows = db.execute(
        select(
            PurchaseOrderItem.unit_price,
            PurchaseOrderItem.expected_unit_price,
            PurchaseOrderItem.quantity,
            PurchaseOrderItem.price_variance,
        )
    ).all()
    features = np.array(
        [
            [
                float(actual) / max(float(expected), 0.01),
                np.log1p(float(qty)),
                float(variance) / max(float(qty), 1),
            ]
            for actual, expected, qty, variance in rows
        ]
    )
    model = IsolationForest(n_estimators=150, contamination=0.025, random_state=42).fit(features)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    predictions = model.predict(features)
    return {
        "training_records": len(rows),
        "flagged": int((predictions == -1).sum()),
        "flag_rate": float((predictions == -1).mean()),
    }


def predict_price_anomaly(
    actual: float, expected: float, quantity: float, model_path: Path = MODEL_PATH
) -> dict:
    if actual < 0 or expected <= 0 or quantity <= 0:
        raise ValueError("Prices and quantity must be positive")
    model = joblib.load(model_path)
    features = np.array([[actual / expected, np.log1p(quantity), actual - expected]])
    score = float(-model.decision_function(features)[0])
    flag = bool(model.predict(features)[0] == -1)
    return {
        "anomaly_score": round(score, 4),
        "anomaly_flag": flag,
        "expected_range": [round(expected * 0.9, 2), round(expected * 1.1, 2)],
        "potential_financial_impact": round(max(0, actual - expected) * quantity, 2),
    }
