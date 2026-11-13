"""oncall CLI: eval | report | export-harbor | serve | solve | finalize | judge."""
import argparse
import hashlib
import json
import secrets
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
from fnmatch import fnmatch
from importlib.metadata import version as pkg_version
from pathlib import Path
from random import Random

from . import logsink
from .policies import POLICIES, run_env, run_policy
from .scenarios import FAMILIES, T, E, suite
from .sim import ACT_COST, OBS_COST

ROOT = Path(__file__).resolve().parents[2]
DET = "reference,noop,stop_early,exploit_*"
SIM_URL = "http://oncall-sim:8000/mcp"


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def dump(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")


def sd(xs):
    return statistics.stdev(xs) if len(xs) > 1 else 0.0


# ---- eval -------------------------------------------------------------------------------------
def pick_policies(spec):
    names = []
    for pat in spec.split(","):
        hit = [n for n in POLICIES if fnmatch(n, pat.strip())]
        if not hit:
            sys.exit(f"unknown policy {pat!r}; known: {', '.join(POLICIES)}")
        names += [n for n in hit if n not in names]
    return names


def run_eval(policies, suite_name, run_dir=None):
    scs = suite(suite_name)
    res = {"suite": suite_name, "scenarios": [s.id for s in scs], "policies": {}}
    for name in policies:
        out = []
        for sc in scs:
            if run_dir:
                env = run_env(name, sc)
                bd = env.finalize()
                logsink.write_episode(run_dir, f"{name}-{sc.id}", env, bd)
            else:
                bd = run_policy(name, sc)
            out.append(bd)
        res["policies"][name] = out
    return res


def table(res):
    rows = [f"{'policy':28} {'n':>3} {'mean':>7} {'std':>7} {'min':>7} {'max':>7}"]
    for name, bds in res["policies"].items():
        s = [b["score"] for b in bds]
        rows.append(f"{name:28} {len(s):3} {statistics.mean(s):7.3f} {sd(s):7.3f} {min(s):7.3f} {max(s):7.3f}")
    return "\n".join(rows)


def cmd_eval(a):
    run_dir = Path(a.run_dir) / stamp() if a.run_dir else None
    res = run_eval(pick_policies(a.policy), a.suite, run_dir)
    print(table(res))
    if a.out:
        dump(a.out, res)


# ---- report -----------------------------------------------------------------------------------
def fam(b):
    return b["faults"][0][1]


def group(bds, key):
    g = {}
    for b in bds:
        g.setdefault(key(b), []).append(b["score"])
    return {k: {"n": len(v), "mean": statistics.mean(v), "std": sd(v)} for k, v in sorted(g.items())}


def per_scenario(bds):
    g = {}
    for b in bds:
        g.setdefault(b["scenario"], []).append(b["score"])
    return {k: statistics.mean(v) for k, v in g.items()}


def bootstrap_gap(ref, agent, n=2000):
    ids = sorted(set(ref) & set(agent))
    if not ids:
        return None
    gaps = [ref[i] - agent[i] for i in ids]
    rng = Random(0)
    means = sorted(statistics.mean(rng.choices(gaps, k=len(gaps))) for _ in range(n))
    return {"n": len(ids), "mean": statistics.mean(gaps), "ci95": [means[int(.025 * n)], means[int(.975 * n) - 1]]}


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or None
    except OSError:
        return None


def make_report(res):
    pols = res["policies"]
    rep = {"suite": res["suite"], "policies": {}, "gap": {}, "exploits": {}, "tags": {}, "hashes": {
        "git_commit": git_commit(),
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest() if (ROOT / "uv.lock").exists() else None,
        "scenarios": res["scenarios"]}}
    for name, bds in pols.items():
        s = [b["score"] for b in bds]
        rep["policies"][name] = {"n": len(s), "mean": statistics.mean(s), "std": sd(s),
                                 "by_difficulty": group(bds, lambda b: b["difficulty"]), "by_family": group(bds, fam)}
        tags = {}
        for b in bds:
            for t in b["tags"]:
                tags[t] = tags.get(t, 0) + 1
        rep["tags"][name] = dict(sorted(tags.items()))
        if name.startswith("exploit_"):
            rep["exploits"][name] = {"mean": statistics.mean(s), "max": max(s)}
    if "reference" in pols:
        for name in pols:
            if name not in POLICIES:     # non-deterministic agent policy
                rep["gap"][name] = bootstrap_gap(per_scenario(pols["reference"]), per_scenario(pols[name]))
    return rep


def render_md(rep):
    L = [f"# OnCall report: suite `{rep['suite']}`", "", "## Score per policy (mean ± std)", "",
         "| policy | n | all | easy | medium | hard |", "|---|---|---|---|---|---|"]
    ms = lambda d: f"{d['mean']:.3f} ± {d['std']:.3f}" if d else "-"
    for n, p in rep["policies"].items():
        L.append(f"| {n} | {p['n']} | {ms(p)} | " + " | ".join(ms(p["by_difficulty"].get(d)) for d in ("easy", "medium", "hard")) + " |")
    L += ["", "## Score per fault family (mean ± std)", "", "| policy | " + " | ".join(FAMILIES) + " |", "|---|" + "---|" * len(FAMILIES)]
    for n, p in rep["policies"].items():
        L.append(f"| {n} | " + " | ".join(ms(p["by_family"].get(f)) for f in FAMILIES) + " |")
    if rep["gap"]:
        L += ["", "## Gap reference - agent (95% bootstrap CI over scenarios)", ""]
        for n, g in rep["gap"].items():
            L.append(f"- {n}: " + (f"{g['mean']:.3f} [{g['ci95'][0]:.3f}, {g['ci95'][1]:.3f}] over {g['n']} scenarios" if g else "no common scenarios"))
    if rep["exploits"]:
        L += ["", "## Exploit matrix (must stay < 0.25)", "", "| exploit | mean | max | ok |", "|---|---|---|---|"]
        for n, x in rep["exploits"].items():
            L.append(f"| {n} | {x['mean']:.3f} | {x['max']:.3f} | {'yes' if x['max'] < .25 else 'NO'} |")
    L += ["", "## Failure tags", ""]
    for n, t in rep["tags"].items():
        L.append(f"- {n}: " + (", ".join(f"{k}={v}" for k, v in t.items()) or "none"))
    h = rep["hashes"]
    L += ["", "## Hashes", "", f"- git commit: {h['git_commit']}", f"- uv.lock sha256: {h['uv_lock_sha256']}",
          f"- scenarios ({len(h['scenarios'])}): {', '.join(h['scenarios'])}", ""]
    return "\n".join(L)


def compare(res, base):
    bad = []
    for name, bds in res["policies"].items():
        if name not in POLICIES:
            continue
        ref = {b["scenario"]: b["score"] for b in base["policies"].get(name, [])}
        for b in bds:
            if b["scenario"] not in ref or abs(ref[b["scenario"]] - b["score"]) > 1e-9:
                bad.append(f"{name} {b['scenario']}: {b['score']} vs baseline {ref.get(b['scenario'])}")
    return bad


def write_report(res, out_dir):
    rep = make_report(res)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dump(out_dir / "report.json", rep)
    (out_dir / "report.md").write_text(render_md(rep), encoding="utf-8")
    return out_dir


def cmd_report(a):
    res = json.loads(Path(a.input).read_text(encoding="utf-8"))
    out = write_report(res, a.out_dir or Path("results") / stamp())
    print(f"report written to {out}")
    if a.compare:
        bad = compare(res, json.loads(Path(a.compare).read_text(encoding="utf-8")))
        for line in bad[:20]:
            print("MISMATCH", line)
        if bad:
            sys.exit(f"{len(bad)} score(s) differ from {a.compare}")
        print(f"scores match {a.compare}")


# ---- harbor export ----------------------------------------------------------------------------
TOOLS_DOC = [
    ("get_status", "", "time, remaining minutes, active alerts, cumulative spend"),
    ("get_events", "since=0", "alerts, deploys and team messages"),
    ("get_topology", "", "services, replicas, dependency edges with circuit-breaker state; the database replica's sync state"),
    ("get_metrics", "services (1-5 names), window=5 (1-30)", "metric series per service: rps, error_rate, p50, p99, cpu, mem, conns, worker_util, disk, retries, queue_lag, cache_hit_rate"),
    ("get_logs", "service, level=ALL|ERROR|WARN|INFO, grep='', limit=50 (1-200)", "log lines of the last 60 minutes"),
    ("get_traces", "endpoint ('/' + a direct dependency of the entry service), n=5 (1-10)", "sample request traces"),
    ("get_deploys", "service=None", "deploy history incl. has_schema_migration and reversible"),
    ("get_config", "service", "current config and its change audit log"),
    ("get_flags", "", "feature flags and their change audit log"),
    ("get_runbook", "topic", "generic SRE runbook text"),
    ("rollback", "service, version", "roll back to an older version"),
    ("restart", "service", "restart a service"),
    ("scale", "service, replicas (1-20)", "set the replica count (adds spend)"),
    ("set_config", "service, key, value", "keys: max_retries 0-10, timeout_ms 10-30000, pool_size 1-100, rate_limit_rps 0-100000 (0 = off), log_level, dlq_enabled"),
    ("set_flag", "flag, on", "turn a feature flag on or off"),
    ("set_circuit_breaker", "service, dep, mode=closed|open|fallback", "set the breaker of one dependency edge"),
    ("failover_db", "", "fail over the database to its replica"),
    ("run_maintenance", "service, action", "actions: rotate_cert, prune_logs, purge_dlq, warm_cache, vacuum_db, rebalance_shards, compact_wal, flush_dns (valid kinds differ per action)"),
    ("wait", "minutes (1-30)", "let time pass"),
    ("resolve_incident", "root_causes=[{service, fault_class}], summary=''", "close the incident; ends your interaction"),
]


def instruction():
    cost = {**OBS_COST, **ACT_COST, "wait": "n"}
    tools = "\n".join(f"- `{n}({sig})`: {doc}. Cost: {cost[n]} min." for n, sig, doc in TOOLS_DOC)
    return f"""# Production incident

You are the on-call engineer for a web platform of about a dozen services (user-facing entry service,
application services, a database, a cache and an external provider). Users are being affected by an
incident that is already in progress. Find the root cause(s), fix them, and report what you found.

You interact with the platform only through the tools of the MCP server `oncall`. The platform is not reachable
any other way. Time is simulated: **every tool call advances the clock**, and the platform
keeps serving traffic (and failing) while you work.

## Rules of the clock

- The shift is **T = {T} minutes** (t = 0 .. {T - 1}). History before t = 0 is visible through the metrics and log tools.
- Actions take effect only when their duration has elapsed; observations return the state at the time of the call.
- The shift ends when you call `resolve_incident`, when t >= {T}, or after 150 tool calls.
- After it ends you cannot act any more, but the platform keeps running for a further **{E}-minute epilog at 1.5x traffic**.
  Your score depends on how the platform fares through the epilog, so fixes must be durable, not cosmetic.
- A call with invalid arguments costs 1 minute and changes nothing.
- There may be more than one problem, and a second one can start later in the shift.
- Not every alert, recent deploy or warning is related to the incident.

## Tools (cost in simulated minutes)

{tools}

`fault_class` is one of: {", ".join(f"`{f}`" for f in FAMILIES)}.
In `resolve_incident`, list one entry per root cause: the service where the fault lives and its class.

## Scoring

Per minute t, `offered` is the user traffic and `good` the share served successfully and fast enough.
Error budget: `w_t = 1` while the cumulative outage minutes (sum of (offered - good) / offered) are <= 15, else `w_t = 2`.

```
U        = 1 - sum_t w_t * (offered_t - good_t) / sum_t w_t * offered_t        (t over the shift and the epilog)
R_avail  = clip((U - U_noop) / (U_oracle - U_noop), 0, 1)     # U_noop: doing nothing, U_oracle: an omniscient operator
R_fixed  = share of the real faults that are actually fixed at the end of the epilog
R_diag   = 1 if the set of (service, fault_class) you reported equals the true set, else 0
raw      = 0.6 * R_avail + 0.3 * R_fixed + 0.1 * R_diag
score    = clip(raw * M_dataloss - P_collateral - P_cost, 0, 1)
```

- `M_dataloss` = 0.25 if you fail over to a database replica that is not in sync, or roll back past an irreversible schema migration; otherwise 1.
- `P_collateral` = 0.10 per rollback, restart, failover_db or harmful maintenance (vacuum_db, rebalance_shards, compact_wal)
  on a service that is not the location of any real fault.
- `P_cost` = 0.10 if the mean spend over shift and epilog exceeds 1.3x that of doing nothing.

The reward of this task is `score`. Stopping early or changing things at random does not pay off.
"""


def task_toml(sc, tid):
    return f'''schema_version = "1.4"
artifacts = []

[task]
name = "oncall/{tid}"
version = "1.0.0"
description = "OnCall incident-response episode"
authors = []
keywords = ["incident-response", "mcp", "rl-environment"]

[metadata]
difficulty = "{sc.difficulty}"

[verifier]
timeout_sec = 300.0
# environment_mode left at its default (shared): tests run in the agent container, which can reach the sidecar.

[agent]
timeout_sec = 3600.0

[environment]
network_mode = "public"
build_timeout_sec = 600.0
os = "linux"

[[environment.mcp_servers]]
name = "oncall"
transport = "streamable-http"
url = "{SIM_URL}"
'''


def compose(sc, token_sha):
    return f'''services:
  main:
    build:
      context: ${{CONTEXT_DIR}}
    command: ["sh", "-c", "sleep infinity"]
    depends_on:
      oncall-sim:
        condition: service_healthy
  oncall-sim:
    image: oncall-sim:local
    environment:
      SCENARIO_SEED: "{sc.seed}"
      SCENARIO_DIFFICULTY: "{sc.difficulty}"
      ONCALL_SALT: "{sc.salt}"
      ADMIN_TOKEN_SHA256: "{token_sha}"
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; socket.create_connection(('localhost', 8000), 2)"]
      interval: 2s
      timeout: 3s
      retries: 30
'''


def dockerfile():
    return f"""FROM python:3.12-slim
# Agent container: MCP client libraries and curl only. No simulator code, no admin token.
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir mcp=={pkg_version('mcp')}
WORKDIR /workspace
"""


SOLVE_SH = f"""#!/bin/bash
# Oracle run: the reference policy over MCP HTTP. solution/ exists only in Harbor oracle runs.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$DIR" python -m oncall.cli solve --url {SIM_URL}
"""


def test_sh(token):
    return f"""#!/bin/bash
# Asks the sim sidecar for the final score. Any failure leaves the reward at 0.
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
curl -sS --fail --max-time 240 -X POST -H "Authorization: Bearer {token}" \\
  http://oncall-sim:8000/admin/finalize -o /logs/verifier/reward_breakdown.json || exit 0
python3 - <<'EOF' || echo 0 > /logs/verifier/reward.txt
import json
score = float(json.load(open("/logs/verifier/reward_breakdown.json"))["score"])
open("/logs/verifier/reward.txt", "w").write(str(score))
EOF
exit 0
"""


def export_harbor(suite_name, out):
    out = Path(out)
    src = Path(__file__).resolve().parent
    ids = []
    for i, sc in enumerate(suite(suite_name)):
        tid = f"{suite_name}-{i:02d}"      # opaque: sc.id contains the fault family
        d = out / tid
        if d.exists():
            shutil.rmtree(d)
        token = secrets.token_hex(32)       # fresh per export; only tests/test.sh knows it
        files = {"task.toml": task_toml(sc, tid), "instruction.md": instruction(),
                 "environment/Dockerfile": dockerfile(),
                 "environment/docker-compose.yaml": compose(sc, hashlib.sha256(token.encode()).hexdigest()),
                 "solution/solve.sh": SOLVE_SH, "tests/test.sh": test_sh(token)}
        for rel, text in files.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        shutil.copytree(src, d / "solution" / "oncall", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        ids.append(tid)
    return ids


def cmd_export(a):
    ids = export_harbor(a.suite, a.out)
    print(f"exported {len(ids)} tasks to {a.out}")


# ---- serve / solve / finalize -----------------------------------------------------------------
def cmd_serve(a):
    from .server import main as serve
    serve()


def cmd_solve(a):
    from .client import http_call
    POLICIES["reference"](http_call(a.url))


def fetch_score(url, token):
    req = urllib.request.Request(url, data=b"", method="POST", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def cmd_finalize(a):
    base = a.url.split("/mcp")[0].rstrip("/")
    bd = fetch_score(base + "/admin/finalize", a.token)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.txt").write_text(str(bd["score"]), encoding="utf-8")
    dump(out / "reward_breakdown.json", bd)
    print(f"score {bd['score']}")


# ---- judge ------------------------------------------------------------------------------------
def cmd_judge(a):
    out = Path("results") / stamp()
    out.mkdir(parents=True)
    ids = export_harbor(a.suite, "harbor/tasks")
    print(f"exported {len(ids)} tasks")
    if shutil.which("docker"):
        subprocess.run(["docker", "build", "-t", "oncall-sim:local", "-f", "docker/sim.Dockerfile", "."], check=True)
    else:
        print("docker not found: sim image not built")
    res = run_eval(pick_policies(DET), a.suite)
    print(table(res))
    if shutil.which("harbor") and a.model:
        runs = []
        for tid in ids:
            for k in range(a.agent_runs):
                jobs = out / "harbor" / f"{tid}-{k}"
                subprocess.run(["harbor", "run", "-p", f"harbor/tasks/{tid}", "-a", a.agent, "-m", a.model, "-o", str(jobs)])
                # ponytail: Harbor's job layout is unverified; take whatever verifier breakdown it left.
                for f in sorted(jobs.rglob("reward_breakdown.json")):
                    runs.append(json.loads(f.read_text(encoding="utf-8")))
        res["policies"][f"agent:{a.model}"] = runs
    else:
        print("agent runs skipped (needs `harbor` on PATH and --model)")
    dump(out / "eval.json", res)
    print(f"report written to {write_report(res, out)}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="oncall")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("eval")
    s.add_argument("--policy", default=DET)
    s.add_argument("--suite", default="dev")
    s.add_argument("--out")
    s.add_argument("--run-dir")
    s.set_defaults(fn=cmd_eval)
    s = sub.add_parser("report")
    s.add_argument("--input", required=True)
    s.add_argument("--compare")
    s.add_argument("--out-dir")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("export-harbor")
    s.add_argument("--suite", default="judge")
    s.add_argument("--out", default="harbor/tasks")
    s.set_defaults(fn=cmd_export)
    sub.add_parser("serve").set_defaults(fn=cmd_serve)
    s = sub.add_parser("solve")
    s.add_argument("--url", required=True)
    s.set_defaults(fn=cmd_solve)
    s = sub.add_parser("finalize")
    s.add_argument("--url", required=True)
    s.add_argument("--token", required=True)
    s.add_argument("--out", default="/logs/verifier")
    s.set_defaults(fn=cmd_finalize)
    s = sub.add_parser("judge")
    s.add_argument("--suite", default="judge", choices=["judge", "judge-fast"])
    s.add_argument("--agent-runs", type=int, default=3)
    s.add_argument("--model")
    s.add_argument("--agent", default="opencode")
    s.set_defaults(fn=cmd_judge)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
