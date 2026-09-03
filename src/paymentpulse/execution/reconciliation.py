"""
Reconciliation Service for UNKNOWN Outcomes.

Implements Phase 9:
- Scans executions in UNKNOWN state.
- Polls live state fetcher.
- Reconciles state machine and idempotency records.
"""

from __future__ import annotations
import logging
from typing import Callable

from paymentpulse.safety.state_machine import PaymentStateMachine, RecoveryLifecycleState
from paymentpulse.safety.idempotency import IdempotencyStore

logger = logging.getLogger(__name__)

class ReconciliationService:
    def __init__(
        self,
        idempotency_store: IdempotencyStore,
        live_state_fetcher: Callable[[str], str]
    ):
        self.idempotency_store = idempotency_store
        self.live_state_fetcher = live_state_fetcher
        
    def reconcile(self, payment_id: str, state_machine: PaymentStateMachine) -> bool:
        """
        Attempt to resolve an UNKNOWN state by checking live source of truth.
        """
        if state_machine.recovery_state != RecoveryLifecycleState.UNKNOWN:
            logger.info(f"Payment {payment_id} is not in UNKNOWN state.")
            return False
            
        with self.idempotency_store.lock(payment_id):
            try:
                # Re-check state just in case it changed while acquiring lock
                if state_machine.recovery_state != RecoveryLifecycleState.UNKNOWN:
                    return False
                    
                live_status = self.live_state_fetcher(payment_id)
                logger.info(f"[RECONCILIATION] Fetched live status for {payment_id}: {live_status}")
                
                state_machine.reconcile_unknown(live_status)
                logger.info(f"[RECONCILIATION] Successfully reconciled {payment_id} -> {state_machine.recovery_state.value}")
                return True
                
            except Exception as e:
                logger.error(f"[RECONCILIATION] Failed to reconcile {payment_id}: {e}")
                return False
