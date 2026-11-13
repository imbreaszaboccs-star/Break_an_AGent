"""Budgeted incident triage: a seeded, deterministic, partially observable simulator.

The agent is the on-call engineer for a small service graph. Users hit the
`user-facing` tier; faults live deeper in the graph and show up there as
symptoms. Every tool call costs ticks and the shift has a fixed budget.

The reward is computed from the *state of the world* at a fixed horizon, never
from what the agent says (see `World.score`).
"""
import os
import random
from dataclasses import dataclass, field

BUDGET = 45            # ticks in a shift; every tool call advances the clock by its cost
SETTLE = 6             # extra ticks simulated after the budget before health is scored
HORIZON = BUDGET + SETTLE
HEALTHY_BELOW = 0.05   # error rate under which a service counts as healthy
COUPLING = 0.8         # share of a dependency's errors that reaches its caller
RELIEF = 4             # how long a plain restart masks resource exhaustion
SHIFT_EVENTS = 20      # all incidents begin within the first SHIFT_EVENTS ticks

COSTS = {
    "list_services": 1, "get_alerts": 1, "describe_service": 1, "get_metrics": 1,
    "get_logs": 1, "get_deploys": 1, "get_config": 1,
    "restart": 3, "rollback": 3, "set_config": 3, "scale": 3,
}
KINDS = ("bad_deploy", "bad_config", "resource_exhaustion", "stuck_process")
TIER_NAMES = ("user-facing", "application", "data")
TIER_POOLS = (
    ("frontend", "checkout", "search", "account"),
    ("orders", "payments", "catalog", "auth", "inventory", "recommendations"),
    ("postgres", "redis", "kafka", "blob-store", "email-relay"),
)
TIER_COUNTS = (3, 4, 3)
BAD_VALUES = {"max_connections": "2", "timeout_ms": "1", "cache_ttl_s": "-1"}


@dataclass
class Fault:
    service: str
    kind: str
    severity: float
    onset: int
    key: str = ""           # bad_config
    good: str = ""
    bad: str = ""
    resource: str = "mem"   # resource_exhaustion: "mem" or "conn"
    fixed_at: int = None    # tick from which the fault no longer exists
    relief: list = field(default_factory=list)  # (start, end) windows masked by a restart

    def active(self, t):
        if t < self.onset:
            return False
        if self.fixed_at is not None and t >= self.fixed_at:
            return False
        return not any(a <= t < b for a, b in self.relief)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _bump(version):
    a, b, _ = version[1:].split(".")
    return "v%s.%d.0" % (a, int(b) + 1)


def tstr(t):
    return "T%+d" % t


class World:
    def __init__(self, seed, salt=None):
        self.seed = seed
        self.salt = os.environ.get("TRIAGE_SALT", "") if salt is None else salt
        self.tick = 0
        self.done = False
        self.wasted = 0
        self.findings = []
        self.trace = []
        self.result = None
        self._build(random.Random("%s|%s" % (seed, self.salt)))

    # ------------------------------------------------------------------ world
    def _build(self, rng):
        tiers = [rng.sample(pool, n) for pool, n in zip(TIER_POOLS, TIER_COUNTS)]
        self.tiers = tiers
        self.tier = {s: i for i, names in enumerate(tiers) for s in names}
        self.deps = {s: [] for names in tiers for s in names}
        for upper, lower in ((tiers[0], tiers[1]), (tiers[1], tiers[2])):
            for s in upper:
                self.deps[s] = rng.sample(lower, 2 if upper is tiers[0] else rng.randint(1, 2))
            for d in lower:
                if not any(d in self.deps[s] for s in upper):
                    self.deps[rng.choice(upper)].append(d)
        self.dependents = {s: [u for u in self.deps if s in self.deps[u]] for s in self.deps}
        self.order = tiers[2] + tiers[1] + tiers[0]  # dependencies first
        self.weight = dict(zip(tiers[0], rng.sample([5, 3, 2], 3)))
        self.owner = {s: "team-%s" % rng.choice("abcdef") for s in self.order}
        self.config = {
            s: {"max_connections": str(rng.choice([50, 100, 200])),
                "timeout_ms": str(rng.choice([1000, 2000, 5000])),
                "cache_ttl_s": str(rng.choice([60, 300, 600])),
                "log_level": "info"} for s in self.order}
        self.config_log = {s: [] for s in self.order}
        self.deploys = {
            s: [(-400, "v%d.%d.%d" % (rng.randint(1, 3), rng.randint(0, 9), rng.randint(0, 9)), "release")]
            for s in self.order}

        inner = tiers[1] + tiers[2]
        p, q = rng.sample(inner, 2)
        self.faults = [self._fault(rng, p, 0, 0.6, 0.9), self._fault(rng, q, rng.randint(10, 14), 0.5, 0.7)]
        others = [s for s in self.order if s not in (p, q)]
        # decoys: harmless recent changes and an info-level alert on healthy services
        d1, d2, d3 = rng.sample(others, 3)
        self.deploys[d1].append((-5, _bump(self.deploys[d1][0][1]), "release"))
        self.config_log[d2].append((-4, "log_level", "info", "debug"))
        self.decoy_alerts = [
            {"service": d3, "severity": "info", "type": "disk", "detail": "disk usage 71% (threshold 85%)"}]

    def _fault(self, rng, service, onset, lo, hi):
        f = Fault(service, rng.choice(KINDS), round(rng.uniform(lo, hi), 2), onset)
        if f.kind == "bad_config":
            f.key = rng.choice(sorted(BAD_VALUES))
            f.good, f.bad = self.config[service][f.key], BAD_VALUES[f.key]
            self.config_log[service].append((onset - 2, f.key, f.good, f.bad))
        elif f.kind == "bad_deploy":
            old = self.deploys[service][0][1]
            self.deploys[service].append((onset - 1, _bump(old), "release"))
        elif f.kind == "resource_exhaustion":
            f.resource = rng.choice(["mem", "conn"])
        return f

    # ------------------------------------------------------------- simulation
    def errors(self, t):
        err = {}
        for s in self.order:
            local = sum(f.severity for f in self.faults if f.service == s and f.active(t))
            up = 1.0
            for d in self.deps[s]:
                up *= 1 - COUPLING * err[d]
            err[s] = 1 - (1 - min(local, 1.0)) * up
        return err

    def health(self, t):
        err = self.errors(t)
        tot = sum(self.weight.values())
        return sum(w * (1 - err[s]) for s, w in self.weight.items()) / tot

    def _active(self, s, t):
        return next((f for f in self.faults if f.service == s and f.active(t)), None)

    def _open(self, s):
        return next((f for f in self.faults
                     if f.service == s and f.onset <= self.tick and f.fixed_at is None), None)

    def _rng(self, *parts):
        return random.Random("|".join(str(x) for x in (self.seed, self.salt) + parts))

    # --------------------------------------------------------------- observers
    def _closure_since(self, s, t):
        seen, stack, onsets = set(), [s], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack += self.deps[x]
            f = self._active(x, t)
            if f:
                onsets.append(f.onset)
        return tstr(min(onsets)) if onsets else "n/a"

    def _alerts(self):
        t, err, out = self.tick, self.errors(self.tick), []
        for s in sorted(self.weight, key=lambda x: -self.weight[x]):
            if err[s] >= HEALTHY_BELOW:
                out.append({"service": s, "severity": "critical" if err[s] > 0.3 else "warning",
                            "type": "slo_error_rate", "error_rate": round(err[s], 2),
                            "since": self._closure_since(s, t)})
        for s in self.order:
            f = self._active(s, t)
            if f and f.kind == "resource_exhaustion":
                m = self._metrics(s)
                detail = "memory %d%%" % m["mem_pct"] if f.resource == "mem" else "connection pool %d%%" % m["conn_pool_pct"]
                out.append({"service": s, "severity": "warning", "type": "saturation",
                            "detail": detail, "since": tstr(f.onset)})
        return out + self.decoy_alerts

    def _metrics(self, s):
        t, err = self.tick, self.errors(self.tick)[s]
        r = self._rng("metrics", s, t)
        base = r.randint(120, 400)
        m = {"error_rate": round(err, 2), "latency_p99_ms": int(r.uniform(110, 160) * (1 + 6 * err)),
             "cpu_pct": r.randint(28, 46), "mem_pct": r.randint(40, 58),
             "conn_pool_pct": r.randint(18, 40), "requests_per_s": int(base * (1 - err * 0.5)),
             "restarts_1h": 0}
        f = self._active(s, t)
        if f and f.kind == "resource_exhaustion":
            m["cpu_pct"] = r.randint(70, 90)
            m["mem_pct" if f.resource == "mem" else "conn_pool_pct"] = r.randint(95, 99)
        elif f and f.kind == "stuck_process":
            m["cpu_pct"], m["requests_per_s"] = r.randint(0, 2), 0
        return m

    def _logs(self, s, n):
        t, err = self.tick, self.errors(self.tick)
        r = self._rng("logs", s, t // 4)
        lines = []
        f = self._active(s, t)
        if f:
            lines += {
                "bad_deploy": ["ERROR NullPointerException in request handler (build %s)" % self.version(s),
                               "ERROR 500 on POST /v2/%s" % s],
                "bad_config": ["ERROR config key '%s' has invalid value '%s'" % (f.key, f.bad)] * 2,
                "resource_exhaustion": (["ERROR OutOfMemoryError: heap 98% used"] if f.resource == "mem"
                                        else ["WARN connection pool exhausted (max=%s), requests queued"
                                              % self.current_config(s)["max_connections"]]) * 2,
                "stuck_process": ["WARN worker-3 unresponsive for 240s", "WARN liveness probe timed out"],
            }[f.kind]
        for d in self.deps[s]:
            if err[d] >= HEALTHY_BELOW:
                lines += ["ERROR call to %s failed: upstream error rate %d%%" % (d, round(err[d] * 100))] * 2
        noise = ["INFO request completed in %dms" % r.randint(20, 90) for _ in range(8)]
        noise += ["WARN slow query %dms" % r.randint(400, 900)] * r.randint(0, 2)
        r.shuffle(noise)
        lines = lines[:n] + noise[:max(0, n - len(lines))]  # signal is never cut off by n
        r.shuffle(lines)
        return ["%s %s" % (tstr(t - len(lines) + 1 + i), line) for i, line in enumerate(lines)]

    def current_config(self, s):
        cfg = dict(self.config[s])
        for at, key, _, new in sorted(self.config_log[s]):
            if at <= self.tick:
                cfg[key] = new
        return cfg

    def version(self, s):
        return [d for d in sorted(self.deploys[s]) if d[0] <= self.tick][-1][1]

    # ------------------------------------------------------------------ tools
    def call(self, tool, **a):
        if self.done:
            return {"ok": False, "error": "episode is over"}
        if tool == "submit":
            return self._submit(a.get("findings", []))
        if tool == "wait":
            cost = int(clamp(int(a.get("ticks", 1)), 1, 10, ))
        elif tool in COSTS:
            cost = COSTS[tool]
        else:
            return {"ok": False, "error": "unknown tool %r" % tool}
        if self.tick + cost > BUDGET:
            self.finish()
            return {"ok": False, "error": "shift budget exhausted", "episode_over": True}
        s = a.get("service")
        if tool not in ("wait", "list_services", "get_alerts") and s not in self.deps:
            return {"ok": False, "error": "unknown service %r" % s}
        self.trace.append((tool, dict(a)))
        res = self._run(tool, s, a, cost)
        self.tick += cost
        out = {"ok": True, "tick": self.tick, "budget_left": BUDGET - self.tick, "result": res}
        if self.tick >= BUDGET:
            self.finish()
            out["episode_over"] = True
        return out

    def _run(self, tool, s, a, cost):
        if tool == "list_services":
            return [{"service": x, "tier": TIER_NAMES[self.tier[x]]} for x in self.order[::-1]]
        if tool == "get_alerts":
            return self._alerts()
        if tool == "describe_service":
            d = {"service": s, "tier": TIER_NAMES[self.tier[s]], "depends_on": self.deps[s],
                 "depended_on_by": self.dependents[s], "owner": self.owner[s], "version": self.version(s)}
            if s in self.weight:
                d["traffic_weight"] = self.weight[s]
            return d
        if tool == "get_metrics":
            return self._metrics(s)
        if tool == "get_logs":
            return self._logs(s, int(a.get("n", 10)))
        if tool == "get_deploys":
            return [{"at": tstr(t), "version": v, "note": n}
                    for t, v, n in sorted(self.deploys[s]) if t <= self.tick][-5:]
        if tool == "get_config":
            return {"current": self.current_config(s),
                    "changes": [{"at": tstr(t), "key": k, "old": o, "new": n}
                                for t, k, o, n in sorted(self.config_log[s]) if t <= self.tick]}
        if tool == "wait":
            return "waited %d ticks" % cost
        return self._mutate(tool, s, a, cost)

    def _mutate(self, tool, s, a, cost):
        end, f = self.tick + cost, self._open(s)
        useful = False
        if f and tool == "restart" and f.kind == "stuck_process":
            f.fixed_at, useful = end, True
        elif f and tool == "restart" and f.kind == "resource_exhaustion":
            f.relief.append((end, end + RELIEF))
            useful = True  # temporary relief is not penalised, but it does not fix anything
        elif f and tool == "rollback" and f.kind == "bad_deploy":
            f.fixed_at, useful = end, True
        elif f and tool == "scale" and f.kind == "resource_exhaustion":
            f.fixed_at, useful = end, True
        elif f and tool == "set_config" and f.kind == "bad_config" \
                and a.get("key") == f.key and str(a.get("value")) == f.good:
            f.fixed_at, useful = end, True
        if tool == "set_config" and a.get("key") in self.config[s]:
            self.config_log[s].append((end, a["key"], self.current_config(s)[a["key"]], str(a.get("value"))))
        if tool == "rollback":
            prev = [d for d in sorted(self.deploys[s]) if d[0] <= self.tick]
            if len(prev) > 1:
                self.deploys[s].append((end, prev[-2][1], "rollback"))
        if not useful:
            self.wasted += 1
        return "%s issued on %s; takes effect at %s" % (tool, s, tstr(end))

    def _submit(self, findings):
        clean = []
        for fd in list(findings)[:3]:
            if isinstance(fd, dict) and fd.get("service") in self.deps and fd.get("kind") in KINDS:
                clean.append({"service": fd["service"], "kind": fd["kind"]})
        self.findings = clean
        self.trace.append(("submit", {"findings": clean}))
        self.finish()
        return {"ok": True, "episode_over": True}

    # ---------------------------------------------------------------- scoring
    def finish(self):
        if not self.done:
            self.done = True
            self.result = self.score()
        return self.result

    def score(self):
        """Reward from world state at a fixed horizon, independent of when the agent stopped."""
        h = self.health(HORIZON)
        idle = World(self.seed, self.salt).health(HORIZON)
        recovery = 0.0 if idle >= 1 else clamp((h - idle) / (1 - idle))
        truth = {(f.service, f.kind): f for f in self.faults}
        tp = sum(1 for fd in self.findings
                 if (fd["service"], fd["kind"]) in truth and truth[(fd["service"], fd["kind"])].fixed_at is not None)
        fp = sum(1 for fd in self.findings if (fd["service"], fd["kind"]) not in truth)
        diagnosis = clamp((tp - fp) / len(self.faults))
        efficiency = max(0.0, 1 - self.tick / BUDGET)
        collateral = min(0.25, 0.04 * self.wasted)
        reward = clamp(0.70 * recovery + 0.20 * diagnosis + 0.10 * recovery * efficiency - collateral)
        return {"reward": round(reward, 4), "recovery": round(recovery, 4), "diagnosis": round(diagnosis, 4),
                "efficiency": round(efficiency, 4), "wasted_mutations": self.wasted, "ticks_used": self.tick,
                "health_final": round(h, 4), "health_idle": round(idle, 4)}


def replay(seed, trace, salt=None):
    """Recompute the score from a recorded list of (tool, args); used by the verifier."""
    w = World(seed, salt)
    for tool, args in trace:
        w.call(tool, **args)
    return w.finish()
