import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.api.dependencies import DbSession, current_user, require_roles
from procureai.db.models import Role, User
from procureai.db.repositories.suppliers import SupplierRepository
from procureai.schemas.suppliers import SupplierCreate, SupplierRead

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("")
def list_suppliers(
    db: DbSession,
    _: Annotated[User, Depends(current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: str | None = None,
):
    rows, total = SupplierRepository(db).list(
        offset=(page - 1) * page_size, limit=page_size, search=search
    )
    return {
        "items": [SupplierRead.model_validate(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    data: SupplierCreate, db: DbSession, _: Annotated[User, Depends(require_roles(Role.ADMIN))]
):
    return SupplierRepository(db).create(data)


@router.delete("/{supplier_id}", status_code=204)
def archive_supplier(
    supplier_id: uuid.UUID, db: DbSession, _: Annotated[User, Depends(require_roles(Role.ADMIN))]
):
    repository = SupplierRepository(db)
    supplier = repository.get(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    repository.deactivate(supplier)
