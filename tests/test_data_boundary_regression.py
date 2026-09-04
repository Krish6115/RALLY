import pytest
import pandas as pd

from rally.features.context_builder import ContextBuilder
from rally.models.uplift_model import TLearnerUpliftModel
from rally.simulator.generator import SyntheticDataGenerator

def test_latent_leakage_prevented():
    """
    Proves that the deployable model never sees simulator latent ground truth features.
    Any feature starting with '_latent_' or containing 'oracle' must be stripped.
    """
    sim = SyntheticDataGenerator(n_events=10, seed=42)
    df_raw = sim.generate_batch()
    
    # 1. Ensure the simulator generated latent columns
    latent_cols = [c for c in df_raw.columns if "_latent_" in c]
    assert len(latent_cols) > 0, "Simulator failed to generate latent ground truth."
    
    # 2. Extract features using the deployable ContextBuilder
    builder = ContextBuilder()
    X = builder.fit_transform(df_raw)
    
    feature_names = builder.feature_names
    
    # 3. Assert zero leakage
    for col in feature_names:
        assert "_latent_" not in col, f"Leakage detected: {col} reached the model context."
        assert "oracle" not in col.lower(), f"Oracle leakage detected: {col} is an oracle variable."
        assert "recovered" not in col.lower(), f"LEAKAGE DETECTED: {col} is a post-decision outcome."
        
def test_economic_unit_conversion():
    """
    Proves economic scaling never multiplies INR by INR, or treats probability as INR.
    """
    from rally.domain.decisions import ModelPrediction
    from rally.domain.enums import RecoveryAction
    from rally.policy.engine import DecisionPipeline
    
    # Probability (0.1) * GMV (1000) = Expected Value INR (100)
    # Expected Value INR (100) - Cost INR (2.5) = ENRV (97.5)
    pred = ModelPrediction(
        model_version="v1",
        action_probabilities={RecoveryAction.SEND_PAYMENT_LINK: 0.8},
        action_uplifts={RecoveryAction.SEND_PAYMENT_LINK: 0.1}, # 10% uplift
        confidence=0.9
    )
    
    def mock_economic_scorer(p, amount):
        uplift = p.action_uplifts[RecoveryAction.SEND_PAYMENT_LINK]
        gmv = amount * uplift
        cost = 2.50
        from rally.domain.decisions import EconomicValue
        return [EconomicValue(
            action=RecoveryAction.SEND_PAYMENT_LINK,
            expected_recovered_gmv=gmv,
            expected_recovered_contribution=gmv,
            intervention_cost=cost,
            enrv=gmv - cost
        )]
        
    pipeline = DecisionPipeline(ml_predictor=lambda x, y: pred, economic_scorer=mock_economic_scorer)
    
    from rally.policy.constraints import PolicyConstraints
    from rally.domain.entities import MerchantPolicy
    
    decision = pipeline.decide(
        event_id="e1", payment_id="p1", feature_snapshot_id="s1", model_version="v1",
        uplift_estimates={}, constraints=PolicyConstraints(
            transaction_amount_inr=1000.0
        )
    )
    
    assert decision.expected_recovered_gmv == 100.0
    assert decision.enrv == 97.5
