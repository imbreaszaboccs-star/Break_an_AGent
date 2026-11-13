# Incident triage: a budgeted, partially observable RL environment

An agent is the on-call engineer for a 10-service platform (3 user-facing → 4 application → 3 data).
Faults live deep in the graph and surface as symptoms at the top, so the loudest alert is usually
**not** the culprit. Every tool call advances a shared clock (lookups 1 tick, changes 3, `wait` n);
the shift is 45 ticks and a second incident starts mid-shift. The agent has to trace symptoms to a
root cause, pick the *right* remedy, verify it held, and notice the second incident.

| Fault kind | Signature the agent can see | Correct remedy | Tempting wrong move |
|---|---|---|---|
| `bad_deploy` | NullPointerException in logs, fresh deploy | `rollback` | restart |
| `bad_config` | "invalid value" in logs, config change | `set_config` back to the old value | restart / scale |
| `resource_exhaustion` | memory or pool at 95%+, saturation alert | `scale` | `restart` (masks it for 4 ticks, then it returns) |
| `stuck_process` | cpu ~0, 0 req/s, "unresponsive" | `restart` | rollback |

Everything needed is observable through the tools (alerts, metrics, logs, deploys, config history,
dependency graph); nothing is withheld, and the decoys (a harmless recent deploy, a debug-log config
change, an info-level disk alert) are visible to the agent too.

## Reward (`triage_env/world.py: World.score`)

```
reward = 0.70 * recovery + 0.20 * diagnosis + 0.10 * recovery * efficiency - collateral
```
* **recovery**: traffic-weighted health of the user-facing tier at a *fixed horizon* (tick 51), rescaled between
  "do nothing" (0) and "fully healthy" (1). Stopping early changes nothing about when health is measured.
* **diagnosis**: a submitted `{service, kind}` counts only if it matches a real fault **and that fault was fixed**; wrong findings subtract.
* **collateral**: 0.04 per change that neither fixed nor relieved a fault (capped at 0.25).
* **efficiency**: ticks unused; only pays out in proportion to recovery.

The verifier does not trust the server: the MCP server records every call, and `triage_env.score`
**replays** them on a fresh simulator (`replay()`), so the reward is recomputed from actions.

## Run it

```sh
python -m unittest discover -s tests -t .          # 10 integrity tests, stdlib only
python -m triage_env.evaluate --seeds 0-19         # reference vs do-nothing / stop-early / shortcuts
python scripts/build_tasks.py --seeds 0-4          # writes Harbor task dirs to tasks/
harbor lint tasks/incident-triage-s00              # static check (passes)
harbor run -p tasks/incident-triage-s00 -a opencode -m <model>   # needs Docker + credits; flags per starter kit
```
`harbor run -a oracle -p tasks/...` plays `solution/solve.sh` (the scripted reference) through the same verifier.

## Results so far (seeds 0-19, scripted policies, no LLM yet)

```
policy         mean     sd    min    max
reference     0.947  0.005  0.938  0.956     scripted triage that only reads tool output
do_nothing    0.000  0.000  0.000  0.000
stop_early    0.000  0.000  0.000  0.000     submits a random guess at tick 0
loudest_fix   0.000  0.000  0.000  0.000     restarts the loudest alert, submits
shotgun       0.137  0.179  0.000  0.450     fires remedies at random services
```
**Not yet measured:** the frontier-agent gap (needs the Harbor+OpenCode harness and credits). The
reference is deterministic, so reference variance is ~0 by construction; the interesting number is the LLM's.

## Reward-hacking probes already covered (`tests/test_world.py`)
do-nothing / stop-early score 0 · pre-emptive remedies before a fault starts do nothing · restart on a
resource-exhausted service gives temporary relief that does not count · finishing right after incident 1
misses incident 2 · findings without a fix get no diagnosis credit · budget is enforced · replay equals live score.

## Known gaps (be honest with the judges)
* **Truth is derivable from the container.** The agent container holds the simulator source and `TRIAGE_SEED`; an agent that reads
  them can recompute the scenario. Fix: run the MCP server as a Docker Compose sidecar the agent cannot read, or set `TRIAGE_SALT` only on the server side.
* **Harbor/Docker path unverified here.** `harbor lint` passes and the oracle + verifier were dry-run without Docker, and the MCP server
  was exercised with an MCP client, but no container has been built (no Docker on this machine). Whether `/logs/agent` is visible to the separate verifier needs one real `harbor run`.
* The trace file can be forged by an agent with shell access (it would still have to encode a good action sequence, i.e. know the answer).
* `mcp>=2` renamed `FastMCP`; the server pins `mcp<2`.
