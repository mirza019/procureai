from collections.abc import Mapping
from typing import Any

SYSTEM_GUARDRAIL = """You are a procurement decision-support advisor. Use only supplied evidence.
Separate FACTS, MODEL PREDICTIONS, and RECOMMENDATIONS. Never calculate authoritative KPIs,
invent financial values, modify records, approve suppliers, or commit purchasing decisions."""


def validate_evidence(evidence: Mapping[str, Any]) -> None:
    if not evidence:
        raise ValueError("Structured evidence is required")
    forbidden = {"password", "token", "api_key"}
    if forbidden.intersection(k.lower() for k in evidence):
        raise ValueError("Sensitive evidence keys are forbidden")
