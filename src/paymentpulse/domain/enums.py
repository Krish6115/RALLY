from __future__ import annotations
import enum

class PaymentMethod(str, enum.Enum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"

class ErrorSource(str, enum.Enum):
    CUSTOMER = "customer"
    BANK = "bank"
    GATEWAY = "gateway"
    RAZORPAY = "razorpay"
    NETWORK = "network"

class RecoveryAction(str, enum.Enum):
    DO_NOTHING = "do_nothing"
    RETRY_NOW = "retry_now"
    WAIT_2MIN = "wait_2min"
    WAIT_5MIN = "wait_5min"
    WAIT_10MIN = "wait_10min"
    SWITCH_UPI_APP = "switch_upi_app"
    SWITCH_TO_CARD = "switch_to_card"
    SEND_PAYMENT_LINK = "send_payment_link"
    ESCALATE_TO_HUMAN = "escalate_to_human"

    @classmethod
    def active_actions(cls) -> list[RecoveryAction]:
        return [a for a in cls if a != cls.DO_NOTHING]

    @classmethod
    def wait_actions(cls) -> list[RecoveryAction]:
        return [cls.WAIT_2MIN, cls.WAIT_5MIN, cls.WAIT_10MIN]

    @property
    def is_side_effecting(self) -> bool:
        return self in {
            RecoveryAction.RETRY_NOW,
            RecoveryAction.SEND_PAYMENT_LINK,
            RecoveryAction.SWITCH_UPI_APP,
            RecoveryAction.SWITCH_TO_CARD,
            RecoveryAction.ESCALATE_TO_HUMAN,
        }

class PaymentStatus(str, enum.Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"

class RecoveryState(str, enum.Enum):
    FAILED = "failed"
    RECOVERY_PENDING = "recovery_pending"
    RECOVERY_EXECUTING = "recovery_executing"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"
    TERMINATED = "terminated"

class ExecutionOutcome(str, enum.Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"

class DecisionReason(str, enum.Enum):
    MODEL_RECOMMENDATION = "model_recommendation"
    RULE_BASED_FALLBACK = "rule_based_fallback"
    SAFETY_VETO = "safety_veto"
    LOW_CONFIDENCE = "low_confidence"

class DegradedReason(str, enum.Enum):
    STALE_FEATURES = "stale_features"
    MODEL_ERROR = "model_error"
    INVALID_PREDICTION = "invalid_prediction"
    FEATURE_SCHEMA_MISMATCH = "feature_schema_mismatch"
    NONE = "none"

class WebhookEventType(str, enum.Enum):
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_FAILED = "payment.failed"
    ORDER_PAID = "order.paid"
