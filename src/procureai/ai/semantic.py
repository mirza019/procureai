from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from procureai.schemas.agents import EntityReference, RoutingDecision

SEMANTIC_CATALOG = {
    "risk": {
        "entity": "supplier",
        "field": "risk",
        "meaning": "Current deterministic supplier overall risk score",
        "aggregations": ["MIN", "MAX"],
    },
    "spend": {
        "entity": "supplier",
        "field": "spend",
        "meaning": "Approved purchase-order value",
        "aggregations": ["MIN", "MAX", "SUM"],
    },
    "delivery": {
        "entity": "supplier",
        "field": "otd",
        "meaning": "Share of deliveries received on or before plan",
        "aggregations": ["MIN", "MAX", "AVG"],
    },
    "quality": {
        "entity": "supplier",
        "field": "quality_score",
        "meaning": "Deterministic supplier quality score",
        "aggregations": ["MIN", "MAX", "AVG"],
    },
    "quality_cost": {
        "entity": "supplier",
        "field": "quality_cost",
        "meaning": "Recorded cost of poor quality",
        "aggregations": ["MAX", "SUM"],
    },
}

GLOBAL_RANKING = re.compile(
    r"\b(highest|lowest|best|worst|top|bottom|safest|most|least)\b", re.IGNORECASE
)
FOLLOWUP = re.compile(r"\b(it|its|that supplier|this supplier|why|what about)\b", re.IGNORECASE)


def resolve_period(text: str, today: date | None = None) -> tuple[date, date] | None:
    today = today or datetime.now(UTC).date()
    if "last month" in text:
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    if "this month" in text:
        return today.replace(day=1), today
    if "last week" in text:
        end = today - timedelta(days=today.weekday() + 1)
        return end - timedelta(days=6), end
    if "this week" in text:
        return today - timedelta(days=today.weekday()), today
    if "last 12 months" in text:
        return today - timedelta(days=365), today
    return None


def plan_question(
    question: str, explicit_entities: list[EntityReference], context: list[EntityReference]
) -> RoutingDecision | None:
    text = question.lower().strip()
    period = resolve_period(text)
    metric = None
    if "reduce sourcing risk" in text or "sourcing risk" in text:
        return RoutingDecision(
            agents=["RankingAgent"],
            intent="ranking",
            scope="GLOBAL",
            entities=[],
            query_plan={
                "entity_type": "supplier",
                "metric": "risk",
                "direction": "desc",
                "limit": 5,
                "period": period,
            },
        )
    if "risk" in text or "safest" in text:
        metric = "risk"
    elif "spend" in text:
        metric = "spend"
    elif "delivery" in text or "otd" in text:
        metric = "otd"
    elif "quality cost" in text:
        metric = "quality_cost"
    elif "quality" in text:
        metric = "quality_score"
    if GLOBAL_RANKING.search(text) and metric:
        ascending = any(
            word in text
            for word in ("lowest", "bottom", "least", "safest", "worst delivery", "worst otd")
        )
        if metric == "quality_score" and "worst" in text:
            ascending = True
        if metric == "otd" and "best" in text:
            ascending = False
        limit_match = re.search(r"\b(?:top|bottom)\s+(\d+)\b", text)
        return RoutingDecision(
            agents=["RankingAgent"],
            intent="ranking",
            scope="GLOBAL",
            entities=[],
            query_plan={
                "entity_type": "supplier",
                "metric": metric,
                "direction": "asc" if ascending else "desc",
                "limit": min(int(limit_match.group(1)), 20) if limit_match else 1,
                "period": period,
            },
        )
    if explicit_entities:
        return None
    if context and FOLLOWUP.search(text):
        return RoutingDecision(
            agents=["SupplierInvestigationAgent"],
            intent="supplier_investigation",
            scope="CONVERSATIONAL_FOLLOWUP",
            entities=context,
        )
    return None
