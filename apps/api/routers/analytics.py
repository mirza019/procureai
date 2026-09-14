from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from apps.api.dependencies import DbSession, require_roles
from procureai.db.models import PurchaseOrder, Role, Supplier, User
from procureai.procurement.metrics import concentration

router = APIRouter(prefix="/analytics", tags=["analytics"])
VIEW_ROLES = (Role.ADMIN, Role.PROCUREMENT_ANALYST, Role.PROCUREMENT_MANAGER, Role.EXECUTIVE)


@router.get("/executive")
def executive_summary(db: DbSession, _: Annotated[User, Depends(require_roles(*VIEW_ROLES))]):
    spend_rows = db.execute(
        select(Supplier.supplier_code, func.sum(PurchaseOrder.total_value))
        .join(PurchaseOrder)
        .group_by(Supplier.supplier_code)
    ).all()
    metrics = concentration({code: Decimal(total) for code, total in spend_rows})
    return {
        "total_spend": metrics["total"],
        "top_supplier_share": metrics["top_supplier_share"],
        "top_5_supplier_share": metrics["top_5_share"],
        "hhi": metrics["hhi"],
        "calculation": "Authoritative SQL totals; shares derived deterministically",
    }
