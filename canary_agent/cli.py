"""Command-line entrypoint.

    canary-rollback-agent run \\
        --canary my-app-canary --stable my-app-stable \\
        --stages 10,25,50,100 --scenario healthy

Runs entirely in mock mode (no cluster needed) unless PROMETHEUS_URL and/or
KUBECONFIG are set in the environment -- see README for live-mode wiring.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .agent import run_canary_rollout
from .policy import Thresholds


def _print_event(record: dict) -> None:
    if record.get("event") == "rollback_applied":
        print(f"  >>> ROLLBACK applied: {record['reason']} "
              f"(traffic now {record['traffic_split']['canary_replicas']}/"
              f"{record['traffic_split']['stable_replicas']} canary/stable replicas)")
        return

    decision = record["decision"]
    metrics = record["metrics"]
    split = record["traffic_split"]
    print(
        f"[stage {record['stage_percent']:>3}%] source={record['metrics_source']:<4} "
        f"canary_err={metrics['error_rate']:.1%} baseline_err={metrics['baseline_error_rate']:.1%} "
        f"canary_p95={metrics['p95_latency_ms']:.0f}ms baseline_p95={metrics['baseline_p95_latency_ms']:.0f}ms "
        f"-> {decision['action'].upper()} ({decision['reason']}) "
        f"[replicas: {split['canary_replicas']} canary / {split['stable_replicas']} stable, "
        f"mode={split['source']}]"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="canary-rollback-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a progressive canary rollout")
    run.add_argument("--namespace", default="default")
    run.add_argument("--canary", required=True, help="Canary Deployment name")
    run.add_argument("--stable", required=True, help="Stable Deployment name")
    run.add_argument("--stages", default="10,25,50,100", help="Comma-separated traffic percentages")
    run.add_argument("--total-replicas", type=int, default=10)
    run.add_argument("--bake-seconds", type=float, default=0.0, help="Pause between stages (real rollouts only)")
    run.add_argument("--scenario", default="healthy", choices=["healthy", "regression"],
                      help="Mock-mode metrics scenario (ignored if PROMETHEUS_URL is set)")
    run.add_argument("--audit-log", type=Path, default=Path("canary-rollout-audit.jsonl"))
    run.add_argument("--max-error-rate", type=float, default=0.05)
    run.add_argument("--max-error-rate-delta", type=float, default=0.02)
    run.add_argument("--max-latency-ratio", type=float, default=1.5)

    return parser


def cmd_run(args: argparse.Namespace) -> int:
    stages = [int(s.strip()) for s in args.stages.split(",") if s.strip()]
    thresholds = Thresholds(
        max_error_rate=args.max_error_rate,
        max_error_rate_delta=args.max_error_rate_delta,
        max_latency_ratio=args.max_latency_ratio,
    )

    print(f"Starting canary rollout: {args.canary} -> {args.stable} in '{args.namespace}', "
          f"stages={stages}, scenario={args.scenario}\n")

    result = run_canary_rollout(
        namespace=args.namespace,
        canary_deployment=args.canary,
        stable_deployment=args.stable,
        stages=stages,
        total_replicas=args.total_replicas,
        thresholds=thresholds,
        scenario=args.scenario,
        bake_seconds=args.bake_seconds,
        audit_log_path=args.audit_log,
        on_event=_print_event,
    )

    print(f"\nResult: {result.status.upper()} at {result.final_stage_percent}% -- {result.reason}")
    print(f"Audit log: {args.audit_log}")
    return 0 if result.status == "promoted" else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return cmd_run(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
