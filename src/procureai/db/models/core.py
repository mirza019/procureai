import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from procureai.db.base import Base


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    PROCUREMENT_ANALYST = "PROCUREMENT_ANALYST"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER"
    EXECUTIVE = "EXECUTIVE"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.PROCUREMENT_ANALYST)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"
    supplier_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    region: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(100))
    supplier_category: Mapped[str] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3))
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    preferred_supplier: Mapped[bool] = mapped_column(Boolean, default=False)
    strategic_supplier: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    baseline_lead_time_days: Mapped[int] = mapped_column(Integer)
    baseline_quality_rating: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    baseline_delivery_rating: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    risk_tier: Mapped[str] = mapped_column(String(20), index=True)
    base_price_competitiveness: Mapped[float] = mapped_column(Float, default=1.0)
    capacity: Mapped[float] = mapped_column(Float, default=1.0)
    financial_stability: Mapped[float] = mapped_column(Float, default=80.0)
    country_risk: Mapped[float] = mapped_column(Float, default=20.0)
    orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="supplier")


class Category(Base):
    __tablename__ = "categories"
    category_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_code: Mapped[str] = mapped_column(String(20), unique=True)
    category_name: Mapped[str] = mapped_column(String(120))
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.category_id")
    )
    criticality: Mapped[str] = mapped_column(String(20))


class Material(Base):
    __tablename__ = "materials"
    material_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    material_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    material_name: Mapped[str] = mapped_column(String(160))
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.category_id"), index=True)
    unit_of_measure: Mapped[str] = mapped_column(String(10))
    standard_cost: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    criticality: Mapped[str] = mapped_column(String(20))
    single_source_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    po_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    po_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.supplier_id"), index=True)
    order_date: Mapped[date] = mapped_column(Date, index=True)
    required_delivery_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    buyer: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), index=True)
    total_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contracts.contract_id"))
    supplier: Mapped[Supplier] = relationship(back_populates="orders")
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )
    __table_args__ = (Index("ix_po_supplier_order_date", "supplier_id", "order_date"),)


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    po_item_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.po_id"), index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.material_id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    currency: Mapped[str] = mapped_column(String(3))
    line_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_unit_price: Mapped[Decimal] = mapped_column(Numeric(16, 4))
    price_variance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="items")


class Contract(TimestampMixin, Base):
    __tablename__ = "contracts"
    contract_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.supplier_id"), index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.category_id"))
    contract_number: Mapped[str] = mapped_column(String(30), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    contract_value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    incoterm: Mapped[str] = mapped_column(String(10), default="DAP")
    sla_otd_target: Mapped[float] = mapped_column(Float, default=0.95)
    sla_quality_target: Mapped[float] = mapped_column(Float, default=0.98)
    status: Mapped[str] = mapped_column(String(20), index=True, default="ACTIVE")
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)


class Delivery(Base):
    __tablename__ = "deliveries"
    delivery_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    po_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_order_items.po_item_id"), unique=True
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.supplier_id"), index=True)
    planned_delivery_date: Mapped[date] = mapped_column(Date)
    actual_delivery_date: Mapped[date] = mapped_column(Date, index=True)
    quantity_expected: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    lead_time_days: Mapped[int] = mapped_column(Integer)
    days_late: Mapped[int] = mapped_column(Integer, index=True)
    delivery_status: Mapped[str] = mapped_column(String(20))


class Invoice(Base):
    __tablename__ = "invoices"
    invoice_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.supplier_id"), index=True)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.po_id"), index=True)
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    invoice_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_due_date: Mapped[date] = mapped_column(Date)
    payment_date: Mapped[date | None] = mapped_column(Date)
    invoice_status: Mapped[str] = mapped_column(String(20))
    po_match_status: Mapped[str] = mapped_column(String(20), index=True)
    duplicate_flag: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    variance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)


class QualityIncident(Base):
    __tablename__ = "quality_incidents"
    incident_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.supplier_id"), index=True)
    material_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("materials.material_id"))
    po_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_order_items.po_item_id"))
    incident_date: Mapped[date] = mapped_column(Date, index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    defect_type: Mapped[str] = mapped_column(String(80))
    quantity_affected: Mapped[Decimal] = mapped_column(Numeric(16, 3))
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    root_cause_category: Mapped[str] = mapped_column(String(80))
    resolution_status: Mapped[str] = mapped_column(String(20))
    days_to_close: Mapped[int] = mapped_column(Integer)


class SupplierRiskFactor(Base):
    __tablename__ = "supplier_risk_factors"
    risk_factor_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.supplier_id"), index=True)
    risk_date: Mapped[date] = mapped_column(Date, index=True)
    financial_risk: Mapped[float] = mapped_column(Float)
    delivery_risk: Mapped[float] = mapped_column(Float)
    quality_risk: Mapped[float] = mapped_column(Float)
    geographic_risk: Mapped[float] = mapped_column(Float)
    dependency_risk: Mapped[float] = mapped_column(Float)
    price_risk: Mapped[float] = mapped_column(Float)
    overall_risk: Mapped[float] = mapped_column(Float, index=True)


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    alert_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    alert_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.supplier_id"))
    material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials.material_id"))
    financial_exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    description: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_name: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), index=True)
    trigger_type: Mapped[str] = mapped_column(String(20))
    records_received: Mapped[int] = mapped_column(Integer, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500))
    initiated_by: Mapped[str] = mapped_column(String(320), default="system")


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"
    step_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.run_id"), index=True)
    step_name: Mapped[str] = mapped_column(String(40))
    sequence_number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500))


class AuditLog(Base):
    __tablename__ = "audit_log"
    audit_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(30))
    before_state: Mapped[dict | None] = mapped_column(JSON)
    after_state: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    correlation_id: Mapped[str] = mapped_column(String(50), index=True)


class AgentInteraction(Base):
    __tablename__ = "agent_interactions"
    agent_request_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    question: Mapped[str] = mapped_column(String(1000))
    tools_called: Mapped[list] = mapped_column(JSON)
    entity_ids: Mapped[list] = mapped_column(JSON)
    model_provider: Mapped[str] = mapped_column(String(30))
    model_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), index=True)
    total_latency_ms: Mapped[int] = mapped_column(Integer)
    tool_latency_ms: Mapped[int] = mapped_column(Integer)
    llm_latency_ms: Mapped[int] = mapped_column(Integer)
    error_type: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProcurementAction(TimestampMixin, Base):
    __tablename__ = "procurement_actions"
    action_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    action_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(160))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.supplier_id"), index=True
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.material_id"), index=True
    )
    reason: Mapped[str] = mapped_column(String(500))
    financial_exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    suggested_owner: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcurementTask(TimestampMixin, Base):
    __tablename__ = "procurement_tasks"
    task_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(String(1000))
    action_type: Mapped[str] = mapped_column(String(60), index=True)
    priority: Mapped[str] = mapped_column(String(20), index=True)
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[str | None] = mapped_column(String(100))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.supplier_id"))
    material_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("materials.material_id"))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contracts.contract_id"))
    financial_exposure: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    assigned_role: Mapped[str] = mapped_column(String(40))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    evidence_bundle: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[dict | None] = mapped_column(JSON)


class Report(Base):
    __tablename__ = "reports"
    report_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    report_type: Mapped[str] = mapped_column(String(20), index=True)
    audience_role: Mapped[str] = mapped_column(String(40), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    data_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    template_version: Mapped[str] = mapped_column(String(40))
    analytics_version: Mapped[str] = mapped_column(String(40), default="analytics-v1")
    ml_model_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[str] = mapped_column(String(10), default="1.0")
    status: Mapped[str] = mapped_column(String(20), index=True)
    pdf_location: Mapped[str | None] = mapped_column(String(500))
    excel_location: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(String(4000))
    snapshot: Mapped[dict] = mapped_column(JSON)
    llm_provider: Mapped[str | None] = mapped_column(String(30))
    llm_model: Mapped[str | None] = mapped_column(String(100))


class ReportSection(Base):
    __tablename__ = "report_sections"
    section_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.report_id"), index=True)
    section_key: Mapped[str] = mapped_column(String(60))
    sequence_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[dict] = mapped_column(JSON)


class ReportEvidence(Base):
    __tablename__ = "report_evidence"
    evidence_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.report_id"), index=True)
    metric: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(100))
    period: Mapped[str] = mapped_column(String(60))
    value: Mapped[dict] = mapped_column(JSON)
    previous_value: Mapped[dict | None] = mapped_column(JSON)
    calculation_service: Mapped[str] = mapped_column(String(120))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReportRecommendation(Base):
    __tablename__ = "report_recommendations"
    recommendation_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.report_id"), index=True)
    action: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(800))
    expected_benefit: Mapped[str] = mapped_column(String(500))
    priority: Mapped[str] = mapped_column(String(20))
    suggested_owner: Mapped[str] = mapped_column(String(100))
    suggested_due: Mapped[str] = mapped_column(String(80))
    confidence: Mapped[str] = mapped_column(String(20))
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    disposition: Mapped[str] = mapped_column(String(20), default="PENDING")


class ReportTask(Base):
    __tablename__ = "report_tasks"
    report_task_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.report_id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_tasks.task_id"), index=True)


class ReportSchedule(TimestampMixin, Base):
    __tablename__ = "report_schedules"
    schedule_id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_type: Mapped[str] = mapped_column(String(20))
    audience_role: Mapped[str] = mapped_column(String(40))
    cron_expression: Mapped[str] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Berlin")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
