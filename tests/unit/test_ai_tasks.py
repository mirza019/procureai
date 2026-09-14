import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from procureai.ai.base import AIResponse, LLMProvider
from procureai.ai.tasks import evidence_for_task, run_agent_task
from procureai.db.base import Base
from procureai.synthetic.demo import load_demo_data


class FakeProvider(LLMProvider):
    async def generate(self, prompt, evidence):
        assert "Never calculate authoritative KPIs" in prompt
        assert evidence["portfolio_kpis"]["total_spend"] > 0
        return AIResponse(
            "Facts\nValidated evidence.\nRecommendations\nReview supplier.", "fake", "test"
        )


@pytest.mark.asyncio
async def test_agent_task_is_grounded_in_service_evidence():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        load_demo_data(db, po_count=40)
        evidence = evidence_for_task(db, "supplier_risk_review")
        assert evidence["supplier_scorecard"]["code"] == "SUP-DE-014"
        result = await run_agent_task(db, "supplier_risk_review", provider=FakeProvider())
    assert result["provider"] == "fake"
    assert "deterministic" in result["disclaimer"]
