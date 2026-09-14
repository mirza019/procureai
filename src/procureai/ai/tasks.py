from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from sqlalchemy.orm import Session

from procureai.ai.base import AIResponse, LLMProvider
from procureai.ai.guardrails import SYSTEM_GUARDRAIL, validate_evidence
from procureai.ai.providers import GeminiProvider, OllamaProvider
from procureai.config.settings import Settings, get_settings
from procureai.services.analytics import (
    alerts,
    cost_anomalies,
    executive_dashboard,
    quality_summary,
    supplier_scorecards,
)

AgentTask = Literal[
    "executive_brief",
    "supplier_risk_review",
    "savings_priorities",
    "quality_investigation",
    "contract_watch",
]

TASK_PROMPTS: dict[AgentTask, str] = {
    "executive_brief": "Prepare a concise executive procurement brief with priorities and next actions.",
    "supplier_risk_review": "Explain the supplier deterioration evidence, likely hypotheses, and a controlled response plan.",
    "savings_priorities": "Prioritize validated savings opportunities and propose negotiation or sourcing actions.",
    "quality_investigation": "Summarize quality exposure and propose an evidence-gathering investigation plan.",
    "contract_watch": "Prioritize contract and dependency alerts and propose renewal or alternative-sourcing actions.",
}


def provider_from_settings(settings: Settings | None = None) -> LLMProvider:
    selected = settings or get_settings()
    return (
        OllamaProvider(selected) if selected.llm_provider == "ollama" else GeminiProvider(selected)
    )


def evidence_for_task(
    db: Session, task: AgentTask, supplier_code: str = "SUP-DE-014"
) -> dict[str, Any]:
    """Retrieve trusted, bounded evidence for an agent task; no LLM calculations occur here."""
    scorecards = supplier_scorecards(db)
    supplier = next((row for row in scorecards if row["code"] == supplier_code), None)
    common: dict[str, Any] = {"portfolio_kpis": executive_dashboard(db), "open_alerts": alerts(db)}
    if task == "supplier_risk_review":
        common["supplier_scorecard"] = supplier
    elif task == "savings_priorities":
        common["top_cost_anomalies"] = cost_anomalies(db, limit=10)
    elif task == "quality_investigation":
        common["quality_summary"] = quality_summary(db)
        common["supplier_scorecard"] = supplier
    elif task == "contract_watch":
        common["open_alerts"] = [
            row
            for row in common["open_alerts"]
            if row["type"] in {"CONTRACT_EXPIRY", "SINGLE_SOURCE"}
        ]
    validate_evidence(common)
    return common


async def run_agent_task(
    db: Session,
    task: AgentTask,
    supplier_code: str = "SUP-DE-014",
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    evidence = evidence_for_task(db, task, supplier_code)
    llm = provider or provider_from_settings()
    prompt = f"{SYSTEM_GUARDRAIL}\n\nTASK: {TASK_PROMPTS[task]}\nUse headings: Facts, Predictions, Recommendations, Questions to investigate."
    response: AIResponse = await llm.generate(prompt, evidence)
    return {
        "task": task,
        "provider": response.provider,
        "model": response.model,
        "narrative": response.text,
        "evidence": evidence,
        "disclaimer": "Advisory output only. KPI and financial calculations come from deterministic application services.",
    }


def available_tasks() -> Mapping[str, str]:
    return TASK_PROMPTS
