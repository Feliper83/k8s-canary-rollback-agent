"""The rollback/promote decision policy.

Pure function, no I/O, so it's trivial to unit test exhaustively -- this is
the piece that actually encodes "what counts as a regression" and deserves
the most scrutiny in review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .metrics import CanaryMetrics

Action = Literal["promote", "rollback"]


@dataclass(frozen=True)
class Thresholds:
    max_error_rate: float = 0.05
    """Hard ceiling on canary error rate, regardless of baseline."""

    max_error_rate_delta: float = 0.02
    """Canary error rate must not exceed baseline by more than this (absolute, e.g. 0.02 = 2pp)."""

    max_latency_ratio: float = 1.5
    """Canary p95 latency must not exceed baseline p95 latency by more than this multiple."""


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str


def decide(metrics: CanaryMetrics, thresholds: Thresholds = Thresholds()) -> Decision:
    if metrics.error_rate > thresholds.max_error_rate:
        return Decision(
            "rollback",
            f"canary error rate {metrics.error_rate:.1%} exceeds absolute ceiling "
            f"{thresholds.max_error_rate:.1%}",
        )

    delta = metrics.error_rate - metrics.baseline_error_rate
    if delta > thresholds.max_error_rate_delta:
        return Decision(
            "rollback",
            f"canary error rate {metrics.error_rate:.1%} exceeds baseline "
            f"{metrics.baseline_error_rate:.1%} by {delta:.1%}, over the "
            f"{thresholds.max_error_rate_delta:.1%} allowance",
        )

    if metrics.baseline_p95_latency_ms > 0:
        ratio = metrics.p95_latency_ms / metrics.baseline_p95_latency_ms
        if ratio > thresholds.max_latency_ratio:
            return Decision(
                "rollback",
                f"canary p95 latency {metrics.p95_latency_ms:.0f}ms is {ratio:.2f}x baseline "
                f"{metrics.baseline_p95_latency_ms:.0f}ms, over the {thresholds.max_latency_ratio:.2f}x allowance",
            )

    return Decision("promote", "all health gates passed")
