"""
Gateway/bank downtime signal simulator.

Simulates the effect of Razorpay's Downtime API — near-real-time detection
of bank/gateway degradation that affects payment success rates.

In production, Razorpay refreshes downtime status every ~5 minutes. In the
simulator, downtime windows are pre-generated and affect:
1. Self-cure rates (lower during downtime — bank can't process)
2. Treatment effects (wait actions become more valuable during downtime,
   retry becomes less valuable, switch becomes most valuable)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class DowntimeWindow:
    """A period of degradation for a specific provider."""
    provider_type: str  # "bank" or "gateway"
    provider_name: str  # e.g., "SBI", "HDFC", "payu", "razorpay_gateway"
    start_hour: float  # Hour of day (0-24, fractional)
    duration_hours: float
    severity: float  # 0.0 (minor degradation) to 1.0 (complete outage)


class DowntimeSimulator:
    """
    Generates and queries simulated downtime windows.

    Design: downtime windows are pre-generated per simulation run so that
    the same seed produces identical downtime patterns. This ensures
    reproducibility across evaluation runs.
    """

    # Major Indian banks and common UPI PSPs
    BANKS = ["SBI", "HDFC", "ICICI", "AXIS", "PNB", "BOB", "KOTAK", "YES"]
    GATEWAYS = ["razorpay_pg", "payu", "ccavenue", "billdesk"]

    def __init__(self, rng: np.random.Generator, downtime_probability: float = 0.15):
        """
        Args:
            rng: NumPy random generator for reproducibility.
            downtime_probability: Probability that any given provider is experiencing
                downtime at any random point in time. Default 0.15 (15%) is
                deliberately high to generate enough downtime-affected events
                for the model to learn from — in production, actual downtime
                rates are lower.
        """
        self.rng = rng
        self.downtime_probability = downtime_probability
        self.windows: list[DowntimeWindow] = []
        self._generate_windows()

    def _generate_windows(self) -> None:
        """Generate downtime windows for a simulated 24-hour period."""
        for bank in self.BANKS:
            # Each bank has a chance of having 0-2 downtime windows per day
            n_windows = self.rng.poisson(lam=0.3)
            for _ in range(n_windows):
                self.windows.append(DowntimeWindow(
                    provider_type="bank",
                    provider_name=bank,
                    start_hour=self.rng.uniform(0, 24),
                    duration_hours=self.rng.exponential(scale=0.5),  # ~30 min average
                    severity=self.rng.beta(2, 5),  # Skewed toward lower severity
                ))

        for gw in self.GATEWAYS:
            n_windows = self.rng.poisson(lam=0.1)  # Gateways have less downtime
            for _ in range(n_windows):
                self.windows.append(DowntimeWindow(
                    provider_type="gateway",
                    provider_name=gw,
                    start_hour=self.rng.uniform(0, 24),
                    duration_hours=self.rng.exponential(scale=0.3),
                    severity=self.rng.beta(2, 8),
                ))

    def check_downtime(
        self,
        provider_name: str,
        hour_of_day: float,
    ) -> tuple[bool, float]:
        """
        Check if a provider is experiencing downtime at a given time.

        Returns:
            (is_down, severity) — severity is 0.0 if not down.
        """
        for w in self.windows:
            if w.provider_name != provider_name:
                continue
            end_hour = w.start_hour + w.duration_hours
            # Handle wrap-around midnight
            if w.start_hour <= hour_of_day < end_hour:
                return True, w.severity
            if end_hour > 24 and hour_of_day < (end_hour - 24):
                return True, w.severity
        return False, 0.0

    def get_downtime_modifier(
        self,
        provider_name: str,
        hour_of_day: float,
    ) -> dict[str, float]:
        """
        Get modifiers for self-cure rate and treatment effects during downtime.

        During downtime:
        - Self-cure rate drops (bank can't process retries)
        - Retry uplift drops (same bank, same problem)
        - Wait uplift increases (downtime may resolve)
        - Switch uplift increases (different provider may work)
        """
        is_down, severity = self.check_downtime(provider_name, hour_of_day)

        if not is_down:
            return {
                "self_cure_multiplier": 1.0,
                "retry_multiplier": 1.0,
                "wait_multiplier": 1.0,
                "switch_multiplier": 1.0,
            }

        return {
            "self_cure_multiplier": max(0.1, 1.0 - severity * 0.8),
            "retry_multiplier": max(0.05, 1.0 - severity * 0.9),
            "wait_multiplier": 1.0 + severity * 0.5,  # Wait becomes more valuable
            "switch_multiplier": 1.0 + severity * 0.8,  # Switch becomes most valuable
        }
