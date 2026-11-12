# k8s-canary-rollback-agent

An autonomous agent that progressively shifts traffic from a stable Kubernetes deployment to a canary, checking
real-time health signals (error rate, p95 latency vs. baseline) at every stage — and automatically rolling back the
moment the canary regresses, instead of waiting for a human to notice a dashboard.

## Why this exists

Built around a recurring production pattern: canary rollouts where the promote/rollback decision was previously made
by watching a Grafana dashboard during a release window. This agent encodes that decision as an explicit, testable
policy (`canary_agent/policy.py`) and runs it unattended — turning a release that required an engineer babysitting
metrics for hours into one that runs in minutes and only pages someone if it rolls back.

Every decision is written to a structured audit log (JSONL — timestamp, traffic split applied, metrics observed,
decision + reason) so a rollback is always explainable after the fact, not just "the agent did something."

## How a rollout works

Given a list of stages (default `10,25,50,100`), for each stage the agent:

1. Shifts that percentage of replicas to the canary deployment (`k8s_actions.py`)
2. Optionally bakes for `--bake-seconds` to let traffic/metrics settle (real rollouts only)
3. Fetches canary vs. baseline error rate and p95 latency (`metrics.py`)
4. Runs them through the promote/rollback policy (`policy.py`):
   - rollback if canary error rate exceeds an absolute ceiling
   - rollback if canary error rate exceeds baseline by more than an allowed delta
   - rollback if canary p95 latency exceeds baseline by more than an allowed ratio
   - otherwise promote to the next stage
5. Appends the decision (with full reasoning) to the audit log

The instant a stage fails a health gate, traffic is shifted back to 0% canary and the rollout stops — later stages
are never attempted.

## Mock mode vs. live mode

Everything above runs with **no cluster and no Prometheus** by default, replaying one of two deterministic
scenarios so the agent is fully demoable and its policy is unit-testable without infrastructure:

- `--scenario healthy` — canary tracks baseline at every stage, rollout reaches 100%
- `--scenario regression` — canary looks fine for two stages, then its error rate spikes at the 50% stage,
  triggering an automatic rollback

Set these environment variables to switch each half to a real backend:

| Variable | Switches | Behavior |
|---|---|---|
| `PROMETHEUS_URL` | metrics | Queries real Prometheus for error rate / p95 latency by `app` label instead of replaying a mock scenario. |
| `KUBECONFIG` | traffic shifting | Actually patches the canary/stable Deployments' replica counts via the Kubernetes API instead of a dry-run. |

Install the optional `live` extra (`requests`, `kubernetes` client) to use either:

```bash
pip install -e ".[live]"
```

## Usage

```bash
pip install -e ".[dev]"

# Healthy rollout -> reaches 100%
canary-rollback-agent run --canary app-canary --stable app-stable --scenario healthy

# Regression -> auto-rollback at the 50% stage
canary-rollback-agent run --canary app-canary --stable app-stable --scenario regression
```

Exit code is `0` if the rollout promoted fully, `1` if it rolled back — wire this straight into a CI/CD pipeline as
the release gate.

## Project layout

```
canary_agent/
  metrics.py       health signals: live Prometheus query, or mock scenario replay
  policy.py         pure promote/rollback decision function + thresholds
  k8s_actions.py    traffic shifting: live Deployment scaling, or dry-run
  agent.py          orchestrates stages, writes the JSONL audit log
  cli.py            argparse entrypoint
tests/
  test_policy.py       exhaustive threshold-boundary tests
  test_metrics.py       mock scenario behavior
  test_k8s_actions.py   replica-split math + dry-run fallback
  test_agent.py         full rollout loop, both scenarios, audit log contents
```

## Run the tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
