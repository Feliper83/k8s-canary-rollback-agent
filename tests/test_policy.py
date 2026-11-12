from canary_agent.metrics import CanaryMetrics
from canary_agent.policy import Thresholds, decide


def _metrics(**overrides) -> CanaryMetrics:
    base = dict(error_rate=0.01, p95_latency_ms=180, baseline_error_rate=0.01, baseline_p95_latency_ms=180)
    base.update(overrides)
    return CanaryMetrics(**base)


def test_promotes_when_canary_matches_baseline() -> None:
    decision = decide(_metrics())
    assert decision.action == "promote"


def test_rolls_back_on_absolute_error_rate_ceiling() -> None:
    decision = decide(_metrics(error_rate=0.06))
    assert decision.action == "rollback"
    assert "absolute ceiling" in decision.reason


def test_rolls_back_on_error_rate_delta_over_baseline() -> None:
    decision = decide(_metrics(error_rate=0.035, baseline_error_rate=0.01))
    assert decision.action == "rollback"
    assert "exceeds baseline" in decision.reason


def test_rolls_back_on_latency_ratio() -> None:
    decision = decide(_metrics(p95_latency_ms=400, baseline_p95_latency_ms=180))
    assert decision.action == "rollback"
    assert "latency" in decision.reason


def test_promotes_within_all_thresholds_even_with_small_deltas() -> None:
    decision = decide(_metrics(error_rate=0.015, baseline_error_rate=0.01, p95_latency_ms=200, baseline_p95_latency_ms=180))
    assert decision.action == "promote"


def test_custom_thresholds_are_respected() -> None:
    tight = Thresholds(max_error_rate=0.02, max_error_rate_delta=0.005, max_latency_ratio=1.1)
    decision = decide(_metrics(error_rate=0.018, baseline_error_rate=0.01), tight)
    assert decision.action == "rollback"
