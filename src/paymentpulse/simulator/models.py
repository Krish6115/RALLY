"""
Core data models for PaymentPulse.

These Pydantic models define the schema for every data structure that flows
through the system. The key design principle: latent customer/environment
state (which drives the simulator's ground truth) is kept separate from
observable features (which is all the ML model ever sees).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field



from paymentpulse.domain.enums import (
    PaymentMethod, ErrorSource, RecoveryAction, PaymentStatus,
    ExecutionOutcome
)
from paymentpulse.domain.entities import (
    MerchantPolicy
)

class CustomerProfile(BaseModel):
    """
    LATENT customer state — drives simulator ground truth.
    The ML model NEVER sees these fields directly; it only sees their
    noisy effects through observable features (error codes, attempt history, etc.).
    This separation is the anti-leakage design (Section H of research doc).
    """
    customer_id: str
    self_cure_propensity: float = Field(ge=0.0, le=1.0)
    nudge_responsiveness: float = Field(ge=0.0, le=1.0)
    method_switch_willingness: float = Field(ge=0.0, le=1.0)
    fatigue_rate: float = Field(ge=0.0, le=1.0)
    purchase_intent: float = Field(ge=0.0, le=1.0)

class FailureEvent(BaseModel):
    attempt: PaymentAttempt
    customer: CustomerProfile
    merchant_policy: MerchantPolicy
    is_gateway_down: bool
    is_bank_down: bool
    downtime_severity: float
    prior_attempts_this_session: int
    time_since_session_start_seconds: float

class PaymentAttempt(BaseModel):
    payment_id: str
    order_id: str
    session_id: str
    amount_inr: float
    method: PaymentMethod
    instrument: str
    error_code: str
    error_source: ErrorSource
    error_description: str = ""
    attempt_number: int
    timestamp: datetime
    session_start: datetime

class DecisionRecord(BaseModel):
    decision_id: str
    payment_id: str
    features: dict[str, float]
    predicted_uplifts: dict[str, float]
    selected_action: str
    timestamp: datetime
    is_random_exploration: bool = False

class ActionOutcome(BaseModel):
    outcome_id: str
    decision_id: str
    payment_id: str
    action: str
    execution_status: ExecutionOutcome
    recovered_amount_inr: float = 0.0
    timestamp: datetime

class EventContext(BaseModel):
    """
    The unit of analysis: one (order_id, payment_attempt_id) failure event.
    This is the input to the decision pipeline.
    """
    attempt: PaymentAttempt
    customer: CustomerProfile
    merchant_policy: MerchantPolicy
    is_gateway_down: bool = False
    is_bank_down: bool = False
    downtime_severity: float = Field(default=0.0, ge=0.0, le=1.0)
    prior_attempts_this_session: int = Field(default=0, ge=0)
    prior_recoveries_this_session: int = Field(default=0, ge=0)
    time_since_session_start_seconds: float = Field(default=0.0, ge=0.0)
