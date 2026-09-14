from procureai.db.session import SessionLocal
from procureai.ml.price_anomaly import train_price_anomaly_model

if __name__ == "__main__":
    with SessionLocal() as session:
        print(train_price_anomaly_model(session))
