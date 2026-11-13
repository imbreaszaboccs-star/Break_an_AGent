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
| reference | 0.978 | 0.999 |
| noop | 0.000 | 0.000 |
| stop_early | 0.000 | 0.000 |
| exploit_* (8 policies) | 0.000 | 0.000 |

Invariant: `max(exploit) < 0.25 < mean(reference) - 0.5`.

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

## Known gaps

- Harbor end to end has not been run (Harbor is not installed here): the compose merge with Harbor's own
  `main` service, the healthcheck, the `harbor run` flags and the job-output layout `oncall judge` reads are unverified.
- Only fault families F1-F5 exist; F6-F14 and compositional traps are milestone 5.
- Scores are deterministic, but `sin`/`gauss` may differ in the last ulp across platforms (baseline compare uses 1e-9).
- The reference policy is strong (0.978), and difficulty for LLM agents is unmeasured.
- Re-exporting regenerates the admin tokens, so `harbor/tasks/**/tests/test.sh` and the compose files change on every export.
