"""Simulator package — latent-truth synthetic data generation."""

from .models import (
    PaymentMethod,
    ErrorSource,
    RecoveryAction,
    CustomerProfile,
    MerchantPolicy,
    FailureEvent,
    PaymentAttempt,
    DecisionRecord,
    ActionOutcome,
    EventContext,
)
from .generator import SyntheticDataGenerator, generate_batch
from .error_taxonomy import ERROR_CATALOG, ErrorCodeEntry

__all__ = [
    "PaymentMethod",
    "ErrorSource",
    "RecoveryAction",
    "PaymentAttempt",
    "CustomerProfile",
    "MerchantPolicy",
    "FailureEvent",
    "DecisionRecord",
    "ActionOutcome",
    "EventContext",
    "SyntheticDataGenerator",
    "generate_batch",
    "ERROR_CATALOG",
    "ErrorCodeEntry",
]
