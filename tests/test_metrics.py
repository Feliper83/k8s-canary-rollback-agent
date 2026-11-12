import pytest

from canary_agent.metrics import fetch_canary_health, mock_metrics


def test_mock_metrics_healthy_scenario_tracks_baseline() -> None:
    m = mock_metrics("healthy", stage_index=2)
    assert abs(m.error_rate - m.baseline_error_rate) < 0.01


def test_mock_metrics_regression_scenario_spikes_at_stage_two() -> None:
    before = mock_metrics("regression", stage_index=1)
    after = mock_metrics("regression", stage_index=2)
    assert after.error_rate > before.error_rate * 3


def test_mock_metrics_unknown_scenario_raises() -> None:
    with pytest.raises(ValueError, match="Unknown mock scenario"):
        mock_metrics("does-not-exist", stage_index=0)


def test_mock_metrics_clamps_to_last_defined_stage() -> None:
    # Only 4 stages are defined (indices 0-3); index 10 should reuse index 3.
    assert mock_metrics("healthy", stage_index=10) == mock_metrics("healthy", stage_index=3)


def test_fetch_canary_health_uses_mock_without_prometheus_url(monkeypatch) -> None:
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)

    metrics, source = fetch_canary_health(
        canary_app="app-canary", stable_app="app-stable", stage_index=0, scenario="healthy"
    )

    assert source == "mock"
    assert metrics == mock_metrics("healthy", stage_index=0)
