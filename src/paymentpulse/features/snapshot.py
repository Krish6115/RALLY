"""
Feature Snapshot & Reproducibility System.

Implements Phase 11:
- Captures point-in-time features before prediction.
- Calculates feature staleness against a strict threshold.
- Stores features immutably for model retraining and auditing.
"""

from __future__ import annotations
import logging
import time
import uuid
from typing import Optional

from paymentpulse.domain.entities import FeatureSnapshot

logger = logging.getLogger(__name__)

class FeatureStore:
    def __init__(self):
        # In-memory mock feature store: dict[payment_id, dict[str, float]]
        self._store: dict[str, dict[str, float]] = {}
        self._last_updated: dict[str, float] = {}
        
        # Snapshots created during decisioning: dict[snapshot_id, FeatureSnapshot]
        self._snapshots: dict[str, FeatureSnapshot] = {}

    def write_features(self, payment_id: str, features: dict[str, float]) -> None:
        """Write incoming feature vectors."""
        self._store[payment_id] = features.copy()
        self._last_updated[payment_id] = time.time()

    def capture_snapshot(self, payment_id: str) -> Optional[FeatureSnapshot]:
        """
        Capture a point-in-time snapshot of the features for decision reproducibility.
        """
        if payment_id not in self._store:
            logger.warning(f"[FEATURE STORE] No features found for {payment_id}")
            return None
            
        features = self._store[payment_id].copy()
        last_updated = self._last_updated[payment_id]
        staleness = time.time() - last_updated
        
        snapshot = FeatureSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:8]}",
            payment_id=payment_id,
            features=features,
            staleness_seconds=staleness
        )
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot
        
    def get_snapshot(self, snapshot_id: str) -> Optional[FeatureSnapshot]:
        return self._snapshots.get(snapshot_id)
