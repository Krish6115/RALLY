"""
Action executor — maps abstract RecoveryAction to concrete side effects.
"""

from __future__ import annotations

import logging
from typing import Optional, Any

from paymentpulse.domain.enums import RecoveryAction, DecisionRecord
from paymentpulse.execution.razorpay_client import RazorpayClient

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes decided actions via the Razorpay client."""

    def __init__(self, client: RazorpayClient):
        self.client = client

    def execute(
        self,
        decision: DecisionRecord,
        amount_inr: float,
        customer_contact: str = "+919876543210",  # Default for simulation
    ) -> dict[str, Any]:
        """
        Execute the final action from a decision record.

        Args:
            decision: The decision record output by the policy engine.
            amount_inr: The transaction amount.
            customer_contact: The customer's contact info.

        Returns:
            Dict containing execution results/metadata.
        """
        action = decision.final_action
        order_id = decision.order_id
        payment_id = decision.payment_id

        # Idempotency key derived deterministically from the decision
        idempotency_key = f"rec_{decision.event_id}"

        result = {
            "action_attempted": action.value,
            "success": True,
            "api_response": None,
            "error": None,
        }

        try:
            if action == RecoveryAction.DO_NOTHING:
                logger.info(f"Execution: No-op for payment {payment_id}")
                
            elif action == RecoveryAction.RETRY_NOW:
                # In a real integration, this might trigger a server-to-server retry
                # if the gateway supports it, or send a specific retry link.
                # Here we map it to sending a payment link.
                logger.info(f"Execution: Retrying payment {payment_id}")
                resp = self.client.send_payment_link(
                    order_id, amount_inr, customer_contact, idempotency_key
                )
                result["api_response"] = resp

            elif action in RecoveryAction.wait_actions():
                # Wait actions are handled by not doing anything side-effecting now,
                # but potentially enqueueing a background job.
                logger.info(f"Execution: Waiting ({action.value}) for {payment_id}")

            elif action == RecoveryAction.SWITCH_UPI_APP:
                logger.info(f"Execution: Sending switch-UPI link for {payment_id}")
                resp = self.client.send_payment_link(
                    order_id, amount_inr, customer_contact, idempotency_key,
                    method_hint="upi"
                )
                result["api_response"] = resp

            elif action == RecoveryAction.SWITCH_TO_CARD:
                logger.info(f"Execution: Sending switch-to-card link for {payment_id}")
                resp = self.client.send_payment_link(
                    order_id, amount_inr, customer_contact, idempotency_key,
                    method_hint="card"
                )
                result["api_response"] = resp

            elif action == RecoveryAction.SEND_PAYMENT_LINK:
                logger.info(f"Execution: Sending standard payment link for {payment_id}")
                resp = self.client.send_payment_link(
                    order_id, amount_inr, customer_contact, idempotency_key
                )
                result["api_response"] = resp

            elif action == RecoveryAction.ESCALATE_TO_HUMAN:
                # Log to escalation queue (no API call to Razorpay)
                logger.info(f"Execution: Escalating payment {payment_id} to human queue")

        except Exception as e:
            logger.error(f"Execution failed for {payment_id}: {e}")
            result["success"] = False
            result["error"] = str(e)

        return result
