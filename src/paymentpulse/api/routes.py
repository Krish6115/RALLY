"""
PaymentPulse API Contract (Phase 18).

Exposes:
1. POST /webhooks/razorpay (Ingestion of events)
2. POST /decisions (Explicit triggering of recovery evaluation)
3. GET /health (Healthcheck)
"""

from fastapi import APIRouter, Header, Request, HTTPException
from pydantic import BaseModel
import logging

from paymentpulse.api.webhooks import WebhookReceiver
from paymentpulse.domain.entities import WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter()

# In a real app, this would be injected via FastAPI dependencies
receiver: WebhookReceiver = None 

class DecisionRequest(BaseModel):
    payment_id: str
    order_id: str
    amount_inr: float
    error_code: str
    merchant_id: str

@router.post("/webhooks/razorpay")
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(...)
):
    """
    Ingest webhook securely.
    """
    body = await request.body()
    # Mocking event parsing from body for demo contract
    event_id = "evt_mock" 
    event_type = "payment.failed"
    timestamp = 1600000000
    
    if receiver:
        evt: WebhookEvent = receiver.process_incoming(
            event_id=event_id,
            event_type_str=event_type,
            payload_body=body,
            signature=x_razorpay_signature,
            created_at_timestamp=timestamp
        )
        if evt.status == "rejected":
            logger.warning(f"Webhook rejected: {evt.rejection_reason}")
            raise HTTPException(status_code=400, detail="Invalid webhook")
            
        logger.info(f"Webhook accepted: {evt.event_type.value}")
        # Next step: put onto internal Kafka/PubSub or directly to RecoveryCoordinator
        
    return {"status": "ok"}

@router.post("/decisions")
async def trigger_decision(req: DecisionRequest):
    """
    Manually trigger the recovery pipeline.
    """
    logger.info(f"Received manual decision request for {req.payment_id}")
    return {"status": "accepted", "payment_id": req.payment_id}

@router.get("/health")
async def health_check():
    return {"status": "healthy"}
