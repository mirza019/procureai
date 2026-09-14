.PHONY: install lint test run migrate bootstrap
install:
	python -m pip install -e '.[dev]'
lint:
	ruff check .
	ruff format --check .
test:
	pytest
run:
	uvicorn apps.api.main:app --reload
migrate:
	alembic upgrade head
bootstrap: migrate
	python scripts/bootstrap.py

