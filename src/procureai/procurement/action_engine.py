from __future__ import annotations

from procureai.schemas.agents import Recommendation, ToolEvidence


def supplier_actions(evidence: ToolEvidence) -> list[Recommendation]:
    """Derive allowed action templates from verified supplier evidence."""
    data = evidence.data
    supplier = data["supplier"]["code"]
    scorecard = data["scorecard"]
    delivery = data["delivery"]
    quality = data["quality"]
    price = data["price"]
    dependency = data["risk_history"][0]["dependency"] if data["risk_history"] else 0
    exposure = float(scorecard["spend"])
    actions: list[Recommendation] = []
    if delivery["previous_otd"] - delivery["current_otd"] > 0.10 and dependency > 60:
        actions.extend(
            [
                Recommendation(
                    action_type="SUPPLIER_PERFORMANCE_REVIEW",
                    title="Supplier performance review",
                    reason="OTD declined more than 10 percentage points while dependency exceeds 60%.",
                    priority="CRITICAL",
                    suggested_owner="Procurement Manager",
                    financial_exposure=exposure,
                    supplier_code=supplier,
                ),
                Recommendation(
                    action_type="ALTERNATIVE_SOURCE_EVALUATION",
                    title="Alternative-source evaluation",
                    reason="High dependency amplifies the verified delivery deterioration.",
                    priority="HIGH",
                    suggested_owner="Strategic Sourcing",
                    financial_exposure=exposure,
                    supplier_code=supplier,
                ),
            ]
        )
    if price["change"] > 0.15:
        actions.append(
            Recommendation(
                action_type="COMMERCIAL_REVIEW",
                title="Commercial and price review",
                reason="Current price index increased more than 15% versus the previous period.",
                priority="HIGH",
                suggested_owner="Cost & Value Engineering",
                financial_exposure=exposure,
                supplier_code=supplier,
            )
        )
    if (
        quality["current_severity_weighted"] > quality["previous_severity_weighted"]
        and quality["current_incidents"]
    ):
        actions.append(
            Recommendation(
                action_type="SUPPLIER_QUALITY_REVIEW",
                title="Joint supplier-quality review",
                reason="Severity-weighted quality incidents deteriorated in the current period.",
                priority="HIGH",
                suggested_owner="Supplier Quality Manager",
                financial_exposure=quality["current_cost"],
                supplier_code=supplier,
            )
        )
    contract = data.get("contract")
    if contract and contract["days_remaining"] <= 90:
        actions.append(
            Recommendation(
                action_type="CONTRACT_RENEWAL_REVIEW",
                title="Contract renewal review",
                reason=f"Contract reaches expiry in {contract['days_remaining']} days.",
                priority="HIGH",
                suggested_owner="Procurement Manager",
                financial_exposure=exposure,
                supplier_code=supplier,
            )
        )
    return actions or [
        Recommendation(
            action_type="MONITOR_SUPPLIER",
            title="Continue supplier monitoring",
            reason="No deterministic escalation rule was triggered.",
            priority="LOW",
            suggested_owner="Procurement Analyst",
            financial_exposure=exposure,
            supplier_code=supplier,
        )
    ]


def cost_actions(evidence: ToolEvidence) -> list[Recommendation]:
    rows = evidence.data.get("opportunities", [])
    return [
        Recommendation(
            action_type="PRICE_NEGOTIATION_PREPARATION",
            title=f"Prepare price review for {row['material']}",
            reason=f"Validated unit-price variance for {row['supplier']} is above the deterministic benchmark.",
            priority="CRITICAL" if row["impact"] >= 250_000 else "HIGH",
            suggested_owner="Cost & Value Engineering",
            financial_exposure=row["impact"],
            supplier_code=row["supplier"],
            material_code=row["material"],
        )
        for row in rows[:5]
    ]
