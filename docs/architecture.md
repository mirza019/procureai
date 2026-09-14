# Architecture

ProcureAI is a modular monolith suited to a low-cost portfolio deployment. FastAPI is the
application boundary, NiceGUI supplies the business UI, and services own deterministic
procurement rules. SQLAlchemy repositories isolate persistence. Provider ports isolate LLM
and file-storage integrations.

Logical PostgreSQL schemas evolve in phases: `raw` preserves source records, `staging`
validates and deduplicates, `core` stores trusted entities, `analytics` serves aggregates,
`ml` records features/models/predictions, and `audit` records runs and business changes.
SQLite remains a test-only convenience.

## Delivery roadmap

1. Foundation and supplier/purchasing vertical slice.
2. Full transactional model, pipeline idempotency, history, and rollback.
3. KPI, scorecard, savings and alerts materializations.
4. Dashboard modules, ML training/inference, AI evidence tools, and reporting.
5. Azure infrastructure, observability, performance tests, and hardening.

