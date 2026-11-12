"""Apply a traffic split between a stable and canary Deployment.

Traffic shifting here is done the simplest possible way that still reflects
real production practice: proportional replica counts behind a shared
Service selector (no service mesh / Argo Rollouts CRD required). Swap this
module's internals for an Istio VirtualService or Argo Rollouts patch if
your cluster already has one of those -- the policy/agent layers don't care
how the split is implemented, only that `apply_traffic_weight` does it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TrafficSplit:
    source: str  # "live" or "dry-run"
    canary_replicas: int
    stable_replicas: int


def compute_replica_split(total_replicas: int, canary_percent: int) -> tuple[int, int]:
    canary_replicas = round(total_replicas * canary_percent / 100)
    stable_replicas = total_replicas - canary_replicas
    return canary_replicas, stable_replicas


def _scale_deployment(namespace: str, deployment: str, replicas: int) -> None:
    from kubernetes import client, config

    config.load_kube_config()
    apps_v1 = client.AppsV1Api()
    apps_v1.patch_namespaced_deployment_scale(
        name=deployment,
        namespace=namespace,
        body={"spec": {"replicas": replicas}},
    )


def apply_traffic_weight(
    *,
    namespace: str,
    canary_deployment: str,
    stable_deployment: str,
    canary_percent: int,
    total_replicas: int,
) -> TrafficSplit:
    canary_replicas, stable_replicas = compute_replica_split(total_replicas, canary_percent)

    if os.environ.get("KUBECONFIG"):
        _scale_deployment(namespace, canary_deployment, canary_replicas)
        _scale_deployment(namespace, stable_deployment, stable_replicas)
        return TrafficSplit("live", canary_replicas, stable_replicas)

    return TrafficSplit("dry-run", canary_replicas, stable_replicas)
