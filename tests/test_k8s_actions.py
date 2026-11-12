from canary_agent.k8s_actions import apply_traffic_weight, compute_replica_split


def test_compute_replica_split_rounds_and_preserves_total() -> None:
    canary, stable = compute_replica_split(total_replicas=10, canary_percent=30)
    assert canary == 3
    assert stable == 7
    assert canary + stable == 10


def test_compute_replica_split_zero_percent_is_all_stable() -> None:
    canary, stable = compute_replica_split(total_replicas=10, canary_percent=0)
    assert canary == 0
    assert stable == 10


def test_compute_replica_split_hundred_percent_is_all_canary() -> None:
    canary, stable = compute_replica_split(total_replicas=10, canary_percent=100)
    assert canary == 10
    assert stable == 0


def test_apply_traffic_weight_dry_run_without_kubeconfig(monkeypatch) -> None:
    monkeypatch.delenv("KUBECONFIG", raising=False)

    split = apply_traffic_weight(
        namespace="default",
        canary_deployment="app-canary",
        stable_deployment="app-stable",
        canary_percent=50,
        total_replicas=10,
    )

    assert split.source == "dry-run"
    assert split.canary_replicas + split.stable_replicas == 10
