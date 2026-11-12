"""Fetch canary vs. baseline health signals for one rollout stage.

Live mode queries Prometheus directly (error rate and p95 latency, both
scoped by an `app` label to the canary and stable deployments). Mock mode
replays one of two deterministic scenarios so the agent is demoable --
and its decision logic testable -- without a real cluster:

- "healthy": canary tracks the stable baseline closely at every stage;
  the rollout should reach 100%.
- "regression": the canary looks fine for the first two stages, then its
  error rate spikes at stage index 2 (the 50% stage); the rollout should
  auto-rollback right there instead of reaching 100%.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CanaryMetrics:
    error_rate: float
    p95_latency_ms: float
    baseline_error_rate: float
    baseline_p95_latency_ms: float


# stage_index -> CanaryMetrics, keyed by scenario name.
_MOCK_SCENARIOS: dict[str, dict[int, CanaryMetrics]] = {
    "healthy": {
        0: CanaryMetrics(error_rate=0.011, p95_latency_ms=188, baseline_error_rate=0.010, baseline_p95_latency_ms=182),
        1: CanaryMetrics(error_rate=0.012, p95_latency_ms=190, baseline_error_rate=0.010, baseline_p95_latency_ms=181),
        2: CanaryMetrics(error_rate=0.010, p95_latency_ms=179, baseline_error_rate=0.011, baseline_p95_latency_ms=183),
        3: CanaryMetrics(error_rate=0.009, p95_latency_ms=177, baseline_error_rate=0.010, baseline_p95_latency_ms=180),
    },
    "regression": {
        0: CanaryMetrics(error_rate=0.011, p95_latency_ms=186, baseline_error_rate=0.010, baseline_p95_latency_ms=182),
        1: CanaryMetrics(error_rate=0.013, p95_latency_ms=192, baseline_error_rate=0.010, baseline_p95_latency_ms=181),
        2: CanaryMetrics(error_rate=0.084, p95_latency_ms=410, baseline_error_rate=0.011, baseline_p95_latency_ms=184),
        3: CanaryMetrics(error_rate=0.090, p95_latency_ms=430, baseline_error_rate=0.010, baseline_p95_latency_ms=180),
    },
}


def mock_metrics(scenario: str, stage_index: int) -> CanaryMetrics:
    try:
        stages = _MOCK_SCENARIOS[scenario]
    except KeyError as exc:
        available = ", ".join(_MOCK_SCENARIOS)
        raise ValueError(f"Unknown mock scenario '{scenario}'. Available: {available}") from exc

    # Clamp to the last defined stage so scenarios with fewer entries than
    # --stages still return something sensible instead of raising.
    last_index = max(stages)
    return stages[min(stage_index, last_index)]


def _prometheus_instant_query(base_url: str, query: str) -> float:
    import requests

    res = requests.get(f"{base_url.rstrip('/')}/api/v1/query", params={"query": query}, timeout=10)
    res.raise_for_status()
    body = res.json()
    if body["status"] != "success":
        raise RuntimeError(f"Prometheus query failed: {body.get('error', 'unknown error')}")
    result = body["data"]["result"]
    if not result:
        return 0.0
    return float(result[0]["value"][1])


def live_metrics(prometheus_url: str, canary_app: str, stable_app: str) -> CanaryMetrics:
    def error_rate(app: str) -> float:
        query = (
            f'sum(rate(http_requests_total{{app="{app}",status=~"5.."}}[5m])) '
            f'/ sum(rate(http_requests_total{{app="{app}"}}[5m]))'
        )
        return _prometheus_instant_query(prometheus_url, query)

    def p95_latency_ms(app: str) -> float:
        query = (
            f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket'
            f'{{app="{app}"}}[5m])) by (le)) * 1000'
        )
        return _prometheus_instant_query(prometheus_url, query)

    return CanaryMetrics(
        error_rate=error_rate(canary_app),
        p95_latency_ms=p95_latency_ms(canary_app),
        baseline_error_rate=error_rate(stable_app),
        baseline_p95_latency_ms=p95_latency_ms(stable_app),
    )


def fetch_canary_health(
    *, canary_app: str, stable_app: str, stage_index: int, scenario: str = "healthy"
) -> tuple[CanaryMetrics, str]:
    """Returns (metrics, source) where source is 'live' or 'mock'."""
    prometheus_url = os.environ.get("PROMETHEUS_URL")
    if prometheus_url:
        return live_metrics(prometheus_url, canary_app, stable_app), "live"
    return mock_metrics(scenario, stage_index), "mock"
