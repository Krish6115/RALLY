"""
Razorpay error code taxonomy — faithful reproduction.

Every error code is mapped to:
- Error source (customer / bank / gateway / razorpay / network)
- Recommended next step (from Razorpay's own docs)
- Simulated self-cure probability range (calibrated to published data)
- Simulated treatment-effect profile per action type

This is the foundation for both Baseline 3 (rule-based recovery, which
follows Razorpay's published guidance exactly) and the simulator's
ground-truth model (which uses these profiles to generate realistic
recovery outcomes).

Sources:
- Razorpay Error Codes documentation
- Razorpay "Rainy Day" / payment error classification
- NPCI UPI decline code categories (TD/BD split)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import ErrorSource, RecoveryAction, PaymentMethod


@dataclass(frozen=True)
class TreatmentProfile:
    """
    Expected treatment effect (uplift) for a given action on this error type.
    Values are additive probabilities on top of the self-cure base rate.
    Range: [0.0, ~0.3] — calibrated so total P(recover) stays realistic.
    """
    retry_now: float = 0.0
    wait_short: float = 0.0  # wait_2min
    wait_medium: float = 0.0  # wait_5min
    wait_long: float = 0.0  # wait_10min
    switch_upi_app: float = 0.0
    switch_to_card: float = 0.0
    send_payment_link: float = 0.0
    escalate_to_human: float = 0.0

    def get(self, action: RecoveryAction) -> float:
        """Get treatment effect for a specific action."""
        mapping = {
            RecoveryAction.RETRY_NOW: self.retry_now,
            RecoveryAction.WAIT_2MIN: self.wait_short,
            RecoveryAction.WAIT_5MIN: self.wait_medium,
            RecoveryAction.WAIT_10MIN: self.wait_long,
            RecoveryAction.SWITCH_UPI_APP: self.switch_upi_app,
            RecoveryAction.SWITCH_TO_CARD: self.switch_to_card,
            RecoveryAction.SEND_PAYMENT_LINK: self.send_payment_link,
            RecoveryAction.ESCALATE_TO_HUMAN: self.escalate_to_human,
            RecoveryAction.DO_NOTHING: 0.0,
        }
        return mapping.get(action, 0.0)


@dataclass(frozen=True)
class ErrorCodeEntry:
    """One entry in the error catalog."""
    code: str
    description: str
    source: ErrorSource
    # Which payment methods this error applies to
    applicable_methods: list[PaymentMethod] = field(
        default_factory=lambda: list(PaymentMethod)
    )
    # Razorpay's documented recommended next step
    razorpay_recommended_action: str = ""
    # For Baseline 3 (rule-based): what action should the rule-based system pick?
    rule_based_action: RecoveryAction = RecoveryAction.SEND_PAYMENT_LINK
    # Simulator ground truth
    base_self_cure_rate: float = 0.20
    treatment_profile: TreatmentProfile = field(default_factory=TreatmentProfile)
    # Relative frequency (unnormalized weight for sampling)
    frequency_weight: float = 1.0


# ---------------------------------------------------------------------------
# The catalog — built from Razorpay's published error code documentation
# ---------------------------------------------------------------------------

ERROR_CATALOG: list[ErrorCodeEntry] = [
    # ========== CUSTOMER-SIDE ERRORS ==========
    ErrorCodeEntry(
        code="BAD_REQUEST_PAYMENT_TIMED_OUT",
        description="Customer did not complete the payment within the allowed time",
        source=ErrorSource.CUSTOMER,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING],
        razorpay_recommended_action="Send payment link to retry",
        rule_based_action=RecoveryAction.SEND_PAYMENT_LINK,
        base_self_cure_rate=0.30,  # High — customer may just retry on their own
        treatment_profile=TreatmentProfile(
            retry_now=0.05,
            wait_short=0.08,
            wait_medium=0.12,
            wait_long=0.10,
            switch_upi_app=0.02,
            switch_to_card=0.03,
            send_payment_link=0.15,  # Strong — gives them a fresh start
            escalate_to_human=0.05,
        ),
        frequency_weight=4.0,  # Very common
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_PAYMENT_CANCELLED",
        description="Customer cancelled the payment explicitly",
        source=ErrorSource.CUSTOMER,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD],
        razorpay_recommended_action="Send payment link",
        rule_based_action=RecoveryAction.SEND_PAYMENT_LINK,
        base_self_cure_rate=0.15,  # Lower — they chose to cancel
        treatment_profile=TreatmentProfile(
            retry_now=0.02,  # They just cancelled — retrying immediately is annoying
            wait_short=0.05,
            wait_medium=0.08,
            wait_long=0.06,
            send_payment_link=0.10,
            escalate_to_human=0.03,
        ),
        frequency_weight=2.0,
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_UPI_INVALID_PIN",
        description="Customer entered wrong UPI PIN",
        source=ErrorSource.CUSTOMER,
        applicable_methods=[PaymentMethod.UPI],
        razorpay_recommended_action="Retry with correct PIN",
        rule_based_action=RecoveryAction.RETRY_NOW,
        base_self_cure_rate=0.35,  # High — simple typo, they know to retry
        treatment_profile=TreatmentProfile(
            retry_now=0.15,  # Strong — just needs another attempt
            wait_short=0.10,
            send_payment_link=0.08,
        ),
        frequency_weight=3.0,
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_INSUFFICIENT_FUNDS",
        description="Customer has insufficient balance in their account",
        source=ErrorSource.CUSTOMER,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.WALLET],
        razorpay_recommended_action="Use different payment method or add funds",
        rule_based_action=RecoveryAction.SWITCH_TO_CARD,
        base_self_cure_rate=0.08,  # Low — they don't have money, need to switch
        treatment_profile=TreatmentProfile(
            retry_now=0.01,  # Won't help — same account, same balance
            switch_upi_app=0.06,  # Might have balance in different bank
            switch_to_card=0.12,  # Credit card doesn't need balance
            send_payment_link=0.08,  # Gives time to add funds or pick method
            wait_long=0.05,  # Might get a transfer in
            escalate_to_human=0.02,
        ),
        frequency_weight=3.5,
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_CARD_DECLINED",
        description="Card was declined by the issuing bank",
        source=ErrorSource.CUSTOMER,
        applicable_methods=[PaymentMethod.CARD],
        razorpay_recommended_action="Try different card or payment method",
        rule_based_action=RecoveryAction.SEND_PAYMENT_LINK,
        base_self_cure_rate=0.10,
        treatment_profile=TreatmentProfile(
            retry_now=0.02,
            switch_to_card=0.08,  # Different card might work
            switch_upi_app=0.10,  # UPI from a different account
            send_payment_link=0.12,
            escalate_to_human=0.04,
        ),
        frequency_weight=2.5,
    ),

    # ========== BANK-SIDE ERRORS ==========
    ErrorCodeEntry(
        code="GATEWAY_ERROR_BANK_OFFLINE",
        description="Issuing bank's systems are unavailable",
        source=ErrorSource.BANK,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING],
        razorpay_recommended_action="Wait and retry, or switch bank/method",
        rule_based_action=RecoveryAction.WAIT_5MIN,
        base_self_cure_rate=0.15,
        treatment_profile=TreatmentProfile(
            retry_now=0.01,  # Bank is down — retry won't help
            wait_short=0.05,
            wait_medium=0.15,  # Give bank time to come back
            wait_long=0.18,  # Even better
            switch_upi_app=0.12,  # Different bank's UPI
            switch_to_card=0.10,  # Different issuer
            send_payment_link=0.08,
            escalate_to_human=0.03,
        ),
        frequency_weight=2.0,
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_UPI_TRANSACTION_LIMIT_EXCEEDED",
        description="Customer's UPI transaction limit exceeded for the day/period",
        source=ErrorSource.BANK,
        applicable_methods=[PaymentMethod.UPI],
        razorpay_recommended_action="Switch to card or try tomorrow",
        rule_based_action=RecoveryAction.SWITCH_TO_CARD,
        base_self_cure_rate=0.05,  # Very low — limit won't reset soon
        treatment_profile=TreatmentProfile(
            retry_now=0.00,  # Definitely won't help
            switch_upi_app=0.04,  # Different bank might have different limit
            switch_to_card=0.18,  # Best option — card has separate limit
            send_payment_link=0.10,  # Gives option to pick card
            escalate_to_human=0.02,
        ),
        frequency_weight=1.5,
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_UPI_MANDATE_REJECTED",
        description="UPI mandate/collect request rejected by the bank",
        source=ErrorSource.BANK,
        applicable_methods=[PaymentMethod.UPI],
        razorpay_recommended_action="Retry or use different UPI app",
        rule_based_action=RecoveryAction.RETRY_NOW,
        base_self_cure_rate=0.20,
        treatment_profile=TreatmentProfile(
            retry_now=0.10,
            wait_short=0.08,
            switch_upi_app=0.12,
            send_payment_link=0.10,
        ),
        frequency_weight=1.5,
    ),

    # ========== GATEWAY-SIDE ERRORS ==========
    ErrorCodeEntry(
        code="GATEWAY_ERROR",
        description="Payment gateway returned an error",
        source=ErrorSource.GATEWAY,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING],
        razorpay_recommended_action="Retry; if persistent, contact support",
        rule_based_action=RecoveryAction.RETRY_NOW,
        base_self_cure_rate=0.18,
        treatment_profile=TreatmentProfile(
            retry_now=0.12,  # Often transient — retry works
            wait_short=0.10,
            wait_medium=0.08,
            switch_to_card=0.06,
            send_payment_link=0.08,
        ),
        frequency_weight=2.5,
    ),
    ErrorCodeEntry(
        code="GATEWAY_ERROR_REQUEST_TIMEOUT",
        description="Gateway request timed out",
        source=ErrorSource.GATEWAY,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD],
        razorpay_recommended_action="Retry after a short wait",
        rule_based_action=RecoveryAction.WAIT_2MIN,
        base_self_cure_rate=0.22,
        treatment_profile=TreatmentProfile(
            retry_now=0.08,
            wait_short=0.14,  # Timeout often clears quickly
            wait_medium=0.12,
            send_payment_link=0.06,
        ),
        frequency_weight=2.0,
    ),
    ErrorCodeEntry(
        code="GATEWAY_ERROR_FATAL",
        description="Fatal gateway error — payment cannot proceed via this route",
        source=ErrorSource.GATEWAY,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD],
        razorpay_recommended_action="Switch payment method or gateway",
        rule_based_action=RecoveryAction.SWITCH_TO_CARD,
        base_self_cure_rate=0.05,
        treatment_profile=TreatmentProfile(
            retry_now=0.01,  # Same route will fail again
            switch_upi_app=0.10,
            switch_to_card=0.15,
            send_payment_link=0.12,
            escalate_to_human=0.06,
        ),
        frequency_weight=1.0,
    ),

    # ========== NETWORK-SIDE ERRORS ==========
    ErrorCodeEntry(
        code="BAD_REQUEST_PAYMENT_NETWORK_ERROR",
        description="Network connectivity issue during payment",
        source=ErrorSource.NETWORK,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING],
        razorpay_recommended_action="Retry",
        rule_based_action=RecoveryAction.RETRY_NOW,
        base_self_cure_rate=0.28,  # Transient — often resolves on its own
        treatment_profile=TreatmentProfile(
            retry_now=0.12,
            wait_short=0.15,
            wait_medium=0.10,
            send_payment_link=0.08,
        ),
        frequency_weight=2.0,
    ),

    # ========== RAZORPAY-SIDE ERRORS ==========
    ErrorCodeEntry(
        code="SERVER_ERROR_INTERNAL",
        description="Internal server error on Razorpay's side",
        source=ErrorSource.RAZORPAY,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD, PaymentMethod.NETBANKING],
        razorpay_recommended_action="Automatic retry by Razorpay",
        rule_based_action=RecoveryAction.WAIT_2MIN,
        base_self_cure_rate=0.25,
        treatment_profile=TreatmentProfile(
            retry_now=0.08,
            wait_short=0.15,  # Razorpay fixes fast
            wait_medium=0.12,
            send_payment_link=0.05,
        ),
        frequency_weight=0.5,  # Rare
    ),

    # ========== UPI-SPECIFIC ERRORS ==========
    ErrorCodeEntry(
        code="BAD_REQUEST_UPI_PSP_NOT_AVAILABLE",
        description="UPI PSP (payment service provider / app) unavailable",
        source=ErrorSource.GATEWAY,
        applicable_methods=[PaymentMethod.UPI],
        razorpay_recommended_action="Switch UPI app",
        rule_based_action=RecoveryAction.SWITCH_UPI_APP,
        base_self_cure_rate=0.12,
        treatment_profile=TreatmentProfile(
            retry_now=0.02,
            switch_upi_app=0.20,  # Very effective — different PSP might work
            switch_to_card=0.12,
            send_payment_link=0.10,
            wait_medium=0.08,
        ),
        frequency_weight=1.5,
    ),
    ErrorCodeEntry(
        code="BAD_REQUEST_UPI_TRANSACTION_PENDING",
        description="A previous UPI transaction is still pending",
        source=ErrorSource.BANK,
        applicable_methods=[PaymentMethod.UPI],
        razorpay_recommended_action="Wait for pending transaction to resolve",
        rule_based_action=RecoveryAction.WAIT_5MIN,
        base_self_cure_rate=0.35,  # High — pending transaction will clear
        treatment_profile=TreatmentProfile(
            retry_now=0.01,  # Won't help — transaction still pending
            wait_short=0.08,
            wait_medium=0.18,  # Good chance it clears
            wait_long=0.20,
            send_payment_link=0.05,
            switch_to_card=0.10,
        ),
        frequency_weight=1.5,
    ),

    # ========== FRAUD / RISK ERRORS ==========
    ErrorCodeEntry(
        code="BAD_REQUEST_PAYMENT_DECLINED_BY_RISK",
        description="Payment declined by risk/fraud detection system",
        source=ErrorSource.RAZORPAY,
        applicable_methods=[PaymentMethod.UPI, PaymentMethod.CARD],
        razorpay_recommended_action="Do not retry — risk flag should be reviewed",
        rule_based_action=RecoveryAction.DO_NOTHING,
        base_self_cure_rate=0.02,  # Almost never self-cures — risk flag sticks
        treatment_profile=TreatmentProfile(
            # Everything is near-zero — this is a legitimate block
            retry_now=0.01,
            escalate_to_human=0.05,
        ),
        frequency_weight=0.5,
    ),
]


def get_error_by_code(code: str) -> ErrorCodeEntry | None:
    """Look up an error code entry."""
    for entry in ERROR_CATALOG:
        if entry.code == code:
            return entry
    return None


def get_errors_by_source(source: ErrorSource) -> list[ErrorCodeEntry]:
    """Get all error codes from a given source."""
    return [e for e in ERROR_CATALOG if e.source == source]


def get_errors_for_method(method: PaymentMethod) -> list[ErrorCodeEntry]:
    """Get all error codes applicable to a payment method."""
    return [e for e in ERROR_CATALOG if method in e.applicable_methods]
