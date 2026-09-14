import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SupplierCreate(BaseModel):
    supplier_code: str = Field(pattern=r"^SUP-[A-Z]{2}-\d{3}$")
    supplier_name: str = Field(min_length=2, max_length=200)
    country: str = Field(min_length=2, max_length=2)
    region: str
    city: str
    supplier_category: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    payment_terms_days: int = Field(ge=0, le=180)
    preferred_supplier: bool = False
    strategic_supplier: bool = False
    baseline_lead_time_days: int = Field(ge=1, le=365)
    baseline_quality_rating: Decimal = Field(ge=0, le=100)
    baseline_delivery_rating: Decimal = Field(ge=0, le=100)
    risk_tier: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")


class SupplierRead(SupplierCreate):
    model_config = ConfigDict(from_attributes=True)
    supplier_id: uuid.UUID
    active: bool
    created_at: datetime
    updated_at: datetime
