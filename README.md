# OnCall

OnCall is a deterministic, seeded incident-response RL environment. An agent is the on-call engineer
for a ~12-service platform (e-shop, SaaS or media topology) that is already failing. It investigates and
fixes it through 20 MCP tools (observations, actions, `resolve_incident`), and every call advances a
simulated clock. The reward is computed from ground truth (traffic served through the shift and a 45-minute
1.5x-traffic epilog, faults really fixed, correct diagnosis, minus collateral damage, data loss and cost).

Design: [DESIGN.md](DESIGN.md) (Czech). Progress: [TASKS.md](TASKS.md).

## Quickstart

```bash
uv sync                      # or: make dev
uv run pytest -q             # make test
uv run oncall eval --policy 'reference,noop,stop_early,exploit_*' --suite dev     # make eval
make baseline                # regenerate results/baseline.json (judge suite)
uv run oncall report --input results/baseline.json --compare results/baseline.json   # exit 1 on any score drift > 1e-9
```

Serving one episode over MCP (streamable HTTP, `/mcp`) and scoring it:

```bash
make images                  # docker build -> oncall-sim:local
docker run --rm -p 8000:8000 -e SCENARIO_SEED=2005 -e SCENARIO_DIFFICULTY=medium \
  -e ADMIN_TOKEN_SHA256=$(printf secret | sha256sum | cut -d' ' -f1) oncall-sim:local
uv run oncall solve --url http://localhost:8000/mcp                  # reference policy over MCP
uv run oncall finalize --url http://localhost:8000/mcp --token secret --out out/   # reward.txt + reward_breakdown.json
```

`POST /admin/finalize` (`Authorization: Bearer <token>`, compared as SHA-256 to `ADMIN_TOKEN_SHA256`) is the only
way to read the score; no tool returns truth. Set `ONCALL_RUN_DIR` to also write the episode JSONL
(`ONCALL_CLICKHOUSE_URL` additionally pushes it to ClickHouse; failures only warn).

## v2: harder through realism (what changed and why)

v1 was too easy for frontier agents (reference 0.98, Kimi 0.87): one cause per scenario, loud signals, logs that named the cause.
Benchmarks where frontier agents score 10-50 % (ITBench, OpenRCA, AIOpsLab) are hard because of silent data-integrity faults
behind green dashboards, misleading upstream symptoms, gray (partial) failures, several concurrent root causes and
the need to follow the propagation path. v2 adds exactly that, **each mechanism copied from a documented real incident**.
Difficulty is measured afterwards; no parameter was tuned to hit a score, the only fairness invariant is that the tool-only
reference solves every dev scenario (>= 0.8).

- **Telemetry**: logs among ~97 % noise, symptom services log loud upstream errors and the cause service quiet lines; versions only
  in `get_deploys`; 6-10 mostly symptom/flapping alerts at the start; health checks are liveness only; `get_metrics` has 1-minute
  points (default window 5, so periodic bursts hide in it). New tools: `get_instances`, `drain_instance`, `get_business_metrics`;
  new `run_maintenance` actions and `set_config` keys (see the instruction text).
- **Silent harm in the SLI**: a request answered 200 that charged twice, read stale state, lost the receipt mail or the session
  is not `good`. Dashboards stay green, business metrics, support messages and per-instance views show it.
- **Levels** (no `easy`): `medium` = one mechanism + one trap (deploy herring, misleading chat message, or the mechanism's own);
  `hard` = two concurrent causes with a silent / gray / periodic one, or a multi-step mechanism + a mid-shift second fault / ticking bomb;
  `expert` = three interacting causes (loop or causal chain, a silent/gray one, a trap). The report label of a scenario is its primary
  mechanism; F1/F3/F5/F7 occur only as components. Suites: dev 30 (10/10/10), judge 24 (6/10/8), judge-fast 12 (3/5/4), heldout 100, train 100+ (seeds 10000+).
- Tags added: `silent_harm_missed`, `dangerous_failover`, `gray_missed`, `config_push_missed`, `loop_not_broken`.
- New exploit `exploit_block_top_client` (blocks the loudest client in the gateway log, never diagnoses): it hits a real customer.
  `exploit_drain_outliers`, `exploit_blind_sweep` and `exploit_maintenance_all` cover the new actions.

| | real incident | what the simulator does | correct fix | tempting wrong move |
|---|---|---|---|---|
| R1 duplicate_charges | [Twilio billing 2013](https://www.twilio.com/en-us/blog/company/communications/billing-incident-post-mortem-breakdown-analysis-and-root-cause-html) | cache replica resync storms make billing read zero balances and re-charge; HTTP all 200 | kill switch off, read from primary, re-enable | restart the cache primary (data loss), re-enable early |
| R2 replica_lag_stale_reads | [GitHub 2018-10-21](https://github.blog/2018-10-30-oct21-post-incident-analysis), [Honeycomb 2023](https://www.honeycomb.io/blog/incident-review-what-comes-up-must-first-go-down) | a long query holds the replica back 2-10 min, clients read stale orders | `kill_long_queries` or `read_from=primary` | fail over to the lagging replica (data loss) |
| R3 migration_lock | [Pulumi 2023-10-06](https://www.pulumi.com/blog/post-mortem-2023-10-06/) | a migration holds a lock, pools fill with waiters, db CPU low | `cancel_migration`, then roll back the deploy | scale clients, restart/fail over the db |
| R4 pool_sync_recycle | [Clerk 2025-09](https://clerk.com/blog/2025-09-18-database-incident-postmortem) | after a db minor upgrade pooled connections recycle in sync every 15 min | `conn_lifetime_jitter=on` on all clients | block bots, stop the cron, scale/restart the db |
| R5 progressive_gray | [Netlify 2021-03-25](https://www.netlify.com/blog/2021/04/02/load-balancer-service-degradation-march-25-2021.md) | gateway instances lose their LB route one by one, health checks pass | `restart_networkd` | drain bad instances only, restart the service |
| R6 clock_skew | [Cloudflare 2017 leap second](https://blog.cloudflare.com/how-and-why-the-leap-second-affected-cloudflare-dns/) | one auth instance's clock jumps, 401s, logouts | drain it or `sync_clock` | roll back auth, flush sessions |
| R7 expired_cert_dismissed_alert | [Postmark 2024-09-16](https://postmarkapp.com/blog/outbound-smtp-outage-on-september-15-2024), [Let's Encrypt 2021](https://letsencrypt.org/docs/dst-root-ca-x3-expiration-september-2021) | mail sender TLS fails, a flapping synthetic alert is dismissed | `rotate_cert` / `update_ca_bundle` | circuit breaker, rollback |
| R8 mail_backlog_ramp | [Postmark 2022-12-16](https://postmarkapp.com/blog/email-delays-december-16-2022) | provider outage queues mail; draining at full rate trips receiver throttling, which lingers | `send_rate_per_s` low (<= 4x normal), raise in steps | purge the queue (mail lost), full-rate drain, scale |
| R9 cache_invalidation_loop | [Facebook 2010-09-23](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/) | an invalid cache config value makes clients delete keys and refill from the db, db errors cause more deletes | shed load, revert the value, wait for db + cache, lift the limit | revert only, restart, scale apps |
| R10 bad_config_push | [Cloudflare 2019-07-02](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/) | a gateway rule pushed via config/flag burns CPU (backtracking), no deploy | revert `waf_ruleset` / kill-switch flag | roll back code, scale the gateway |
| R11 redis_maxmemory | [GitLab production#482](https://gitlab.com/gitlab-com/gl-infra/production/-/issues/482) | lowered maxmemory / changed policy evicts sessions, mass logout, login storm | restore `maxmemory_mb` / `volatile-lru` | `flush_redis`, restart the cache (data loss) |
| R12 duplicate_events | [CircleCI 2025-12-02](https://status.circleci.com/incidents/kvzp8x242n34) | a producer deploy publishes every order event twice: duplicate shipments, 2x queue in-rate | roll back the producer (or flag off), then purge duplicates | rate-limit customers, scale consumers |
| R13 stuck_failover | [GoCardless 2017-10-10](https://gocardless.com/blog/incident-review-api-and-dashboard-outage-on-10th-october/) | primary has disk I/O errors, replica in sync, the cluster manager reverts a failover | `cluster_manager=maintenance`, then `failover_db` | repeated failovers, restart, chase the WAL warning |
| R14 abusive_client | [Healthchecks.io 2025-11-01](https://blog.healthchecks.io/2025/11/post-mortem-outage-on-november-1/) | one client holds the gateway's connection slots | `block_client=<id>` | scale / restart the gateway, global rate limit |

## Baseline v2 (judge suite, 24 scenarios, `results/baseline.json`)

| policy | mean score | max |
|---|---|---|
| reference (tool-only runbook) | 0.969 | 0.997 |
| noop, stop_early | 0.000 | 0.000 |
| exploit_* (11 policies) | 0.000 | 0.028 |

Reference per level (judge): medium 0.977, hard 0.968, expert 0.963 (min 0.920); the 300-scenario sweep (100 per level) never goes below 0.89
for any mechanism. The reference and the oracle are runbooks written by the environment authors, so these numbers show solvability and
no leakage, not how hard the benchmark is for models: that is measured by running agents (not done yet for v2).
Invariant: `max(exploit) < 0.25 < mean(reference) - 0.5`.
Scoring note: `P_collateral` is 0.10 per unnecessary destructive action (rollback, restart, failover, draining a healthy instance, `flush_redis`)
and 0.05 per other unnecessary change (a change is necessary if it is a step of a real fix or targets a faulty service), so blind sweeps do not pay.

## v1 (before the realism rework): frontier agents on the v1 judge suite (24 scenarios x 3 runs each)

These numbers belong to the v1 scenarios (easy/medium/hard levels, F1-F14 only) and are not comparable with the v2 suites above. Direct runner at temperature 1.0 with reasoning on. Combined report:
[results/judge-agents/report.md](results/judge-agents/report.md) (per model: [Nemotron](results/nemotron-judge/report.md),
[Kimi](results/kimi-judge/report.md), [DeepSeek](results/deepseek-judge/report.md)).

| policy | all | easy | medium | hard | gap to reference (95% CI) | gap per run |
|---|---|---|---|---|---|---|
| reference | 0.979 | 0.978 | 0.980 | 0.978 | | |
| Kimi K3.1 Pro (Verda inference) | 0.874 ± 0.182 | 0.922 | 0.957 | 0.802 | **0.105** [0.060, 0.158] | 0.130 / 0.069 / 0.116 |
| DeepSeek 4.1 Flash (Verda inference) | 0.851 ± 0.195 | 0.922 | 0.947 | 0.764 | **0.127** [0.072, 0.195] | 0.120 / 0.132 / 0.130 |
| Nemotron 3.5 Super 120B (NVIDIA API) | 0.840 ± 0.183 | 0.891 | 0.904 | 0.781 | **0.138** [0.088, 0.200] | 0.104 / 0.152 / 0.159 |
| noop / stop_early | 0.000 | 0.000 | 0.000 | 0.000 | | |

The gap is positive in every run for all three models. Difficulty concentrates where the design puts the traps: hard
scenarios with a mid-shift second fault (F8: Kimi 0.55), cache stampede (F9: Nemotron 0.59, Kimi 0.73), unmasked
cascade (F14: ~0.8), poison message + second fault (F10: DeepSeek 0.72) and, for Kimi, the full-disk masked fix (F7: 0.78 ± 0.34). All three models share the dominant failure:
fix the first fault, call `resolve_incident`, and miss the second fault that arrives at t~40-50 even though the
instruction says faults can arrive mid-shift (`missed_event`; annotated in the reports with the exact times). Other
tags over 72 episodes each (Nemotron / Kimi / DeepSeek): collateral 13 / 15 / 14, over_investigation 19 / 10 / 8,
symptom_fix 7 / 4 / 6, missed_event 5 / 7 / 8.
Replaying all 216 recorded action sequences on a fresh simulator reproduces every score bit for bit. Model ids,
providers and sampling settings are in the report hashes and `results/agent-*.json`.

## Harbor

```bash
uv run oncall export-harbor --suite judge --out harbor/tasks     # make export; 24 task dirs, fresh admin tokens
make images                                                      # the sim sidecar image oncall-sim:local
uv run oncall judge --suite judge-fast --agent-runs 3 --model <model> --agent opencode   # make judge-fast
```

Each task is a Harbor task: the agent container (`main`, python + `mcp` + curl, no simulator code, no token)
reaches the sim sidecar `oncall-sim` at `http://oncall-sim:8000/mcp`; `tests/test.sh` (shared verifier mode, uploaded
after the agent finishes) calls `/admin/finalize` and writes `/logs/verifier/reward.txt`
plus `reward_breakdown.json`. `solution/` carries a copy of the package and runs the reference policy (oracle runs
only). `oncall judge` runs the deterministic policies and, only if `harbor` is on PATH and `--model` is given,
the agent runs; it writes `results/<timestamp>/report.md`. Without those, agent runs are skipped.

## LLM agents (Gemini, Nemotron, Gemma on vLLM)

Any OpenAI-compatible chat endpoint can play the agent through the same tools (schemas taken from the MCP server).
Model ids are always explicit; keys come from the environment and are never logged.

```bash
export GEMINI_API_KEY=...       # or NVIDIA_API_KEY for nemotron; vllm needs VLLM_BASE_URL, no key
make judge MODEL=<gemini model id>                       # baselines + 3 agent runs, report in results/<ts>/
make judge MODEL=<id> ARGS='--runner harbor --agent opencode'   # same, but through `harbor run`
make agent PROVIDER=nemotron MODEL=<id> SUITE=judge-fast         # agent only -> results/agent-*.json + runs/
uv run oncall report --input results/<ts>/eval.json              # gap reference - agent with 95% bootstrap CI
```

Without `--model`, `oncall judge` runs only the deterministic policies and says so. Each agent episode leaves a
logsink JSONL plus the full LLM transcript (`<episode>.messages.json`) in the run dir.

## Training a small model (Gemma on Verda)

[train/README.md](train/README.md) is the runbook: reference rollouts on the `train` split + rejection-sampled
LLM rollouts -> `train/build_dataset.py` (score >= 0.8, refuses dev/judge/heldout seeds, keeps model reasoning when a
transcript exists) -> LoRA SFT (`train/sft.py`) -> optional online GRPO against the environment (`train/grpo.py`) ->
`gemma-base` vs `gemma-ft` on `heldout` and on a held-out fault family via `make agent PROVIDER=vllm`.
GPU deps live in a separate group: `uv sync --group train`.

## Analysis (ClickHouse)

`analysis/schema.sql` + queries (score by model x difficulty x family, tag distribution, time to first correct fix,
Gemma base vs fine-tuned, exploit matrix). `make clickhouse` loads `runs/` when `ONCALL_CLICKHOUSE_URL` is set and
is a no-op otherwise. JSONL in `runs/` stays the source of truth.

## Known gaps

- Harbor end to end was verified with Harbor 0.26 on one task (`judge-00`): `harbor run -a oracle` -> reward 0.97317,
  bit-identical to the local reference score; `-a nop` -> 0.0. Not yet run there: a real LLM agent (`-a opencode`),
  which needs a model API key. The first build of the agent image can exceed 10 minutes on slow mirrors
  (`build_timeout_sec = 1800`).
- The reference policy scores 0.95-1.0 on every scenario, so the suite is calibrated for solvability and exploit
  resistance, not yet for frontier-model difficulty (unmeasured). Some mechanics are simplifications: a queue is one
  lag number with a poison message that only the DLQ clears, `purge_dlq` only matters for R8 (mail queue) and R12 (duplicate backlog), and F14's partner B is "scaled in
  by the autoscaler" when its upstream starts failing (fixed once it has >= 80% of its original replicas).
- Scores are deterministic, but `sin`/`gauss` may differ in the last ulp across platforms (baseline compare uses 1e-9).
- Re-exporting regenerates the admin tokens, so `harbor/tasks/**/tests/test.sh` and the compose files change on every export.
