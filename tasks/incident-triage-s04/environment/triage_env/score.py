"""Verifier entry point: replay a recorded trace and write the reward.

python -m triage_env.score --trace /logs/agent/triage_trace.json --out /logs/verifier
A missing or empty trace is scored as do-nothing (0)."""
import argparse
import json
from pathlib import Path

from .world import World, replay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", default="/logs/agent/triage_trace.json")
    ap.add_argument("--out", default="/logs/verifier")
    ap.add_argument("--seed", type=int, default=0, help="used only when the trace file is missing")
    a = ap.parse_args()
    try:
        data = json.loads(Path(a.trace).read_text())
        res = replay(data["seed"], [(t, args) for t, args in data["trace"]])
    except (OSError, ValueError, KeyError):
        res = World(a.seed).finish()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "reward.txt").write_text("%s\n" % res["reward"])
    (out / "reward.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res))


if __name__ == "__main__":
    main()
