"""Generate one Harbor task directory per seed under tasks/.

python scripts/build_tasks.py --seeds 0-4
The simulator package is copied into each task so every task is self-contained."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "triage_env"

INSTRUCTION = """\
You are the on-call engineer for a small web platform. Customers use the three **user-facing**
services; those depend on application services, which depend on data services. Something is
broken, and the loudest alert is not necessarily where the problem is.

You work through the `incident-triage` MCP server. Every tool call advances a shared clock:
looking things up costs 1 tick, changing things (restart, rollback, set_config, scale) costs
3 ticks, and `wait` lets time pass. Your shift is **45 ticks**. Effects of a change are not
reported back; observe them yourself. Incidents can begin at any time during the first
20 ticks of the shift, so a quiet dashboard early on is not proof that the shift is over.

When you are done (or out of ideas), call `submit` with up to three findings
`{"service": ..., "kind": ...}` for root causes you found **and fixed**. `kind` is one of
`bad_deploy`, `bad_config`, `resource_exhaustion`, `stuck_process`.

You are scored on the health of the user-facing services after the shift, weighted by traffic,
compared with doing nothing. Credit for a finding requires that the fault was actually fixed;
needless changes to healthy services cost points; finishing sooner earns a small bonus.
"""

TASK_TOML = """\
schema_version = "1.4"
artifacts = []

[task]
name = "break-the-agent/incident-triage-s{seed:02d}"
version = "1.0.0"
description = "Budgeted incident triage (seed {seed})"
authors = []
keywords = ["incident-response", "mcp", "rl-environment"]

[metadata]
seed = {seed}

[verifier]
timeout_sec = 120.0
environment_mode = "separate"
collect = []

[verifier.env]
TRIAGE_SEED = "{seed}"

[agent]
timeout_sec = 1800.0

[environment]
network_mode = "public"
build_timeout_sec = 600.0
os = "linux"

[[environment.mcp_servers]]
name = "incident-triage"
transport = "stdio"
command = "python"
args = ["-m", "triage_env.mcp_server"]

[environment.env]
TRIAGE_SEED = "{seed}"
TRIAGE_TRACE = "/logs/agent/triage_trace.json"
PYTHONPATH = "/opt/triage"

[solution.env]
TRIAGE_SEED = "{seed}"
"""

ENV_DOCKERFILE = """\
FROM python:3.12-slim
RUN pip install --no-cache-dir "mcp==1.30.0"
COPY triage_env /opt/triage/triage_env
WORKDIR /app
"""

TESTS_DOCKERFILE = """\
FROM python:3.12-slim
COPY triage_env /tests/triage_env
COPY test.sh /tests/test.sh
WORKDIR /app
"""

TEST_SH = """\
#!/bin/bash
# Replays the recorded tool calls on a fresh copy of the simulator and writes the reward.
# A missing trace (agent never called a tool) scores as do-nothing.
mkdir -p /logs/verifier
PYTHONPATH=/tests python -m triage_env.score --trace /logs/agent/triage_trace.json --out /logs/verifier
"""

SOLVE_SH = """\
#!/bin/bash
# Oracle: the scripted reference policy, using only the information the tools expose.
mkdir -p /logs/agent
PYTHONPATH=/opt/triage python -m triage_env.baselines reference --trace /logs/agent/triage_trace.json
"""


def build(seed, out):
    d = out / ("incident-triage-s%02d" % seed)
    if d.exists():
        shutil.rmtree(d)
    for sub in ("environment", "tests", "solution"):
        (d / sub).mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(PKG, d / "environment" / "triage_env", ignore=ignore)
    shutil.copytree(PKG, d / "tests" / "triage_env", ignore=ignore)
    (d / "instruction.md").write_text(INSTRUCTION, newline="\n")
    (d / "task.toml").write_text(TASK_TOML.format(seed=seed), newline="\n")
    (d / "environment" / "Dockerfile").write_text(ENV_DOCKERFILE, newline="\n")
    (d / "tests" / "Dockerfile").write_text(TESTS_DOCKERFILE, newline="\n")
    (d / "tests" / "test.sh").write_text(TEST_SH, newline="\n")
    (d / "solution" / "solve.sh").write_text(SOLVE_SH, newline="\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0-4")
    ap.add_argument("--out", default=str(ROOT / "tasks"))
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.seeds.split("-"))
    for s in range(lo, hi + 1):
        build(s, Path(a.out))
    print("built seeds %d-%d in %s" % (lo, hi, a.out))


if __name__ == "__main__":
    main()
