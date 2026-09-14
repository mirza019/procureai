import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from procureai.db.models import Supplier
from procureai.schemas.suppliers import SupplierCreate


class SupplierRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(
        self, *, offset: int = 0, limit: int = 50, search: str | None = None
    ) -> tuple[list[Supplier], int]:
        query = select(Supplier).where(Supplier.active.is_(True))
        if search:
            query = query.where(Supplier.supplier_name.ilike(f"%{search}%"))
        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        return list(
            self.session.scalars(query.order_by(Supplier.supplier_code).offset(offset).limit(limit))
        ), total

    def get(self, supplier_id: uuid.UUID) -> Supplier | None:
        return self.session.get(Supplier, supplier_id)

    def create(self, data: SupplierCreate) -> Supplier:
        supplier = Supplier(**data.model_dump())
        self.session.add(supplier)
        self.session.commit()
        self.session.refresh(supplier)
        return supplier

    def deactivate(self, supplier: Supplier) -> None:
        supplier.active = False
        self.session.commit()
