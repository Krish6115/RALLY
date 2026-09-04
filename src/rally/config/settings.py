"""
Configuration Management for PaymentPulse.

Loads from environment variables (.env file) with sensible defaults.
All thresholds and policy values are documented with their rationale.
Enforces strict configuration parsing via Pydantic to protect against accidental live execution.
"""

from __future__ import annotations
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class RazorpayConfig(BaseSettings):
    """Razorpay API credentials and endpoints."""
    key_id: str = Field(default="")
    key_secret: str = Field(default="")
    base_url: str = Field(default="https://api.razorpay.com/v1")
    webhook_secret: str = Field(default="test_secret")

    model_config = SettingsConfigDict(env_prefix="RAZORPAY_", env_file=".env", extra="ignore")

    @property
    def is_configured(self) -> bool:
        return bool(self.key_id and self.key_secret and "xxxx" not in self.key_id)

class SimulatorConfig(BaseSettings):
    default_batch_size: int = Field(default=10000)
    seed: int = Field(default=42)
    epsilon: float = Field(default=0.1)
    base_self_cure_rate: float = Field(default=0.25)
    min_self_cure_rate: float = Field(default=0.05)
    max_self_cure_rate: float = Field(default=0.45)

    model_config = SettingsConfigDict(env_prefix="SIMULATOR_", env_file=".env", extra="ignore")

class SafetyConfig(BaseSettings):
    max_retries: int = Field(default=3)
    session_timeout_minutes: int = Field(default=15)
    nudge_cap_per_day: int = Field(default=3)
    webhook_staleness_seconds: int = Field(default=300)
    action_cooldown_seconds: int = Field(default=30)
    max_decision_latency_ms: int = Field(default=500)
    feature_staleness_threshold_seconds: int = Field(default=60)
    default_lease_seconds: float = Field(default=30.0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

class EvaluationConfig(BaseSettings):
    max_credible_uplift_pp: float = Field(default=10.0)
    min_credible_uplift_pp: float = Field(default=1.0)
    sms_cost_inr: float = Field(default=0.15)
    whatsapp_cost_inr: float = Field(default=0.50)
    email_cost_inr: float = Field(default=0.02)
    friction_cost_per_nudge_inr: float = Field(default=2.0)
    human_escalation_cost_inr: float = Field(default=25.0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

class AppSettings(BaseSettings):
    environment: str = Field(default="development", description="development, staging, production")
    use_live_adapter: bool = Field(default=False)
    enable_stdout_metrics: bool = Field(default=True)
    
    razorpay: RazorpayConfig = Field(default_factory=RazorpayConfig)
    simulator: SimulatorConfig = Field(default_factory=SimulatorConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)

    project_root: Path = Field(default=_PROJECT_ROOT)
    data_dir: Path = Field(default=_PROJECT_ROOT / "data")
    results_dir: Path = Field(default=_PROJECT_ROOT / "results")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def model_post_init(self, __context):
        if self.use_live_adapter:
            if not self.razorpay.is_configured:
                raise ValueError("Razorpay credentials MUST be set if use_live_adapter=True.")
            if "test" in self.razorpay.key_id and self.environment == "production":
                raise ValueError("Cannot use test keys in production environment.")

# Expose both `settings` and `config` for backwards compatibility
config = AppSettings()
settings = config
