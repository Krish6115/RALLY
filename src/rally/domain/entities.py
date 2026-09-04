from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any
from pydantic import BaseModel, Field
from rally.domain.enums import (
    PaymentMethod, ErrorSource, RecoveryAction, PaymentStatus,
    ExecutionOutcome, WebhookEventType
)

def utcnow():
    return datetime.now(timezone.utc)

class Merchant(BaseModel):
    merchant_id: str
    name: str = "Merchant"
    created_at: datetime = Field(default_factory=utcnow)
    is_active: bool = True

class Customer(BaseModel):
    customer_id: str
    contact: str = "+919876543210"
    email: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    opted_out: bool = False

class Order(BaseModel):
    order_id: str
    merchant_id: str
    customer_id: str
    amount_inr: float = Field(..., gt=0)
    currency: str = "INR"
    status: str = "created"
    created_at: datetime = Field(default_factory=utcnow)
    paid_at: Optional[datetime] = None

class Payment(BaseModel):
    payment_id: str
    order_id: str
    amount_inr: float = Field(..., gt=0)
    status: PaymentStatus = PaymentStatus.CREATED
    method: PaymentMethod = PaymentMethod.UPI
    created_at: datetime = Field(default_factory=utcnow)
    captured_at: Optional[datetime] = None

class PaymentFailure(BaseModel):
    failure_id: str
    payment_id: str
    order_id: str
    error_code: str
    error_source: ErrorSource
    error_description: str = ""
    occurred_at: datetime = Field(default_factory=utcnow)
    attempt_number: int = Field(default=1, ge=1)
    
class MerchantPolicy(BaseModel):
    merchant_id: str = "merchant_default"
    max_retries: int = Field(default=3, ge=0)
    max_nudges_per_day: int = Field(default=3, ge=0)
    allowed_channels: list[str] = Field(default_factory=lambda: ["sms", "whatsapp", "email"])
    allowed_methods: list[PaymentMethod] = Field(default_factory=lambda: list(PaymentMethod))
    opt_out_customer_ids: set[str] = Field(default_factory=set)
    min_intervention_amount_inr: float = Field(default=50.0, ge=0)
    allow_human_escalation: bool = True

class FeatureSnapshot(BaseModel):
    snapshot_id: str
    payment_id: str
    features: dict[str, float]
    staleness_seconds: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)

class RecoveryExecution(BaseModel):
    execution_id: str
    decision_id: str
    payment_id: str
    order_id: str
    action: RecoveryAction
    status: ExecutionOutcome = ExecutionOutcome.PENDING
    dispatched_at: datetime = Field(default_factory=utcnow)
    completed_at: Optional[datetime] = None
    idempotency_key: str
    api_response: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None

class ModelVersion(BaseModel):
    version_id: str
    algorithm: str
    trained_at: datetime = Field(default_factory=utcnow)
    feature_names: list[str] = Field(default_factory=list)
    metrics_summary: dict[str, float] = Field(default_factory=dict)
    is_active: bool = True

class AuditEvent(BaseModel):
    audit_id: str
    event_type: str
    entity_id: str
    payload: dict[str, Any]
    timestamp: datetime = Field(default_factory=utcnow)
    actor: str = "system"

class WebhookEvent(BaseModel):
    event_id: str
    event_type: WebhookEventType
    payload_body: bytes
    signature: str
    received_at: datetime = Field(default_factory=utcnow)
    status: str = "received"
    rejection_reason: Optional[str] = None
