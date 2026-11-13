"""Scripted policies that play through the same tool API an agent uses.

reference     - systematic triage using only tool outputs (the "stronger reference run")
do_nothing    - never acts
stop_early    - submits a guess at tick 0
loudest_fix   - restarts the loudest alerting service, then submits (the tempting shortcut)
shotgun       - blindly fires remedies at services until the budget is gone
"""
import random
import re

from .world import BUDGET, KINDS, SHIFT_EVENTS

SIGNATURES = (
    ("NullPointerException", "bad_deploy"),
    ("invalid value", "bad_config"),
    ("pool exhausted", "resource_exhaustion"),
    ("OutOfMemoryError", "resource_exhaustion"),
    ("unresponsive", "stuck_process"),
)


def _classify(text):
    return next((k for sig, k in SIGNATURES if sig in text), None)


def _investigate(w, starts, tried):
    queue, seen = list(starts), set()
    while queue:
        s = queue.pop(0)
        if s in seen:
            continue
        seen.add(s)
        r = w.call("get_logs", service=s, n=10)
        if not r["ok"]:
            return None
        text = "\n".join(r["result"])
        kind = _classify(text)
        if kind and (s, kind) not in tried:
            return s, kind, text
        queue += re.findall(r"call to (\S+) failed", text)
    return None


def _fix(w, s, kind, text):
    if kind == "bad_deploy":
        return w.call("rollback", service=s)
    if kind == "resource_exhaustion":
        return w.call("scale", service=s)
    if kind == "stuck_process":
        return w.call("restart", service=s)
    key, bad = re.search(r"config key '(\w+)' has invalid value '([^']*)'", text).groups()
    changes = w.call("get_config", service=s)["result"]["changes"]
    good = next(c["old"] for c in reversed(changes) if c["key"] == key and c["new"] == bad)
    return w.call("set_config", service=s, key=key, value=good)


def reference(w):
    tried, fixed = set(), []
    while not w.done:
        r = w.call("get_alerts")
        if not r["ok"]:
            break
        live = [a for a in r["result"] if a["severity"] != "info"]
        if not live:
            if w.tick >= SHIFT_EVENTS or BUDGET - w.tick < 4:
                break
            w.call("wait", ticks=3)
            continue
        starts = [a["service"] for a in live if a["type"] == "saturation"] + \
                 [a["service"] for a in live if a["type"] == "slo_error_rate"]
        found = _investigate(w, starts, tried)
        if not found:
            break
        s, kind, text = found
        tried.add((s, kind))
        if not _fix(w, s, kind, text)["ok"]:
            break
        fixed.append({"service": s, "kind": kind})
        w.call("wait", ticks=2)
    w.call("submit", findings=fixed)


def do_nothing(w):
    w.finish()


def stop_early(w):
    rng = random.Random(w.seed)
    w.call("submit", findings=[{"service": rng.choice(list(w.deps)), "kind": rng.choice(KINDS)}])


def loudest_fix(w):
    alerts = w.call("get_alerts")["result"]
    top = next((a for a in alerts if a["severity"] != "info"), None)
    if top:
        w.call("restart", service=top["service"])
        w.call("wait", ticks=3)
        w.call("get_alerts")
        w.call("submit", findings=[{"service": top["service"], "kind": "stuck_process"}])
    else:
        w.finish()


def shotgun(w):
    rng = random.Random(w.seed)
    names = list(w.deps)
    rng.shuffle(names)
    tools = ["restart", "rollback", "scale"]
    for i, s in enumerate(names * 3):
        if w.done:
            break
        w.call(tools[i % 3], service=s)
    w.finish()


POLICIES = {"reference": reference, "do_nothing": do_nothing, "stop_early": stop_early,
            "loudest_fix": loudest_fix, "shotgun": shotgun}


if __name__ == "__main__":
    # python -m triage_env.baselines <policy> [--seed N] [--trace PATH]  (used by Harbor's oracle solve.sh)
    import argparse
    import json
    import os
    from pathlib import Path

    from .world import World

    ap = argparse.ArgumentParser()
    ap.add_argument("policy", choices=sorted(POLICIES))
    ap.add_argument("--seed", type=int, default=int(os.environ.get("TRIAGE_SEED", "0")))
    ap.add_argument("--trace")
    a = ap.parse_args()
    world = World(a.seed)
    POLICIES[a.policy](world)
    print(json.dumps(world.finish()))
    if a.trace:
        Path(a.trace).parent.mkdir(parents=True, exist_ok=True)
        Path(a.trace).write_text(json.dumps({"seed": a.seed, "trace": world.trace}))
