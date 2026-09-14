from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from procureai.ai.base import AIResponse, LLMProvider
from procureai.db.base import Base
from procureai.db.models import Report, ReportEvidence, Role
from procureai.reporting.intelligent import (
    generate_report,
    monthly_period,
    role_sections,
    weekly_period,
)
from procureai.schemas.reporting import ReportRequest, ReportStatus, ReportType
from procureai.synthetic.demo import load_demo_data


@pytest.fixture
def demo_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        load_demo_data(session, po_count=50)
        yield session


class FailingProvider(LLMProvider):
    async def generate(self, prompt, evidence):
        raise RuntimeError("provider unavailable")


class StructuredProvider(LLMProvider):
    async def generate(self, prompt, evidence):
        return AIResponse(
            text="""{"executive_summary":"Performance requires attention.","key_findings":[],"positive_developments":[],"risks":[],"opportunities":[],"recommendations":[],"suggested_tasks":[],"next_period_priorities":[]}""",
            provider="test",
            model="structured-v1",
        )


def test_period_calculation():
    assert weekly_period(date(2026, 10, 5)) == (date(2026, 9, 28), date(2026, 10, 4))
    assert monthly_period(date(2026, 10, 1)) == (date(2026, 9, 1), date(2026, 9, 30))


def test_role_templates_are_distinct():
    analyst = role_sections(Role.PROCUREMENT_ANALYST)
    manager = role_sections(Role.PROCUREMENT_MANAGER)
    executive = role_sections(Role.EXECUTIVE)
    admin = role_sections(Role.ADMIN)
    assert analyst != manager != executive != admin
    assert "invoice_exceptions" in analyst
    assert "recommendations" in manager
    assert "pipeline_health" in admin
    assert "materials" not in executive


@pytest.mark.asyncio
async def test_generation_is_versioned_snapshot_and_survives_ai_failure(demo_db, tmp_path):
    request = ReportRequest(
        report_type=ReportType.MONTHLY,
        audience_role=Role.PROCUREMENT_MANAGER,
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )
    first = await generate_report(
        demo_db, request, provider=FailingProvider(), output_root=tmp_path
    )
    second = await generate_report(
        demo_db, request, provider=StructuredProvider(), output_root=tmp_path
    )
    assert first.status == ReportStatus.READY
    assert first.version == "1.0"
    assert second.version == "1.1"
    assert first.warnings
    assert first.generated_at.tzinfo is not None
    assert (tmp_path / f"{first.report_id}-v1.0.pdf").exists()
    assert (tmp_path / f"{first.report_id}-v1.0.xlsx").exists()
    stored = demo_db.get(Report, first.report_id)
    snapshot_before = stored.snapshot
    assert snapshot_before == first.snapshot
    assert (
        len(
            list(
                demo_db.scalars(
                    select(ReportEvidence).where(ReportEvidence.report_id == first.report_id)
                )
            )
        )
        >= 8
    )


@pytest.mark.asyncio
async def test_report_rejects_invalid_period(demo_db, tmp_path):
    request = ReportRequest(
        report_type=ReportType.WEEKLY,
        audience_role=Role.EXECUTIVE,
        period_start=date(2026, 9, 30),
        period_end=date(2026, 9, 1),
    )
    with pytest.raises(ValueError, match="period end"):
        await generate_report(demo_db, request, output_root=tmp_path)
