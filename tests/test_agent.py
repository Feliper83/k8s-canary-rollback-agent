import json
from pathlib import Path

from canary_agent.agent import run_canary_rollout


def test_healthy_scenario_promotes_through_all_stages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("KUBECONFIG", raising=False)
    audit_log = tmp_path / "audit.jsonl"

    result = run_canary_rollout(
        namespace="default",
        canary_deployment="app-canary",
        stable_deployment="app-stable",
        stages=[10, 25, 50, 100],
        scenario="healthy",
        audit_log_path=audit_log,
    )

    assert result.status == "promoted"
    assert result.final_stage_percent == 100

    records = [json.loads(line) for line in audit_log.read_text().splitlines()]
    assert len(records) == 4
    assert all(r["decision"]["action"] == "promote" for r in records)


def test_regression_scenario_rolls_back_before_full_promotion(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("KUBECONFIG", raising=False)
    audit_log = tmp_path / "audit.jsonl"

    result = run_canary_rollout(
        namespace="default",
        canary_deployment="app-canary",
        stable_deployment="app-stable",
        stages=[10, 25, 50, 100],
        scenario="regression",
        audit_log_path=audit_log,
    )

    assert result.status == "rolled_back"
    assert result.final_stage_percent == 50  # breaches at the 3rd stage (index 2)
    assert "exceeds" in result.reason

    records = [json.loads(line) for line in audit_log.read_text().splitlines()]
    # 3 stage decisions (10, 25, 50) + 1 rollback-applied record; 100% is never attempted.
    assert len(records) == 4
    assert records[-1]["event"] == "rollback_applied"
    assert records[-1]["traffic_split"]["canary_replicas"] == 0


def test_rollback_sets_canary_replicas_to_zero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PROMETHEUS_URL", raising=False)
    monkeypatch.delenv("KUBECONFIG", raising=False)

    events = []
    run_canary_rollout(
        namespace="default",
        canary_deployment="app-canary",
        stable_deployment="app-stable",
        stages=[10, 25, 50, 100],
        scenario="regression",
        audit_log_path=None,
        on_event=events.append,
    )

    rollback_events = [e for e in events if e.get("event") == "rollback_applied"]
    assert len(rollback_events) == 1
    assert rollback_events[0]["traffic_split"]["stable_replicas"] == 10
