"""
Hard constraint definitions for the policy engine.

These are merchant-configurable rules that the policy engine enforces
independently of the ML model. The model ranks among already-legal
options; it never gets to propose an illegal one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from paymentpulse.domain.enums import RecoveryAction, PaymentMethod


@dataclass
class PolicyConstraints:
    """
    Complete constraint specification for a single decision.

    Built from MerchantPolicy + runtime context (session state,
    attempt history, etc.).
    """

    # Hard limits
    max_retries_remaining: int = 3
    session_time_remaining_seconds: float = 900.0  # 15 min default
    nudges_remaining_today: int = 3
    min_intervention_amount_inr: float = 50.0
    transaction_amount_inr: float = 0.0

    # Opt-out
    customer_opted_out: bool = False

    # Allowed methods/channels
    allowed_methods: set[PaymentMethod] = field(
        default_factory=lambda: set(PaymentMethod)
    )
    allowed_channels: set[str] = field(
        default_factory=lambda: {"sms", "whatsapp", "email"}
    )
    allow_human_escalation: bool = True

    # Cooldown
    seconds_since_last_action: Optional[float] = None
    cooldown_seconds: float = 30.0

    # Payment state (the critical one)
    payment_already_succeeded: bool = False
    payment_already_captured: bool = False
    order_already_paid: bool = False

    def get_legal_actions(self) -> list[RecoveryAction]:
        """
        Compute the set of legal actions given all constraints.

        This is the PRE-FILTER: the ML model only ever ranks among
        the actions returned by this method.
        """
        # UNCONDITIONAL STOP — the governing invariant
        if self.payment_already_succeeded or self.payment_already_captured or self.order_already_paid:
            return [RecoveryAction.DO_NOTHING]

        # Customer opted out
        if self.customer_opted_out:
            return [RecoveryAction.DO_NOTHING]

        legal = [RecoveryAction.DO_NOTHING]  # Always available

        # Amount threshold
        below_threshold = (
            self.transaction_amount_inr < self.min_intervention_amount_inr
        )

        # Cooldown check
        in_cooldown = (
            self.seconds_since_last_action is not None and
            self.seconds_since_last_action < self.cooldown_seconds
        )
        if in_cooldown:
            # During cooldown, only wait actions are allowed
            if self.session_time_remaining_seconds > 120:
                legal.append(RecoveryAction.WAIT_2MIN)
            return legal

        # Retry (if retries remaining)
        if self.max_retries_remaining > 0:
            legal.append(RecoveryAction.RETRY_NOW)

        # Wait actions (if session has time)
        if self.session_time_remaining_seconds > 120:
            legal.append(RecoveryAction.WAIT_2MIN)
        if self.session_time_remaining_seconds > 300:
            legal.append(RecoveryAction.WAIT_5MIN)
        if self.session_time_remaining_seconds > 600:
            legal.append(RecoveryAction.WAIT_10MIN)

        # Method switch (if method is allowed)
        if PaymentMethod.UPI in self.allowed_methods and not below_threshold:
            legal.append(RecoveryAction.SWITCH_UPI_APP)
        if PaymentMethod.CARD in self.allowed_methods and not below_threshold:
            legal.append(RecoveryAction.SWITCH_TO_CARD)

        # Payment link (needs a channel and nudge budget)
        if (
            self.allowed_channels and
            self.nudges_remaining_today > 0 and
            not below_threshold
        ):
            legal.append(RecoveryAction.SEND_PAYMENT_LINK)

        # Human escalation
        if self.allow_human_escalation and not below_threshold:
            legal.append(RecoveryAction.ESCALATE_TO_HUMAN)

        return legal

    def validate_action(self, action: RecoveryAction) -> tuple[bool, str]:
        """
        Validate that a specific action is legal.

        Returns:
            (is_legal, reason_if_not)
        """
        legal = self.get_legal_actions()
        if action in legal:
            return True, ""

        # Specific rejection reasons
        if self.payment_already_succeeded or self.payment_already_captured:
            return False, "PAYMENT_ALREADY_SUCCEEDED"
        if self.customer_opted_out:
            return False, "CUSTOMER_OPTED_OUT"
        if action == RecoveryAction.RETRY_NOW and self.max_retries_remaining <= 0:
            return False, "MAX_RETRIES_EXCEEDED"
        if action == RecoveryAction.SEND_PAYMENT_LINK and self.nudges_remaining_today <= 0:
            return False, "NUDGE_CAP_EXCEEDED"
        if action in RecoveryAction.wait_actions():
            return False, "INSUFFICIENT_SESSION_TIME"

        return False, "ACTION_NOT_ALLOWED"
