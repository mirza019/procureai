from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.db.models import Delivery, Invoice, PurchaseOrder, PurchaseOrderItem, Supplier


def data_quality_report(db: Session) -> dict:
    """Run deterministic relational and financial integrity checks."""
    orphan_items = (
        db.scalar(
            select(func.count())
            .select_from(PurchaseOrderItem)
            .outerjoin(PurchaseOrder)
            .where(PurchaseOrder.po_id.is_(None))
        )
        or 0
    )
    orphan_deliveries = (
        db.scalar(
            select(func.count())
            .select_from(Delivery)
            .outerjoin(PurchaseOrderItem)
            .where(PurchaseOrderItem.po_item_id.is_(None))
        )
        or 0
    )
    orphan_invoices = (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .outerjoin(PurchaseOrder)
            .where(PurchaseOrder.po_id.is_(None))
        )
        or 0
    )
    orphan_suppliers = (
        db.scalar(
            select(func.count())
            .select_from(PurchaseOrder)
            .outerjoin(Supplier)
            .where(Supplier.supplier_id.is_(None))
        )
        or 0
    )
    invalid_amounts = (
        db.scalar(
            select(func.count())
            .select_from(PurchaseOrderItem)
            .where((PurchaseOrderItem.quantity < 0) | (PurchaseOrderItem.unit_price < 0))
        )
        or 0
    )
    totals = dict(
        db.execute(
            select(PurchaseOrderItem.po_id, func.sum(PurchaseOrderItem.line_value)).group_by(
                PurchaseOrderItem.po_id
            )
        ).all()
    )
    purchase_orders = db.scalars(select(PurchaseOrder)).all()
    reconciliation_failures = sum(
        abs(Decimal(po.total_value) - Decimal(totals.get(po.po_id, 0))) > Decimal("0.02")
        for po in purchase_orders
    )
    checks = {
        "orphan_po_lines": orphan_items,
        "orphan_deliveries": orphan_deliveries,
        "orphan_invoices": orphan_invoices,
        "orphan_supplier_references": orphan_suppliers,
        "invalid_amounts": invalid_amounts,
        "po_total_reconciliation_failures": reconciliation_failures,
    }
    return {
        "status": "PASS" if not any(checks.values()) else "FAIL",
        "checks": checks,
        "records_checked": sum(totals.values(), Decimal(0)) and len(purchase_orders),
    }
