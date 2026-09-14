# Local demo guide

## Start

```bash
source .venv/bin/activate
alembic upgrade head
python scripts/bootstrap.py
python scripts/train_models.py
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
# second terminal
python apps/frontend/main.py
```

Open the dashboard at <http://127.0.0.1:8080> and API documentation at
<http://127.0.0.1:8000/api/docs>.

All local demo users use `ProcureAI-Demo-2026!` unless `DEMO_ADMIN_PASSWORD` is set:

- `admin@procureai.local`
- `analyst@procureai.local`
- `manager@procureai.local`
- `executive@procureai.local`

These credentials are demo-only. Bootstrap refuses to run in production mode.

## Prepared story

Supplier `SUP-DE-014` is intentionally deteriorating: OTD moved from 94% to 78%, quality
incidents increased, prices rose 13.7%, dependency is elevated, and the current transparent
risk score is 82/100. Material `MAT-0078` contains a controlled €134 versus €105 price
scenario with €290,000 potential financial impact.

The application contains three years of connected synthetic POs, lines, deliveries,
invoices, incidents, contracts, monthly risk factors, alerts, and traceable pipeline steps.
