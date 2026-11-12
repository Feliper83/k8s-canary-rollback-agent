"""Orchestrates a progressive canary rollout with automatic rollback.

At each stage in `stages` (e.g. [10, 25, 50, 100]):
  1. shift that percentage of replicas to the canary deployment
  2. (optionally) bake for `bake_seconds` to let traffic/metrics settle
  3. fetch canary vs. baseline health metrics
  4. run them through the promote/rollback policy
  5. append a structured audit record (what we did, what we saw, why)

On the first rollback decision, traffic is immediately shifted back to 0%
canary and the rollout stops -- no further stages are attempted.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .k8s_actions import apply_traffic_weight
from .metrics import fetch_canary_health
from .policy import Decision, Thresholds, decide

RolloutStatus = Literal["promoted", "rolled_back"]


@dataclass(frozen=True)
class RolloutResult:
    status: RolloutStatus
    final_stage_percent: int
    reason: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_audit(audit_log_path: Path | None, record: dict) -> None:
    if audit_log_path is None:
        return
    with audit_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def run_canary_rollout(
    *,
    namespace: str,
    canary_deployment: str,
    stable_deployment: str,
    stages: list[int],
    total_replicas: int = 10,
    thresholds: Thresholds = Thresholds(),
    scenario: str = "healthy",
    bake_seconds: float = 0.0,
    audit_log_path: Path | None = None,
    on_event=None,
) -> RolloutResult:
    for stage_index, percent in enumerate(stages):
        split = apply_traffic_weight(
            namespace=namespace,
            canary_deployment=canary_deployment,
            stable_deployment=stable_deployment,
            canary_percent=percent,
            total_replicas=total_replicas,
        )

        if bake_seconds:
            time.sleep(bake_seconds)

        metrics, metrics_source = fetch_canary_health(
            canary_app=canary_deployment,
            stable_app=stable_deployment,
            stage_index=stage_index,
            scenario=scenario,
        )
        decision: Decision = decide(metrics, thresholds)

        record = {
            "timestamp": _now(),
            "stage_percent": percent,
            "traffic_split": asdict(split),
            "metrics_source": metrics_source,
            "metrics": asdict(metrics),
            "decision": asdict(decision),
        }
        _append_audit(audit_log_path, record)
        if on_event:
            on_event(record)

        if decision.action == "rollback":
            rollback_split = apply_traffic_weight(
                namespace=namespace,
                canary_deployment=canary_deployment,
                stable_deployment=stable_deployment,
                canary_percent=0,
                total_replicas=total_replicas,
            )
            rollback_record = {
                "timestamp": _now(),
                "stage_percent": 0,
                "traffic_split": asdict(rollback_split),
                "event": "rollback_applied",
                "reason": decision.reason,
            }
            _append_audit(audit_log_path, rollback_record)
            if on_event:
                on_event(rollback_record)

            return RolloutResult(status="rolled_back", final_stage_percent=percent, reason=decision.reason)

    return RolloutResult(status="promoted", final_stage_percent=stages[-1], reason="all stages passed")
