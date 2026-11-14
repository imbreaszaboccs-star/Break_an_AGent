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
docker run --rm -p 8000:8000 -e SCENARIO_SEED=2000 -e SCENARIO_DIFFICULTY=easy \
  -e ADMIN_TOKEN_SHA256=$(printf secret | sha256sum | cut -d' ' -f1) oncall-sim:local
uv run oncall solve --url http://localhost:8000/mcp                  # reference policy over MCP
uv run oncall finalize --url http://localhost:8000/mcp --token secret --out out/   # reward.txt + reward_breakdown.json
```

`POST /admin/finalize` (`Authorization: Bearer <token>`, compared as SHA-256 to `ADMIN_TOKEN_SHA256`) is the only
way to read the score; no tool returns truth. Set `ONCALL_RUN_DIR` to also write the episode JSONL
(`ONCALL_CLICKHOUSE_URL` additionally pushes it to ClickHouse; failures only warn).

## Baseline (judge suite, 24 scenarios, `results/baseline.json`)

| policy | mean score | max |
|---|---|---|
| reference | 0.979 | 1.000 |
| noop | 0.000 | 0.000 |
| stop_early | 0.000 | 0.000 |
| exploit_* (9 policies, incl. `exploit_blind_sweep`) | 0.000 | 0.000 |

Reference per difficulty (judge): easy 0.978, medium 0.980, hard 0.978 (min 0.948). Fault families F1-F14
(F8 = second fault mid-episode and F13 = misleading team message are scenario axes) are all in `dev` and `judge`;
`oncall report` groups by these labels. Invariant: `max(exploit) < 0.25 < mean(reference) - 0.5`.
Scoring note: `P_collateral` is 0.10 per unnecessary destructive action and 0.05 per unnecessary other change
(a change is necessary if it is a step of a real fix or targets a faulty service), so blind sweeps do not pay.

## Frontier agent: Nemotron on judge-fast (12 scenarios x 3 runs)

`nvidia/nemotron-3.5-super-vl-120b-a12b` (NVIDIA API, thinking on, temperature 1.0, top_p 0.95) through the direct
runner. Full report: [results/nemotron-judge-fast/report.md](results/nemotron-judge-fast/report.md).

| policy | all | easy | medium | hard |
|---|---|---|---|---|
| reference | 0.977 | 0.976 | 0.979 | 0.977 |
| Nemotron (36 episodes) | 0.789 ± 0.215 | 0.934 | 0.857 | 0.695 |
| noop / stop_early | 0.000 | 0.000 | 0.000 | 0.000 |

**Gap reference - Nemotron: 0.188, 95% bootstrap CI [0.115, 0.267]; positive in every run (0.181 / 0.222 / 0.162).**
Weakest families: F10 poison message + second fault (0.63), F9 cache stampede (0.64), F12 thread starvation (0.74),
F14 unmasked cascade (0.74). Typical failure: the agent fixes the first fault and resolves before the mid-shift second
fault appears (`missed_event`), or touches a healthy node first (`symptom_fix`, `collateral`). Replaying the 36
recorded action sequences on a fresh simulator reproduces every score bit for bit.

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
  lag number with a poison message that only the DLQ clears, `purge_dlq` is a no-op, and F14's partner B is "scaled in
  by the autoscaler" when its upstream starts failing (fixed once it has >= 80% of its original replicas).
- Scores are deterministic, but `sin`/`gauss` may differ in the last ulp across platforms (baseline compare uses 1e-9).
- Re-exporting regenerates the admin tokens, so `harbor/tasks/**/tests/test.sh` and the compose files change on every export.
