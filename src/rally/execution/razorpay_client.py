"""
Thin wrapper around the official Razorpay Python SDK.

Includes a mock implementation for when test-mode API keys are not
available, ensuring the simulation and evaluation pipelines can run.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Any

import razorpay
from requests.exceptions import RequestException

from rally.config import RazorpayConfig

logger = logging.getLogger(__name__)


class RazorpayClient:
    """Wrapper around the Razorpay API."""

    def __init__(self, config: RazorpayConfig):
        self.config = config
        self.client = None
        if config.is_configured:
            self.client = razorpay.Client(
                auth=(config.key_id, config.key_secret)
            )

    @property
    def is_mock(self) -> bool:
        return self.client is None

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        """Fetch payment details from Razorpay."""
        if self.is_mock:
            return MockRazorpayClient.fetch_payment(payment_id)

        try:
            return self.client.payment.fetch(payment_id)
        except Exception as e:
            logger.error(f"Error fetching payment {payment_id}: {e}")
            raise

    def send_payment_link(
        self,
        order_id: str,
        amount_inr: float,
        customer_contact: str,
        idempotency_key: str,
        method_hint: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create and send a payment link."""
        if self.is_mock:
            return MockRazorpayClient.send_payment_link(
                order_id, amount_inr, customer_contact, idempotency_key, method_hint
            )

        amount_paise = int(amount_inr * 100)
        
        # In a real integration, we'd use idempotency headers.
        # The razorpay-python SDK doesn't natively expose headers in all methods,
        # but we simulate the payload.
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"Payment recovery for order {order_id}",
            "customer": {
                "contact": customer_contact
            },
            "notify": {
                "sms": True,
                "email": True
            },
            "reminder_enable": True,
            "notes": {
                "order_id": order_id,
                "idempotency_key": idempotency_key,
                "method_hint": method_hint or ""
            }
        }

        try:
            return self.client.payment_link.create(payload)
        except Exception as e:
            logger.error(f"Error creating payment link for {order_id}: {e}")
            raise

    def capture_payment(
        self,
        payment_id: str,
        amount_inr: float,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Capture an authorized payment."""
        if self.is_mock:
            return MockRazorpayClient.capture_payment(
                payment_id, amount_inr, idempotency_key
            )
            
        amount_paise = int(amount_inr * 100)
        
        try:
            return self.client.payment.capture(
                payment_id, amount_paise, {"currency": "INR"}
            )
        except Exception as e:
            logger.error(f"Error capturing payment {payment_id}: {e}")
            raise


class MockRazorpayClient:
    """Mock implementation for testing without API keys."""

    @staticmethod
    def fetch_payment(payment_id: str) -> dict[str, Any]:
        logger.debug(f"[MOCK] Fetching payment {payment_id}")
        return {
            "id": payment_id,
            "entity": "payment",
            "amount": 50000,
            "currency": "INR",
            "status": "failed",
            "order_id": f"order_{uuid.uuid4().hex[:12]}",
            "method": "upi",
            "error_code": "BAD_REQUEST_PAYMENT_TIMED_OUT",
        }

    @staticmethod
    def send_payment_link(
        order_id: str,
        amount_inr: float,
        customer_contact: str,
        idempotency_key: str,
        method_hint: Optional[str] = None,
    ) -> dict[str, Any]:
        logger.info(
            f"[MOCK] Creating payment link for order {order_id}, "
            f"amount {amount_inr} INR to {customer_contact} "
            f"(idempotency: {idempotency_key})"
        )
        return {
            "id": f"plink_{uuid.uuid4().hex[:12]}",
            "entity": "payment_link",
            "amount": int(amount_inr * 100),
            "currency": "INR",
            "status": "created",
            "short_url": f"https://rzp.io/i/{uuid.uuid4().hex[:6]}",
        }

    @staticmethod
    def capture_payment(
        payment_id: str,
        amount_inr: float,
        idempotency_key: str,
    ) -> dict[str, Any]:
        logger.info(
            f"[MOCK] Capturing payment {payment_id} for "
            f"amount {amount_inr} INR (idempotency: {idempotency_key})"
        )
        return {
            "id": payment_id,
            "entity": "payment",
            "amount": int(amount_inr * 100),
            "currency": "INR",
            "status": "captured",
        }
