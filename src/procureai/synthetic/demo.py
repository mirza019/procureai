from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from procureai.db.models import (
    Alert,
    Category,
    Contract,
    Delivery,
    Invoice,
    Material,
    PipelineRun,
    PipelineStep,
    PurchaseOrder,
    PurchaseOrderItem,
    QualityIncident,
    Supplier,
    SupplierRiskFactor,
)

CATEGORY_NAMES = [
    "Electrical Components",
    "Mechanical Components",
    "Steel & Metals",
    "Copper & Conductors",
    "Electronics",
    "Industrial Services",
    "Logistics",
    "Software & IT",
    "Engineering Services",
    "Safety Equipment",
]
COUNTRIES = [
    ("DE", "Europe", "Berlin"),
    ("PL", "Europe", "Wroclaw"),
    ("US", "Americas", "Houston"),
    ("MX", "Americas", "Monterrey"),
    ("IN", "Asia", "Pune"),
    ("JP", "Asia", "Osaka"),
    ("ES", "Europe", "Bilbao"),
    ("CZ", "Europe", "Brno"),
]
DEFECTS = [
    "Dimensional deviation",
    "Surface defect",
    "Documentation gap",
    "Electrical failure",
    "Packaging damage",
]
ROOT_CAUSES = [
    "Process control",
    "Raw material",
    "Handling",
    "Design interpretation",
    "Capacity pressure",
]


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _reset_business_data(db: Session) -> None:
    """Clear only synthetic business data, preserving users and migration state."""
    for model in [
        PipelineStep,
        PipelineRun,
        Alert,
        SupplierRiskFactor,
        QualityIncident,
        Invoice,
        Delivery,
        PurchaseOrderItem,
        PurchaseOrder,
        Contract,
        Material,
        Category,
        Supplier,
    ]:
        db.execute(delete(model))
    db.commit()


def load_demo_data(db: Session, seed: int = 42, po_count: int = 2500) -> dict[str, int]:
    """Create a connected, reproducible three-year procurement portfolio dataset."""
    if db.scalar(select(Supplier.supplier_id).limit(1)):
        return counts(db)
    rng = random.Random(seed)
    run = PipelineRun(
        pipeline_name="synthetic_demo_bootstrap", status="RUNNING", trigger_type="MANUAL"
    )
    db.add(run)
    db.flush()
    categories = [
        Category(
            category_code=f"CAT-{i:02d}",
            category_name=name,
            criticality="HIGH" if i in {1, 3, 5} else "MEDIUM",
        )
        for i, name in enumerate(CATEGORY_NAMES, 1)
    ]
    db.add_all(categories)
    db.flush()

    suppliers: list[Supplier] = []
    for i in range(1, 81):
        country, region, city = COUNTRIES[(i - 1) % len(COUNTRIES)]
        if i == 14:
            country, region, city = "DE", "Europe", "Hamburg"
        financial = rng.uniform(58, 97)
        country_risk = rng.uniform(8, 48)
        quality = min(98, max(62, rng.gauss(90, 6)))
        delivery = min(98, max(62, rng.gauss(91, 7)))
        raw_risk = (100 - financial) * 0.4 + country_risk * 0.3 + (100 - delivery) * 0.3
        if i == 14:
            quality, delivery, raw_risk = 76, 78, 82
        tier = (
            "CRITICAL"
            if raw_risk >= 80
            else "HIGH"
            if raw_risk >= 60
            else "MEDIUM"
            if raw_risk >= 30
            else "LOW"
        )
        suppliers.append(
            Supplier(
                supplier_code=f"SUP-{country}-{i:03d}",
                supplier_name=f"Synthetic {CATEGORY_NAMES[i % 10].split()[0]} Works {i:03d}",
                country=country,
                region=region,
                city=city,
                supplier_category=CATEGORY_NAMES[i % 10],
                currency="EUR",
                payment_terms_days=rng.choice([30, 45, 60]),
                preferred_supplier=i % 3 != 0,
                strategic_supplier=i <= 15,
                baseline_lead_time_days=rng.randint(10, 50),
                baseline_quality_rating=quality,
                baseline_delivery_rating=delivery,
                risk_tier=tier,
                base_price_competitiveness=rng.uniform(0.88, 1.15),
                capacity=rng.uniform(0.65, 1.35),
                financial_stability=financial,
                country_risk=country_risk,
            )
        )
    db.add_all(suppliers)
    db.flush()

    materials: list[Material] = []
    for i in range(1, 301):
        category = categories[(i - 1) % 10]
        cost = rng.choice([18, 42, 86, 105, 240, 720, 1400, 4200]) * rng.uniform(0.75, 1.3)
        materials.append(
            Material(
                material_code=f"MAT-{i:04d}",
                material_name=f"Synthetic {category.category_name} Item {i:04d}",
                category_id=category.category_id,
                unit_of_measure=rng.choice(["EA", "KG", "M", "H"]),
                standard_cost=_money(cost),
                criticality="CRITICAL" if i % 19 == 0 else "HIGH" if i % 5 == 0 else "MEDIUM",
                single_source_allowed=False,
                active=True,
            )
        )
    db.add_all(materials)
    db.flush()

    today = datetime.now(UTC).date()
    contracts: list[Contract] = []
    for i, supplier in enumerate(suppliers[:55], 1):
        end = today + timedelta(days=45 if i == 14 else rng.randint(-180, 540))
        status = "ACTIVE" if end >= today else "EXPIRED"
        contracts.append(
            Contract(
                supplier_id=supplier.supplier_id,
                category_id=categories[i % 10].category_id,
                contract_number=f"CTR-{i:04d}",
                start_date=end - timedelta(days=730),
                end_date=end,
                contract_value=_money(rng.uniform(300_000, 6_000_000)),
                status=status,
                payment_terms_days=supplier.payment_terms_days,
                auto_renew=i % 4 == 0,
            )
        )
    db.add_all(contracts)
    db.flush()
    contract_by_supplier = {c.supplier_id: c for c in contracts if c.status == "ACTIVE"}

    start_date = today - timedelta(days=1095)
    invoices: list[Invoice] = []
    deliveries: list[Delivery] = []
    incidents: list[QualityIncident] = []
    total_lines = 0
    for number in range(1, po_count + 1):
        order_date = start_date + timedelta(days=rng.randrange(1095))
        supplier = rng.choices(
            suppliers,
            weights=[
                7 if s.strategic_supplier else 2 if s.preferred_supplier else 1 for s in suppliers
            ],
        )[0]
        contract = contract_by_supplier.get(supplier.supplier_id) if rng.random() < 0.82 else None
        line_count = rng.randint(1, 4)
        selected = rng.sample(materials, line_count)
        po = PurchaseOrder(
            po_number=f"PO-{order_date.year}-{number:06d}",
            supplier_id=supplier.supplier_id,
            order_date=order_date,
            required_delivery_date=order_date + timedelta(days=supplier.baseline_lead_time_days),
            currency="EUR",
            buyer=f"Buyer {number % 12 + 1:02d}",
            status="CLOSED" if order_date < today - timedelta(days=60) else "OPEN",
            total_value=0,
            contract_id=contract.contract_id if contract else None,
        )
        db.add(po)
        db.flush()
        po_total = 0.0
        for line_no, material in enumerate(selected, 1):
            quantity = rng.choice([5, 10, 25, 50, 100, 250, 500, 1000])
            standard = float(material.standard_cost)
            inflation = 1 + 0.035 * ((order_date - start_date).days / 365)
            unit_price = (
                standard * supplier.base_price_competitiveness * inflation * rng.uniform(0.94, 1.07)
            )
            if supplier.supplier_code == "SUP-DE-014" and order_date > today - timedelta(days=365):
                unit_price *= 1.137
            if material.material_code == "MAT-0078" and number % 79 == 0:
                unit_price = 134
                quantity = 10_000
            line_value = quantity * unit_price
            po_total += line_value
            item = PurchaseOrderItem(
                po_id=po.po_id,
                material_id=material.material_id,
                quantity=quantity,
                unit_price=_money(unit_price),
                currency="EUR",
                line_value=_money(line_value),
                expected_unit_price=_money(standard * inflation),
                price_variance=_money(quantity * (unit_price - standard * inflation)),
            )
            db.add(item)
            db.flush()
            total_lines += 1
            reliability = float(supplier.baseline_delivery_rating) / 100
            if supplier.supplier_code == "SUP-DE-014" and order_date > today - timedelta(days=365):
                reliability = 0.78
            late = 0 if rng.random() < reliability else rng.randint(2, 28)
            planned = po.required_delivery_date
            actual = planned + timedelta(days=late)
            deliveries.append(
                Delivery(
                    po_item_id=item.po_item_id,
                    supplier_id=supplier.supplier_id,
                    planned_delivery_date=planned,
                    actual_delivery_date=actual,
                    quantity_expected=quantity,
                    quantity_received=_money(quantity * rng.uniform(0.97, 1.0)),
                    lead_time_days=(actual - order_date).days,
                    days_late=late,
                    delivery_status="ON_TIME" if late == 0 else "LATE",
                )
            )
            defect_probability = max(0.008, (100 - float(supplier.baseline_quality_rating)) / 350)
            if supplier.supplier_code == "SUP-DE-014" and order_date > today - timedelta(days=365):
                defect_probability = 0.12
            if rng.random() < defect_probability:
                severity = rng.choices(["LOW", "MEDIUM", "HIGH", "CRITICAL"], [45, 35, 16, 4])[0]
                affected = max(1, round(quantity * rng.uniform(0.01, 0.15), 2))
                incidents.append(
                    QualityIncident(
                        supplier_id=supplier.supplier_id,
                        material_id=material.material_id,
                        po_item_id=item.po_item_id,
                        incident_date=actual + timedelta(days=rng.randint(0, 8)),
                        severity=severity,
                        defect_type=rng.choice(DEFECTS),
                        quantity_affected=affected,
                        estimated_cost=_money(affected * unit_price * rng.uniform(0.3, 1.4)),
                        root_cause_category=rng.choice(ROOT_CAUSES),
                        resolution_status="CLOSED",
                        days_to_close=rng.randint(
                            4, 75 if severity in {"HIGH", "CRITICAL"} else 35
                        ),
                    )
                )
        po.total_value = _money(po_total)
        mismatch = rng.random() < 0.045
        duplicate = number % 607 == 0
        invoice_amount = po_total * (rng.uniform(1.04, 1.15) if mismatch else 1)
        invoice_date = order_date + timedelta(
            days=supplier.baseline_lead_time_days + rng.randint(2, 25)
        )
        invoices.append(
            Invoice(
                invoice_number=f"INV-{number:07d}",
                supplier_id=supplier.supplier_id,
                po_id=po.po_id,
                invoice_date=invoice_date,
                invoice_amount=_money(invoice_amount),
                payment_due_date=invoice_date + timedelta(days=supplier.payment_terms_days),
                payment_date=invoice_date
                + timedelta(days=supplier.payment_terms_days + rng.randint(-5, 12)),
                invoice_status="PAID",
                po_match_status="MISMATCH" if mismatch else "MATCHED",
                duplicate_flag=duplicate,
                variance_amount=_money(invoice_amount - po_total),
            )
        )
        if number % 250 == 0:
            db.flush()
    db.add_all(deliveries + invoices + incidents)

    for month in range(12):
        risk_date = today - timedelta(days=month * 30)
        for supplier in suppliers:
            deteriorating = supplier.supplier_code == "SUP-DE-014"
            delivery_risk = (
                (22 + (11 - month) * 4.8)
                if deteriorating
                else max(4, 100 - float(supplier.baseline_delivery_rating) + rng.uniform(-4, 5))
            )
            quality_risk = (
                (24 + (11 - month) * 4.2)
                if deteriorating
                else max(3, 100 - float(supplier.baseline_quality_rating) + rng.uniform(-4, 5))
            )
            dependency = 78 if deteriorating else rng.uniform(8, 65)
            overall = (
                0.22 * delivery_risk
                + 0.22 * quality_risk
                + 0.18 * (100 - supplier.financial_stability)
                + 0.14 * supplier.country_risk
                + 0.14 * dependency
                + 0.10 * rng.uniform(5, 45)
            )
            if deteriorating and month == 0:
                overall = 82
            db.add(
                SupplierRiskFactor(
                    supplier_id=supplier.supplier_id,
                    risk_date=risk_date,
                    financial_risk=100 - supplier.financial_stability,
                    delivery_risk=delivery_risk,
                    quality_risk=quality_risk,
                    geographic_risk=supplier.country_risk,
                    dependency_risk=dependency,
                    price_risk=68 if deteriorating else rng.uniform(5, 45),
                    overall_risk=overall,
                )
            )

    special = next(s for s in suppliers if s.supplier_code == "SUP-DE-014")
    special_material = next(m for m in materials if m.material_code == "MAT-0078")
    alerts = [
        Alert(
            alert_type="SUPPLIER_DETERIORATION",
            severity="CRITICAL",
            supplier_id=special.supplier_id,
            financial_exposure=_money(236_000),
            description="SUP-DE-014: OTD fell from 94% to 78%; quality incidents and prices increased.",
        ),
        Alert(
            alert_type="PRICE_ANOMALY",
            severity="HIGH",
            supplier_id=special.supplier_id,
            material_id=special_material.material_id,
            financial_exposure=_money(290_000),
            description="MAT-0078 purchased at €134 versus €105 historical benchmark.",
        ),
        Alert(
            alert_type="CONTRACT_EXPIRY",
            severity="HIGH",
            supplier_id=special.supplier_id,
            financial_exposure=_money(1_250_000),
            description="Strategic supplier contract expires within 60 days.",
        ),
        Alert(
            alert_type="SINGLE_SOURCE",
            severity="HIGH",
            supplier_id=special.supplier_id,
            material_id=special_material.material_id,
            financial_exposure=_money(780_000),
            description="Critical material dependency exceeds 80%.",
        ),
        Alert(
            alert_type="INVOICE_CONTROL",
            severity="MEDIUM",
            financial_exposure=_money(84_500),
            description="Duplicate and mismatched invoices require review.",
        ),
    ]
    db.add_all(alerts)
    steps = ["INGEST", "VALIDATE", "STAGE", "TRANSFORM", "MERGE", "ANALYTICS", "ML", "COMPLETE"]
    final_counts = {
        "suppliers": len(suppliers),
        "materials": len(materials),
        "purchase_orders": po_count,
        "po_lines": total_lines,
        "deliveries": len(deliveries),
        "invoices": len(invoices),
        "quality_incidents": len(incidents),
    }
    processed = sum(final_counts.values())
    for sequence, name in enumerate(steps, 1):
        db.add(
            PipelineStep(
                run_id=run.run_id,
                step_name=name,
                sequence_number=sequence,
                status="SUCCESS",
                finished_at=datetime.now(UTC),
                records_processed=processed if name in {"MERGE", "ANALYTICS"} else po_count,
            )
        )
    run.status = "SUCCESS"
    run.finished_at = datetime.now(UTC)
    run.records_received = processed
    run.records_inserted = processed
    db.commit()
    return counts(db)


def rebuild_demo_data(db: Session, seed: int = 42, po_count: int = 2500) -> dict[str, int]:
    _reset_business_data(db)
    return load_demo_data(db, seed, po_count)


def counts(db: Session) -> dict[str, int]:
    from sqlalchemy import func

    return {
        name: db.scalar(select(func.count()).select_from(model)) or 0
        for name, model in {
            "suppliers": Supplier,
            "materials": Material,
            "purchase_orders": PurchaseOrder,
            "po_lines": PurchaseOrderItem,
            "deliveries": Delivery,
            "invoices": Invoice,
            "quality_incidents": QualityIncident,
            "alerts": Alert,
        }.items()
    }
