"""One command: python -m triage_env.evaluate [--seeds 0-19]  ->  results table + results/baselines.json"""
import argparse
import json
import statistics
from pathlib import Path

from .baselines import POLICIES
from .world import World


def run(policy, seed):
    w = World(seed)
    POLICIES[policy](w)
    return w.finish()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0-19")
    ap.add_argument("--out", default="results/baselines.json")
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.seeds.split("-"))
    seeds = range(lo, hi + 1)
    table = {}
    print("%-12s %6s %6s %6s %6s" % ("policy", "mean", "sd", "min", "max"))
    for name in POLICIES:
        rs = [run(name, s)["reward"] for s in seeds]
        table[name] = {"mean": statistics.mean(rs), "sd": statistics.pstdev(rs), "min": min(rs), "max": max(rs),
                       "per_seed": dict(zip(map(str, seeds), rs))}
        print("%-12s %6.3f %6.3f %6.3f %6.3f" % (name, *(table[name][k] for k in ("mean", "sd", "min", "max"))))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
