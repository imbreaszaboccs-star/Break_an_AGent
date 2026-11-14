"""Fault classes F1-F7, F9-F12, F14 (F8 and F13 are scenario axes): planning (scenario time) and behaviour (tick time).

`plan()` returns the truth spec stored in `Scenario.faults`; `build()` turns a spec into a Fault
that mutates the World each tick via `apply`. Nothing here is visible to agents except through
what the simulator shows (metrics, logs, deploys, audit logs, events).
"""

import math

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
    """App nodes (not the entry, not the queue worker) whose failure reaches users: >= min_share of traffic through critical edges."""
    return [n for n in sc.order if sc.nodes[n].kind == "app" and not sc.nodes[n].entry and sc.nodes[n].role != "worker"
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
        self.t_fix = None

    @property
    def visible_at(self):
        """First tick at which the fault shows in the tools (a premature resolve before this is not the agent's fault)."""
        return self.onset - 2

    def cascade(self, w, t):
        """F14 primary: while unfixed it drops 80 % of the requests it would send downstream; the load ramps back over 3 min after the fix."""
        if self.spec.get("cascade") and t >= self.onset:
            if self.fixed(w):
                self.t_fix = t if self.t_fix is None else self.t_fix
                d = max(0.0, 1 - (t - self.t_fix) / 3)
            else:
                d = 1.0
            if d:
                w.drop[self.node] = 0.8 * d

    def apply(self, w, t):
        pass

    def fixed(self, w):
        raise NotImplementedError

    def log_lines(self, w, node, tt, rec, rng):
        return []

    def fix_plan(self):
        """Privileged: [(earliest call time, tool, args)] of the correct (multi-step) fix; oracle policy only."""
        raise NotImplementedError

    def _at(self, tool, args, t=None):
        """Plan step whose effect lands at the onset (the call starts `cost` earlier), never before t=0."""
        from .sim import ACT_COST
        return (max(0, self.onset - ACT_COST[tool] if t is None else t), tool, args)

    def is_fix(self, tool, args):
        """True if this (tool, args) call is a correct fix for this fault (used by tags)."""
        raise NotImplementedError

    def allows(self, tool, args):
        """True for any call that belongs to a correct fix, incl. later steps (used by the unnecessary-action penalty)."""
        return self.is_fix(tool, args)


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
        self.cascade(w, t)

    def fixed(self, w):
        return w.nodes[self.node].version != self.spec["bad_version"]

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["ver"] == self.spec["bad_version"] and rng.random() < .8:
            return [("ERROR", f"unhandled exception in request handler: NullPointerException at "
                              f"com.svc.{node}.Handler.process(Handler.java:{rng.randint(80, 400)}) "
                              f"[build={rec['ver']}]")]
        return []

    def fix_plan(self):
        return [self._at("rollback", {"service": self.node, "version": self.spec["prev_version"]}, self.onset)]

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
        w.add_err(self.node, 0.7 * max(0.0, (nd.mem - 0.85) / 0.15) ** 2)

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

    def fix_plan(self):
        return [self._at("rollback", {"service": self.node, "version": self.spec["prev_version"]}, self.onset)]

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

    def fix_plan(self):
        return [self._at("set_config", {"service": self.node, "key": "max_retries", "value": self.spec["old"]})]

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
        self.cascade(w, t)

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

    def fix_plan(self):
        s = self.spec
        if s["variant"] == "flag":
            return [self._at("set_flag", {"flag": s["flag"], "on": False})]
        return [self._at("set_config", {"service": self.node, "key": "timeout_ms", "value": s["old"]})]

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

    def fix_plan(self):
        return [self._at("set_circuit_breaker", {"service": self.spec["caller"], "dep": self.node, "mode": "fallback"})]

    def is_fix(self, tool, args):
        return (tool == "set_circuit_breaker" and args.get("service") == self.spec["caller"]
                and args.get("dep") == self.node and args.get("mode") == "fallback")


@_reg
class CertExpiry(Fault):
    """Ticking bomb: a WARN well ahead, then TLS handshake failures from t_exp until the cert is rotated."""
    fault_class = "cert_expiry"
    signals = ("get_events", "get_config", "get_logs")

    def __init__(self, spec):
        super().__init__(spec)
        self.started = False

    @property
    def visible_at(self):
        return self.spec["warn_t"]

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if not self.started:
            self.started, nd.cert_exp = True, s["t_exp"]
        if t == s["warn_t"]:
            msg = f"TLS certificate for {self.node} expires at t={s['t_exp']} (in {s['t_exp'] - t} min), renewal not scheduled"
            w.event(t, "warn", "WARN", self.node, f"{self.node}: {msg}")
            w.alerts[("cert", self.node)] = {"severity": "WARN", "service": self.node, "message": msg, "since": t,
                                             "until": s["t_exp"]}
        if t >= s["t_exp"] and not nd.rotated:
            w.add_err(self.node, 1.0)

    def fixed(self, w):
        return w.nodes[self.node].rotated

    def log_lines(self, w, node, tt, rec, rng):
        s = self.spec
        if node != self.node:
            return []
        if tt >= s["t_exp"] and rec["own"] > .99:
            return [("ERROR", f"TLS handshake failure: certificate expired at t={s['t_exp']}")]
        if s["warn_t"] <= tt < s["t_exp"] and rng.random() < .3:
            return [("WARN", f"TLS certificate expires in {s['t_exp'] - tt} min")]
        return []

    def fix_plan(self):
        return [(0, "run_maintenance", {"service": self.node, "action": "rotate_cert"})]

    def is_fix(self, tool, args):
        return tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == "rotate_cert"


@_reg
class DiskFull(Fault):
    """Debug logging fills /var/log: write errors at 98 %. Pruning without lowering the log level refills it."""
    fault_class = "disk_full"
    signals = ("get_events", "get_metrics", "get_logs", "get_config")

    def __init__(self, spec):
        super().__init__(spec)
        self.warned = {}

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t == s["t0"]:
            w.set_cfg(self.node, "log_level", "DEBUG", t, by="dave")
        nd.disk = min(1.0, nd.disk + (.006 if nd.cfg["log_level"] == "DEBUG" else .0004))
        for thr in (.9, .95, .98):
            if nd.disk >= thr and thr not in self.warned:
                self.warned[thr] = t
                w.event(t, "warn", "WARN", self.node, f"{self.node}: disk usage {int(thr * 100)}% on /var/log")
        if nd.disk >= .9:
            w.alerts[("disk", self.node)] = {"severity": "WARN", "service": self.node, "until": t,
                                             "message": f"disk usage {int(nd.disk * 100)}% on /var/log",
                                             "since": self.warned[.9]}
        if nd.disk >= .98:
            w.add_err(self.node, .5)

    def fixed(self, w):
        nd = w.nodes[self.node]
        return nd.disk < .95 and nd.cfg["log_level"] != "DEBUG"

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node:
            return []
        if rec["disk"] >= .98:
            return [("ERROR", "write failed: no space left on device (/var/log)")]
        if rec["disk"] >= .9 and rng.random() < .6:
            return [("WARN", f"disk usage {int(rec['disk'] * 100)}% on /var/log")]
        return []

    def fix_plan(self):
        return [self._at("run_maintenance", {"service": self.node, "action": "prune_logs"}),
                self._at("set_config", {"service": self.node, "key": "log_level", "value": "INFO"})]

    def is_fix(self, tool, args):
        return args.get("service") == self.node and (
            (tool == "run_maintenance" and args.get("action") == "prune_logs")
            or (tool == "set_config" and args.get("key") == "log_level"
                and str(args.get("value")).upper() in ("INFO", "WARN", "ERROR")))


@_reg
class CacheStampede(Fault):
    """The cache is evicted at onset; the db saturates, so the hit rate never recovers by itself (metastable)."""
    fault_class = "cache_stampede"
    signals = ("get_events", "get_metrics", "get_logs")

    def apply(self, w, t):
        if t == self.onset:
            w.nodes[self.node].hit = 0.05
            w.event(t, "warn", "WARN", self.node, f"{self.node}: maxmemory eviction flushed 95% of keys (memory pressure)")

    def fixed(self, w):
        return w.nodes[self.node].hit > .8 and not w.throttled()

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["hit"] < .5 and rng.random() < .8:
            return [("WARN", f"hit ratio {rec['hit']:.0%}: keys evicted, backend load rising")]
        return []

    def fix_plan(self):
        return [self._at("run_maintenance", {"service": self.node, "action": "warm_cache"}, self.onset)] * 3

    def allows(self, tool, args):    # relief by throttling and the later removal of the throttle
        s = self.spec
        return (self.is_fix(tool, args) or (tool == "set_config" and args.get("service") == s["entry"]
                                            and args.get("key") == "rate_limit_rps")
                or (tool == "set_circuit_breaker" and args.get("dep") == s["db"]))

    def is_fix(self, tool, args):
        s = self.spec
        return ((tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == "warm_cache")
                or (tool == "set_config" and args.get("service") == s["entry"] and args.get("key") == "rate_limit_rps"
                    and isinstance(args.get("value"), (int, float)) and args["value"] > 0))


@_reg
class PoisonMessage(Fault):
    """One message at the queue head crashes every worker replica; only the dead-letter queue gets rid of it."""
    fault_class = "poison_message"
    signals = ("get_metrics", "get_logs", "get_traces")

    def apply(self, w, t):
        nd = w.nodes[self.node]
        if t >= self.onset and not nd.cfg["dlq_enabled"]:
            w.cap_mult[self.node] = 0.02
            w.add_err(self.node, .9)
            w.tick_flags[self.node] = "crash"

    def fixed(self, w):
        return bool(w.nodes[self.node].cfg["dlq_enabled"])

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "crash":
            return [("ERROR", f"worker crashed processing msg_id={self.spec['msg_id']} (exit 137), restarting")]
        return []

    def fix_plan(self):
        return [self._at("set_config", {"service": self.node, "key": "dlq_enabled", "value": True})]

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "dlq_enabled"
                and args.get("value") is True)


@_reg
class BadCanary(Fault):
    """A canary release takes `weight` of the node's traffic: 60 % of those requests fail slowly."""
    fault_class = "bad_canary"
    signals = ("get_deploys", "get_flags", "get_metrics", "get_logs")

    def active(self, w):
        return w.flags[self.spec["flag"]]["on"] and w.nodes[self.node].version == self.spec["stable"]

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t == self.onset - 1:
            w.set_flag(s["flag"], True, t, by="release-bot")
            nd.canary = {"version": s["canary_version"], "weight": s["weight"]}
            nd.dlog.append({"version": s["canary_version"], "t": t, "by": "release-bot", "has_schema_migration": False,
                            "reversible": True, "canary_weight": s["weight"]})
            w.event(t, "deploy", "INFO", self.node,
                    f"canary of {self.node} {s['canary_version']} started at {s['weight']:.0%} of traffic (by release-bot)")
        if nd.canary:
            nd.canary["weight"] = s["weight"] if self.active(w) else 0.0
        if t >= self.onset - 1 and self.active(w):
            w.add_err(self.node, s["weight"] * .6)
            w.p99_add[self.node] = w.p99_add.get(self.node, 0.0) + 4000.0
            w.tick_flags[self.node] = "canary"

    def fixed(self, w):
        return not self.active(w)

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "canary" and rng.random() < .7:
            return [("ERROR", f"request failed on canary {self.spec['canary_version']}: upstream timeout after 4000ms")]
        return []

    def fix_plan(self):
        return [self._at("set_flag", {"flag": self.spec["flag"], "on": False})]

    def is_fix(self, tool, args):
        return ((tool == "set_flag" and args.get("flag") == self.spec["flag"] and args.get("on") is False)
                or (tool == "rollback" and args.get("service") == self.node))


@_reg
class ThreadStarvation(Fault):
    """A slow non-critical dependency (0 % errors) ties up the caller's worker threads, so the caller returns 503."""
    fault_class = "thread_starvation"
    signals = ("get_metrics", "get_logs", "get_traces")

    def apply(self, w, t):
        if t >= self.onset:
            w.fault_lat[self.node] = w.fault_lat.get(self.node, 0.0) + self.spec["ms"]

    def fixed(self, w):
        return w.cb[(self.spec["caller"], self.node)] in ("fallback", "open")

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["p99"] > 1500 and rng.random() < .6:
            return [("WARN", f"slow responses: p99 {int(rec['p99'])}ms (pool contention)")]
        return []

    def fix_plan(self):
        return [self._at("set_circuit_breaker", {"service": self.spec["caller"], "dep": self.node, "mode": "fallback"})]

    def is_fix(self, tool, args):
        return (tool == "set_circuit_breaker" and args.get("service") == self.spec["caller"]
                and args.get("dep") == self.node and args.get("mode") in ("fallback", "open"))


@_reg
class UnderProvisioned(Fault):
    """F14 partner B: scaled in by the autoscaler while its upstream A dropped most requests; collapses when A recovers."""
    fault_class = "under_provisioned"
    signals = ("get_events", "get_topology")

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t == self.onset - 1:
            nd.replicas, nd.ready_n = s["small"], min(nd.ready_n, s["small"])
            w.event(t, "scale", "INFO", self.node,
                    f"autoscaler: {self.node} scaled in {s['full']} -> {s['small']} replicas (low load)")

    def fixed(self, w):
        return w.nodes[self.node].replicas >= math.ceil(.8 * self.spec["full"])

    def fix_plan(self):
        return [self._at("scale", {"service": self.node, "replicas": self.spec["full"]}, self.onset)]

    def is_fix(self, tool, args):
        return (tool == "scale" and args.get("service") == self.node and isinstance(args.get("replicas"), int)
                and args["replicas"] >= math.ceil(.8 * self.spec["full"]))


# ---- planning -------------------------------------------------------------------------------

def plan(fam, sc, rng, onset, used, role="primary"):
    spec = PLANNERS[fam](sc, rng, onset, used)
    spec.setdefault("onset", onset)
    spec.update(fault_class=fam, role=role)
    return spec


def _plan_deploy(sc, rng, onset, used, node=None, err=None):
    node = node or _pick(rng, _apps(sc, used, .3))
    prev = sc.deploys[node][-1]["version"]
    return {"node": node, "prev_version": prev, "bad_version": _bump(prev), "err": err or rng.uniform(.3, .6),
            "period": rng.randint(15, 25)}


def _plan_retry(sc, rng, onset, used):
    def w(e):
        return sc.share[e.caller] * e.fanout * ((1 - sc.params["hit_base"]) if e.via_cache else 1)
    x = max((e for e in sc.edges if e.callee == sc.db), key=w).caller
    if x in used:
        raise ValueError("retry client already used")
    return {"node": x, "db": sc.db, "old": 1, "new": 6}


def _slow(p50, p99, limit):
    if p99 <= limit:
        return 0.0
    if limit >= p50:
        return 0.5 * math.log(p99 / limit) / math.log(p99 / p50)
    return 0.5 + 0.5 * (1 - limit / p50)


def _plan_config(sc, rng, onset, used, node=None):
    hit = sc.params["hit_base"]
    new = rng.randint(30, 60)

    def est_err(n):                 # error the timeout would cause at nominal load
        keep = 1.0
        for e in sc.children(n):
            if e.critical:
                c = sc.nodes[e.callee]
                keep *= 1 - e.fanout * ((1 - hit) if e.via_cache else 1) * _slow(sc.p50[e.callee], c.tail * sc.p50[e.callee], new)
        return 1 - keep
    if node:                        # forced node (F14 primary): timeout variant only
        if est_err(node) < .25:
            raise ValueError("timeout drift would not hurt this node")
        return {"node": node, "variant": "timeout", "old": sc.nodes[node].timeout_ms, "new": new}
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


def _plan_cert(sc, rng, onset, used):
    t_exp = rng.randint(55, 75)
    return {"node": _pick(rng, _apps(sc, used, .3)), "t_exp": t_exp, "warn_t": -rng.randint(5, 20), "onset": t_exp}


def _plan_disk(sc, rng, onset, used):
    node = _pick(rng, _apps(sc, used, .3))
    start = rng.uniform(.88, .92)
    # debug logging must start early enough that the disk hits 98 % at the onset (grows .006/tick, .0004 idle)
    k = next(k for k in range(1, 30) if start + .0004 * (onset - k + 30) + .006 * k >= .98)
    sc.nodes[node].disk = start
    return {"node": node, "t0": onset - k}


def _plan_stampede(sc, rng, onset, used):
    if sc.cache in used:
        raise ValueError("cache already used")
    return {"node": sc.cache, "entry": sc.entry, "db": sc.db}


def _plan_poison(sc, rng, onset, used):
    if sc.worker in used:
        raise ValueError("worker already used")
    return {"node": sc.worker, "queue": sc.queue, "msg_id": f"m-{rng.getrandbits(32):08x}"}


def _plan_canary(sc, rng, onset, used):
    node = _pick(rng, _apps(sc, used, .5) or _apps(sc, used, .4))
    prev = sc.deploys[node][-1]["version"]
    fl = rng.choice(sc.flags)           # the canary flag replaces one of the scenario's flags
    sc.flag_audit[:] = [a for a in sc.flag_audit if a["flag"] != fl["name"]]
    fl.update(name=f"{node}-canary", on=False, effect=None)
    return {"node": node, "stable": prev, "canary_version": _bump(prev), "weight": round(rng.uniform(.06, .10), 3),
            "flag": fl["name"]}


def _plan_thread(sc, rng, onset, used):
    """Slow non-critical dep D of a non-entry caller C; C's thread pool is sized so D's 1 s answers starve it."""
    cands = [e for e in sc.edges if not e.critical and e.fallback_ok and e.fanout >= .3
             and sc.nodes[e.caller].kind == "app" and not sc.nodes[e.caller].entry and sc.crit[e.caller] >= .3
             and sc.nodes[e.callee].kind == "app" and sc.nodes[e.callee].role != "worker"
             and e.caller not in used and e.callee not in used]
    e = _pick(rng, cands)
    ms = rng.randint(850, 1050)
    c = sc.nodes[e.caller]
    busy = sc.share[e.caller] * sc.params["base_rps"] * (sc.p50[e.caller] + e.fanout * ms) / 1000
    c.threads = max(2, math.ceil(busy / (c.replicas * 1.8)))        # starved: ~1.8x busy threads once D is slow
    return {"node": e.callee, "caller": e.caller, "ms": ms}


def plan_cascade(sc, rng, onset, used):
    """F14: A (non-entry, dominant caller of B) fails and drops 80 % of requests; B is later found scaled in."""
    cands = [(e.caller, e.callee) for e in sc.edges
             if e.critical and sc.nodes[e.caller].kind == "app" and sc.nodes[e.callee].kind == "app"
             and not sc.nodes[e.caller].entry and sc.nodes[e.callee].role != "worker" and sc.crit[e.caller] >= .3
             and e.caller not in used and e.callee not in used
             and sc.share[e.caller] * e.fanout / sc.share[e.callee] >= .5]
    a, b = _pick(rng, cands)
    nb = sc.nodes[b]
    full = rng.choice((3, 6))           # B is sized for u=.5 at `full` replicas; the autoscaler leaves it u=1.5 at full load
    nb.replicas = full
    nb.cap = max(20, math.ceil(sc.share[b] * sc.params["base_rps"] / (full * .5)))
    nb.threads = max(20, 2 * nb.cap)
    sa = None
    if rng.random() < .35:
        try:
            sa = _plan_config(sc, rng, onset, used, node=a)
            sa.update(fault_class="config_drift", onset=onset)
        except ValueError:
            sa = None
    if sa is None:
        sa = _plan_deploy(sc, rng, onset, used, node=a, err=.8)
        sa.update(fault_class="bad_deploy", onset=onset)
    sa.update(cascade=True, partner=b, role="primary")
    sb = {"node": b, "partner": a, "full": full, "small": max(1, full // 3), "fault_class": "under_provisioned",
          "onset": onset, "role": "cascade"}
    return [sa, sb]


PLANNERS = {"bad_deploy": _plan_deploy, "memory_leak": _plan_deploy, "retry_storm": _plan_retry,
            "config_drift": _plan_config, "external_dependency": _plan_external, "cert_expiry": _plan_cert,
            "disk_full": _plan_disk, "cache_stampede": _plan_stampede, "poison_message": _plan_poison,
            "bad_canary": _plan_canary, "thread_starvation": _plan_thread}


def build(spec):
    return CLASSES[spec["fault_class"]](spec)
