"""Fault classes F1-F5: planning (scenario time) and behaviour (tick time).

`plan()` returns the truth spec stored in `Scenario.faults`; `build()` turns a spec into a Fault
that mutates the World each tick via `apply`. Nothing here is visible to agents except through
what the simulator shows (metrics, logs, deploys, audit logs, events).
"""

CLASSES = {}
FLAG_NAMES = ("new-checkout-flow", "pricing-v2", "async-invoicing", "fast-ranker", "legacy-tax-calc",
              "dark-launch-recs", "bulk-export", "edge-cache-v2", "beta-dashboard", "audit-v3",
              "strict-validation", "prefetch-hints")


def comb(a, b):
    return 1 - (1 - a) * (1 - b)


def _bump(version):
    a, b, _ = (int(x) for x in version[1:].split("."))
    return f"v{a}.{b + 1}.0"


def _apps(sc, used, min_share, attr="crit"):
    """App nodes (not the entry) whose failure reaches users: >= min_share of traffic through critical edges."""
    return [n for n in sc.order if sc.nodes[n].kind == "app" and not sc.nodes[n].entry
            and n not in used and getattr(sc, attr)[n] >= min_share]


def _pick(rng, cands):
    if not cands:
        raise ValueError("no candidate node")
    return rng.choice(cands)


def _reg(cls):
    CLASSES[cls.fault_class] = cls
    return cls


class Fault:
    fault_class = ""
    signals = ()        # tools whose output shows the fault (>= 2)

    def __init__(self, spec):
        self.spec, self.node, self.onset = spec, spec["node"], spec["onset"]

    def apply(self, w, t):
        pass

    def fixed(self, w):
        raise NotImplementedError

    def log_lines(self, w, node, tt, rec, rng):
        return []

    def fix_action(self):
        """Privileged: (tool, args) of the correct fix (used by the oracle policy only)."""
        raise NotImplementedError

    def is_fix(self, tool, args):
        """True if this (tool, args) call is a correct fix for this fault (used by tags)."""
        raise NotImplementedError

    def oracle_start(self, cost):
        """Privileged: earliest call time whose effect lands at the onset (rollbacks need the deploy to exist)."""
        return self.onset - cost


@_reg
class BadDeploy(Fault):
    fault_class = "bad_deploy"
    signals = ("get_deploys", "get_logs", "get_metrics")

    def apply(self, w, t):
        s = self.spec
        if t == self.onset - 1:
            w.deploy(self.node, s["bad_version"], t, by="ci-bot")
        if w.nodes[self.node].version == s["bad_version"]:
            w.add_err(self.node, s["err"])

    def fixed(self, w):
        return w.nodes[self.node].version != self.spec["bad_version"]

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["ver"] == self.spec["bad_version"] and rng.random() < .8:
            return [("ERROR", f"unhandled exception in request handler: NullPointerException at "
                              f"com.svc.{node}.Handler.process(Handler.java:{rng.randint(80, 400)}) "
                              f"[build={rec['ver']}]")]
        return []

    def fix_action(self):
        return "rollback", {"service": self.node, "version": self.spec["prev_version"]}

    def oracle_start(self, cost):
        return self.onset

    def is_fix(self, tool, args):
        return tool == "rollback" and args.get("service") == self.node and args.get("version") != self.spec["bad_version"]


@_reg
class MemoryLeak(Fault):
    fault_class = "memory_leak"
    signals = ("get_deploys", "get_metrics", "get_logs")

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t == self.onset - 1:
            w.deploy(self.node, s["bad_version"], t, by="ci-bot")
        if nd.version != s["bad_version"]:
            return
        if nd.ready_n > 0:
            nd.mem += (1 - nd.sp.mem_base) / s["period"]
        if nd.mem >= 1.0:                       # OOMKilled: cold start, memory resets
            nd.mem = nd.sp.mem_base
            nd.ready_n, nd.warm_until = 0, t + nd.sp.cold_start
            w.tick_flags[self.node] = "oom"
        w.lat_mult[self.node] = 1 + 2 * nd.mem ** 4
        # ponytail: GC thrash near the limit also drops requests (not in the spec; keeps the leak costly)
        w.add_err(self.node, 0.4 * max(0.0, (nd.mem - 0.85) / 0.15) ** 2)

    def fixed(self, w):
        return w.nodes[self.node].version != self.spec["bad_version"]

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node or rec["ver"] != self.spec["bad_version"]:
            return []
        out = []
        if rec["flag"] == "oom":
            out.append(("ERROR", f"OOMKilled: container exceeded memory limit ({w.nodes[node].sp.mem_mb}Mi), restarting"))
        elif rec["mem"] > .6 and rng.random() < .8:
            out.append(("WARN", f"GC overhead: {int(rec['mem'] * 45)}% of CPU time in GC, heap {rec['mem']:.0%} of limit"))
        return out

    def fix_action(self):
        return "rollback", {"service": self.node, "version": self.spec["prev_version"]}

    def oracle_start(self, cost):
        return self.onset

    def is_fix(self, tool, args):
        return tool == "rollback" and args.get("service") == self.node and args.get("version") != self.spec["bad_version"]


@_reg
class RetryStorm(Fault):
    fault_class = "retry_storm"
    signals = ("get_config", "get_metrics", "get_logs")

    def apply(self, w, t):
        s = self.spec
        if t == self.onset - 2:
            w.set_cfg(self.node, "max_retries", s["new"], t, by="dave")
        if self.onset <= t < self.onset + 3:    # short db slowdown that tips the system over
            w.add_err(s["db"], 0.5)

    def fixed(self, w):
        return w.nodes[self.node].cfg["max_retries"] <= 2 and w.err[self.spec["db"]] < .05

    def log_lines(self, w, node, tt, rec, rng):
        n = w.nodes[node]
        if node == self.node and rec["ce"].get(self.spec["db"], 0) > .05 and rng.random() < .8:
            r = n.cfg["max_retries"]
            return [("WARN", f"retrying call to {self.spec['db']} (attempt {rng.randint(1, max(1, r))}/{r})")]
        return []

    def fix_action(self):
        return "set_config", {"service": self.node, "key": "max_retries", "value": self.spec["old"]}

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "max_retries"
                and isinstance(args.get("value"), int) and args["value"] <= 2)


@_reg
class ConfigDrift(Fault):
    fault_class = "config_drift"

    @property
    def signals(self):
        return (("get_flags" if self.spec["variant"] == "flag" else "get_config"), "get_metrics", "get_logs")

    def apply(self, w, t):
        s = self.spec
        if t == self.onset - 1:
            if s["variant"] == "flag":
                w.set_flag(s["flag"], True, t, by="bob")
            else:
                w.set_cfg(self.node, "timeout_ms", s["new"], t, by="bob")

    def fixed(self, w):
        s = self.spec
        if s["variant"] == "flag":
            return not w.flags[s["flag"]]["on"]
        return w.nodes[self.node].cfg["timeout_ms"] >= s["old"] / 2

    def log_lines(self, w, node, tt, rec, rng):
        s = self.spec
        if node == self.node and s["variant"] == "flag" and w.flags[s["flag"]]["on"] and rng.random() < .8:
            return [("WARN", f"slow path taken: feature '{s['flag']}' enabled, request took {rng.randint(900, 1600)}ms")]
        return []

    def fix_action(self):
        s = self.spec
        if s["variant"] == "flag":
            return "set_flag", {"flag": s["flag"], "on": False}
        return "set_config", {"service": self.node, "key": "timeout_ms", "value": s["old"]}

    def is_fix(self, tool, args):
        s = self.spec
        if s["variant"] == "flag":
            return tool == "set_flag" and args.get("flag") == s["flag"] and args.get("on") is False
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "timeout_ms"
                and isinstance(args.get("value"), int) and args["value"] >= s["old"] / 2)


@_reg
class ExternalDependency(Fault):
    fault_class = "external_dependency"
    signals = ("get_events", "get_metrics", "get_logs")

    def apply(self, w, t):
        s = self.spec
        if t == self.onset:
            w.event(t, "message", "info", s["caller"],
                    f"status page of {self.node}: degraded performance, elevated 5xx (posted by vendor)")
        if t >= self.onset:
            w.add_err(self.node, s["err"])
            w.lat_mult[self.node] = 5.0

    def fixed(self, w):
        return w.cb[(self.spec["caller"], self.node)] == "fallback"

    def fix_action(self):
        return "set_circuit_breaker", {"service": self.spec["caller"], "dep": self.node, "mode": "fallback"}

    def is_fix(self, tool, args):
        return (tool == "set_circuit_breaker" and args.get("service") == self.spec["caller"]
                and args.get("dep") == self.node and args.get("mode") == "fallback")


# ---- planning -------------------------------------------------------------------------------

def plan(fam, sc, rng, onset, used):
    spec = PLANNERS[fam](sc, rng, onset, used)
    spec.update(fault_class=fam, onset=onset)
    return spec


def _plan_deploy(sc, rng, onset, used):
    node = _pick(rng, _apps(sc, used, .3))
    prev = sc.deploys[node][-1]["version"]
    return {"node": node, "prev_version": prev, "bad_version": _bump(prev), "err": rng.uniform(.3, .6),
            "period": rng.randint(15, 25)}


def _plan_retry(sc, rng, onset, used):
    def w(e):
        return sc.share[e.caller] * e.fanout * ((1 - sc.params["hit_base"]) if e.via_cache else 1)
    x = max((e for e in sc.edges if e.callee == sc.db), key=w).caller
    if x in used:
        raise ValueError("retry client already used")
    return {"node": x, "db": sc.db, "old": 1, "new": 6}


def _slow(p50, p99, limit):
    import math
    if p99 <= limit:
        return 0.0
    if limit >= p50:
        return 0.5 * math.log(p99 / limit) / math.log(p99 / p50)
    return 0.5 + 0.5 * (1 - limit / p50)


def _plan_config(sc, rng, onset, used):
    hit = sc.params["hit_base"]
    new = rng.randint(30, 60)

    def est_err(n):                 # error the timeout would cause at nominal load
        keep = 1.0
        for e in sc.children(n):
            if e.critical:
                c = sc.nodes[e.callee]
                keep *= 1 - e.fanout * ((1 - hit) if e.via_cache else 1) * _slow(sc.p50[e.callee], c.tail * sc.p50[e.callee], new)
        return 1 - keep
    tn = [n for n in _apps(sc, used, .25) if est_err(n) >= .25]
    if tn and rng.random() < .5:
        node = rng.choice(tn)
        return {"node": node, "variant": "timeout", "old": sc.nodes[node].timeout_ms, "new": new}
    node = _pick(rng, _apps(sc, used, .4, "share") or _apps(sc, used, .3, "share"))
    fl = rng.choice(sc.flags)          # reuse one of the scenario's flags: off, with a big hidden latency effect
    flag, ms = fl["name"], rng.randint(900, 1500)
    fl.update(on=False, effect=(node, ms))
    sc.flag_audit[:] = [a for a in sc.flag_audit if a["flag"] != flag]
    return {"node": node, "variant": "flag", "flag": flag, "ms": ms}


def _plan_external(sc, rng, onset, used):
    callers = [e.caller for e in sc.edges if e.callee == sc.external]
    if sc.external in used or sc.crit[callers[0]] < .25:
        raise ValueError("external unavailable")
    return {"node": sc.external, "caller": callers[0], "err": rng.uniform(.4, .7)}


PLANNERS = {"bad_deploy": _plan_deploy, "memory_leak": _plan_deploy, "retry_storm": _plan_retry,
            "config_drift": _plan_config, "external_dependency": _plan_external}


def build(spec):
    return CLASSES[spec["fault_class"]](spec)
