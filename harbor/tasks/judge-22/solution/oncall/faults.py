"""Fault classes F1-F7, F9-F12, F14 (F8 and F13 are scenario axes) and R1-R14 (v2 real incidents): planning (scenario time) and behaviour (tick time).

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


def _take_flag(sc, rng, name, on=False):
    """Rename one of the scenario's still unused flags into the fault's flag (so no two faults share a flag)."""
    fl = rng.choice([f for f in sc.flags if not f.get("locked")])
    sc.flag_audit[:] = [a for a in sc.flag_audit if a["flag"] != fl["name"]]
    fl.update(name=name, on=on, effect=None, locked=True)
    return fl


def _pick(rng, cands):
    if not cands:
        raise ValueError("no candidate node")
    return rng.choice(cands)


def inst_name(node, i):
    return f"{node}-{i + 1}"


# role of the billing / token-validating / mail-sending service per template (R1, R6, R7)
BILLER = {"eshop": "checkout", "saas": "billing", "media": "accounts"}
AUTHN = {"eshop": "cart", "saas": "auth", "media": "accounts"}
SENDER = {"eshop": "orders", "saas": "notify", "media": "worker"}
ADMINS = ("alice", "bob", "carol", "dave")


def _role(sc, table):
    return next(n for n in sc.order if sc.nodes[n].role == table[sc.template])


def _reg(cls):
    CLASSES[cls.fault_class] = cls
    return cls


class Fault:
    fault_class = ""
    signals = ()        # tools whose output shows the fault (>= 2)
    silent = False      # harms users with 200s only (SLI harm): error / latency dashboards stay green

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

    def dataloss(self, w, tool, args):
        """Message if this (destructive) action loses data while the fault is active, else None."""
        return None

    def impaired(self, w, node, idx):
        """True if instance `idx` of `node` is impaired by this fault right now (draining it is a legitimate step)."""
        return False

    def failover_ok(self, w):
        """True if a failover_db issued now is a correct step of this fault's fix."""
        return False


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
        if node == self.node and rec["ver"] == self.spec["bad_version"] and rng.random() < .35:
            return [("ERROR", f"unhandled exception in request handler: NullPointerException at "
                              f"com.svc.{node}.Handler.process(Handler.java:{rng.randint(80, 400)})")]
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
        elif rec["mem"] > .6 and rng.random() < .4:
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
        if node == self.node and rec["ce"].get(self.spec["db"], 0) > .05 and rng.random() < .4:
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
        if node == self.node and s["variant"] == "flag" and w.flags[s["flag"]]["on"] and rng.random() < .4:
            return [("WARN", f"slow request dur={rng.randint(900, 1600)}ms path=/v1/items")]
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
        if rec["disk"] >= .9 and rng.random() < .4:
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
        if node == self.node and rec["hit"] < .5 and rng.random() < .4:
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
        if node == self.node and rec["flag"] == "crash" and rng.random() < .7:
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
        if node == self.node and rec["flag"] == "canary" and rng.random() < .4:
            return [("ERROR", "request failed: upstream timeout after 4000ms")]
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
        if node == self.node and rec["p99"] > 1500 and rng.random() < .4:
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


# ---- v2: real-incident mechanisms (R1-R7) -----------------------------------------------------

@_reg
class DuplicateCharges(Fault):
    """R1, Twilio billing 2013: https://www.twilio.com/en-us/blog/company/communications/billing-incident-post-mortem-breakdown-analysis-and-root-cause-html"""
    fault_class = "duplicate_charges"
    signals = ("get_business_metrics", "get_logs", "get_metrics", "get_config")
    silent = True
    PERIOD, LEN = 40, 22     # a network blip makes the cache replica resync every PERIOD min, the storm lasts LEN min

    def __init__(self, spec):
        super().__init__(spec)
        self.init = False

    def storm(self, t):
        return t >= self.onset and (t - self.onset) % self.PERIOD < self.LEN

    def apply(self, w, t):
        s = self.spec
        biller, flag = w.nodes[s["biller"]], w.flags["auto-recharge"]
        if not self.init:       # balances are read from the cache replica (set long ago)
            self.init = True
            biller.cfg["read_from"] = "replica"
            biller.audit.append({"t": -s["age"], "key": "read_from", "old": "primary", "new": "replica", "by": s["by"]})
        if self.storm(t):
            k = (t - self.onset) % self.PERIOD
            if k == 0:
                w.event(t, "warn", "WARN", self.node, f"{self.node}: replication link flapped (packet loss 18s), "
                                                      f"replica requested a full resync")
            w.xm.setdefault(self.node, {})["repl_backlog_mb"] = float(min(900, 60 * (k + 1)))
            w.cpu_add[self.node] = .35
            w.tick_flags[self.node] = "storm"
            if biller.cfg["read_from"] == "replica" and flag["on"]:      # zero balances -> auto-recharge charges again
                w.dup += s["frac"]
                w.harm += s["frac"]
                w.tick_flags[s["biller"]] = "dup"
        if not flag["on"]:
            w.harm += .04           # ponytail: the price of the mitigation: accounts that run dry are suspended

    def fixed(self, w):
        return w.nodes[self.spec["biller"]].cfg["read_from"] == "primary" and w.flags["auto-recharge"]["on"]

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.spec["biller"] and rec["flag"] == "dup" and rng.random() < .5:
            return [("WARN", f"balance 0 for account acct_{rng.randint(10000, 99999)}, triggering auto-recharge "
                             f"({rng.choice((25, 50, 100))} USD)")]
        if node == self.node and rec["flag"] == "storm":
            return ([("WARN", "replica lost connection to master, full resync requested")] * (rng.random() < .5)
                    + [("ERROR", "client-output-buffer-limit reached for replica, closing connection")] * (rng.random() < .3))
        return []

    def dataloss(self, w, tool, args):
        if tool == "restart" and args.get("service") == self.node and not self.fixed(w):
            return "restarted the cache primary during the resync storm: balances lost"

    def fix_plan(self):
        return [self._at("set_config", {"service": self.spec["biller"], "key": "read_from", "value": "primary"}, self.onset)]

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") == self.spec["biller"] and args.get("key") == "read_from"
                and args.get("value") == "primary")

    def allows(self, tool, args):       # stop the harm (flag off), fix the read path, re-enable
        return self.is_fix(tool, args) or (tool == "set_flag" and args.get("flag") == "auto-recharge")


@_reg
class ReplicaLagStaleReads(Fault):
    """R2, GitHub 2018-10-21 (https://github.blog/2018-10-30-oct21-post-incident-analysis) and Honeycomb 2023-07-25 (https://www.honeycomb.io/blog/incident-review-what-comes-up-must-first-go-down)"""
    fault_class = "replica_lag_stale_reads"
    signals = ("get_metrics", "get_logs", "get_business_metrics", "get_config")
    silent = True

    def __init__(self, spec):
        super().__init__(spec)
        self.init, self.lag = False, 0.0

    def apply(self, w, t):
        s = self.spec
        if not self.init:       # these clients offload reads to the replica (set long ago)
            self.init = True
            for c in s["clients"]:
                w.nodes[c].cfg["read_from"] = "replica"
                w.nodes[c].audit.append({"t": -s["age"], "key": "read_from", "old": "primary", "new": "replica",
                                         "by": s["by"]})
        if t >= self.onset:     # a runaway query holds back replication apply
            self.lag = (self.lag * .5 if self.lag >= 3 else 0.0) if self.healed(w) else min(s["max"], self.lag + s["rate"])
        w.db_lag = self.lag
        w.xm.setdefault(self.node, {})["replica_lag_s"] = round(self.lag, 1)
        aff = [c for c in s["clients"] if w.nodes[c].cfg["read_from"] == "replica"]
        stale = min(.4, .3 * sum(w.sc.share[c] for c in aff)) * min(1.0, self.lag / 90)
        if stale > 0.005:
            w.stale += stale
            w.harm += stale
            for c in aff:
                w.tick_flags[c] = "stale"
        if self.lag > 30:
            w.tick_flags[self.node] = "lag"

    def healed(self, w):        # the runaway query is gone (killed, or the replica was promoted)
        db = w.nodes[self.node]
        return "kill_long_queries" in db.maint or db.failovers > 0

    def fixed(self, w):         # no user reads stale data any more (the replica may still lag)
        return self.healed(w) or all(w.nodes[c].cfg["read_from"] == "primary" for c in self.spec["clients"])

    def log_lines(self, w, node, tt, rec, rng):
        if node in self.spec["clients"] and rec["flag"] == "stale" and rng.random() < .5:
            return [("WARN", f"order ord_{rng.randint(100000, 999999)} not found right after create (read replica)")]
        if node == self.node and rec["flag"] == "lag" and rng.random() < .4:
            return [("WARN", f"replica apply blocked by long-running query pid={rng.randint(1000, 9999)} "
                             f"(running {rng.randint(20, 90)}m), lag {int(rec['x']['replica_lag_s'])}s")]
        return []

    def fix_plan(self):
        return [self._at("run_maintenance", {"service": self.node, "action": "kill_long_queries"}, self.onset)]

    def is_fix(self, tool, args):
        return ((tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == "kill_long_queries")
                or (tool == "set_config" and args.get("service") in self.spec["clients"] and args.get("key") == "read_from"
                    and args.get("value") == "primary"))


@_reg
class MigrationLock(Fault):
    """R3, Pulumi 2023-10-06: https://www.pulumi.com/blog/post-mortem-2023-10-06/"""
    fault_class = "migration_lock"
    signals = ("get_metrics", "get_logs", "get_deploys")

    def locked(self, w):
        return "cancel_migration" not in w.nodes[self.node].maint

    def apply(self, w, t):
        s, db, dn = self.spec, w.nodes[self.node], w.nodes[self.spec["deploy_node"]]
        if t == self.onset - 1:
            w.deploy(s["deploy_node"], s["bad_version"], t, by="ci-bot", migration=True)
        entry = next((d for d in dn.dlog if d["version"] == s["bad_version"] and d["by"] == "ci-bot"), None)
        if t < self.onset:
            return
        if entry is not None:
            entry["migration_in_progress"] = self.locked(w)
        # ponytail: the migration job reconnects after a db restart / failover, so only cancel_migration releases the lock
        if self.locked(w):
            relief = t - db.maint.get("kill_long_queries", -99) < 3     # killing the waiters only helps for a moment
            ramp = min(1.0, (t - self.onset + 1) / 4)
            w.xm.setdefault(self.node, {})["locks_waiting"] = float(6 if relief else int(190 * ramp))
            w.cpu_add[self.node] = -.55 * ramp              # the db is idle: its sessions wait on a lock
            if not relief:
                w.add_err(self.node, .75 * ramp)
                w.tick_flags[self.node] = "lock"
        elif dn.version == s["bad_version"]:        # the new code needs the schema change that was cancelled
            w.add_err(s["deploy_node"], .4)

    def fixed(self, w):
        return not self.locked(w) and w.nodes[self.spec["deploy_node"]].version != self.spec["bad_version"]

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "lock" and rng.random() < .5:
            return [("WARN", f"process {rng.randint(1000, 9999)} still waiting for ShareLock on relation "
                             f"{rng.randint(16000, 16999)} after 1000.{rng.randint(10, 99)} ms")] + [
                ("ERROR", "canceling statement due to lock timeout")] * (rng.random() < .4)
        if node != self.node and rec["ce"].get(self.node, 0) > .05 and rng.random() < .6:
            return [("ERROR", "lock wait timeout exceeded; try restarting transaction")]
        return []

    def fix_plan(self):
        s = self.spec
        return [self._at("run_maintenance", {"service": self.node, "action": "cancel_migration"}, self.onset),
                self._at("rollback", {"service": s["deploy_node"], "version": s["prev_version"]}, self.onset)]

    def is_fix(self, tool, args):
        s = self.spec
        return ((tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == "cancel_migration")
                or (tool == "rollback" and args.get("service") == s["deploy_node"] and args.get("version") != s["bad_version"]))

    def allows(self, tool, args):
        return self.is_fix(tool, args) or (tool == "run_maintenance" and args.get("service") == self.node
                                           and args.get("action") == "kill_long_queries")


@_reg
class PoolSyncRecycle(Fault):
    """R4, Clerk 2025-09: https://clerk.com/blog/2025-09-18-database-incident-postmortem"""
    fault_class = "pool_sync_recycle"
    signals = ("get_metrics", "get_events", "get_logs")
    PERIOD, LEN = 15, 2      # pooled connections have a 15 min lifetime and recycle in sync: a 2 min burst each cycle

    def phase0(self, w):
        r = [x for x in w.nodes[self.node].restarts if x >= self.onset]
        return max(r) if r else self.onset      # a db restart re-aligns every client: the cycle only shifts

    def burst(self, w, t):
        p = self.phase0(w)
        return t >= p and (t - p) % self.PERIOD < self.LEN

    def unjittered(self, w):
        cl = self.spec["clients"]
        pool = {c: w.nodes[c].replicas * w.nodes[c].cfg["pool_size"] for c in cl}
        return sum(x for c, x in pool.items() if w.nodes[c].cfg["conn_lifetime_jitter"] != "on") / sum(pool.values())

    def apply(self, w, t):
        s = self.spec
        if t == self.onset - 2:
            w.event(t, "warn", "WARN", self.node, f"{self.node}: minor version upgraded {s['old']} -> {s['new']} "
                                                  f"(automatic maintenance window)")
        if t == self.onset:         # coincidences that look like causes
            w.event(t, "warn", "WARN", s["bot"], f"{s['bot']}: signup rate 3.2x baseline over the last 10 min (possible bot traffic)")
            w.event(t, "warn", "WARN", s["cron"], f"{s['cron']}: scheduled job reports-rollup started")
        if self.burst(w, t):
            u = self.unjittered(w)
            if u > 0:
                w.add_err(self.node, .9 * u)
                w.tick_flags[self.node] = "burst"

    def fixed(self, w):
        return self.unjittered(w) == 0

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "burst" and rng.random() < .8:
            return [("ERROR", "FATAL: sorry, too many clients already")] * rng.randint(1, 3)
        if node in self.spec["clients"] and w.rec[tt + 30][self.node]["flag"] == "burst" and rng.random() < .6:
            return [("ERROR", "connect to database failed: too many clients already")]
        return []

    def fix_plan(self):
        return [self._at("set_config", {"service": c, "key": "conn_lifetime_jitter", "value": "on"}, self.onset)
                for c in self.spec["clients"]]

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") in self.spec["clients"]
                and args.get("key") == "conn_lifetime_jitter" and args.get("value") == "on")


@_reg
class ProgressiveGray(Fault):
    """R5, Netlify 2021-03-25: https://www.netlify.com/blog/2021/04/02/load-balancer-service-degradation-march-25-2021.md"""
    fault_class = "progressive_gray"
    signals = ("get_instances", "get_events", "get_metrics")
    PERIOD = 15              # one more instance loses its load-balancer route every PERIOD min

    def bad(self, w, t):
        k = 0 if t < self.onset else min(len(self.spec["order"]), 1 + (t - self.onset) // self.PERIOD)
        return set() if self.fixed(w) else {i for i in self.spec["order"][:k] if i < w.nodes[self.node].replicas}

    def apply(self, w, t):
        nd = w.nodes[self.node]
        if t == self.onset - 1:
            w.event(t, "info", "INFO", self.node, f"{self.node}: unattended-upgrades ran on the fleet (package updates applied)")
        if t == self.onset + 4:
            w.event(t, "message", "info", "status-feed",
                    "cloud provider status: elevated API latency in the network control plane (investigating)")
        bad = self.bad(w, t)
        live = [i for i in bad if i not in nd.drained]
        if bad:
            w.inst[self.node] = {i: {"err": 1.0, "p50": 3.0, "cpu": .02} for i in bad}
        if live:
            w.add_err(self.node, len(live) / max(1, w.lb_n(nd)))
            w.tick_flags[self.node] = "gray"

    def fixed(self, w):
        return "restart_networkd" in w.nodes[self.node].maint

    def impaired(self, w, node, idx):
        return node == self.node and idx in self.bad(w, w.t)

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "gray" and rng.random() < .5:
            return [("ERROR", "connect() failed (113: No route to host) while connecting to upstream")]
        return []

    def fix_plan(self):
        return [self._at("run_maintenance", {"service": self.node, "action": "restart_networkd"}, self.onset)]

    def is_fix(self, tool, args):
        return tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == "restart_networkd"


@_reg
class ClockSkew(Fault):
    """R6, Cloudflare 2017 leap second: https://blog.cloudflare.com/how-and-why-the-leap-second-affected-cloudflare-dns/"""
    fault_class = "clock_skew"
    signals = ("get_instances", "get_logs", "get_business_metrics")
    silent = True

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t == self.onset + 4:
            w.event(t, "message", "info", "support", "support: users report being logged out at random")
        if t >= self.onset and not self.fixed(w) and s["idx"] < nd.replicas:   # 401s are 4xx: no error-rate alert, users are harmed
            frac = .9 * w.sc.share[self.node] / max(1, w.lb_n(nd))
            w.harm += frac
            w.login_fail += frac
            w.inst[self.node] = {s["idx"]: {"clock": s["offset_ms"]}}
            w.tick_flags[self.node] = "skew"

    def fixed(self, w):
        nd = w.nodes[self.node]
        return "sync_clock" in nd.maint or self.spec["idx"] in nd.drained

    def impaired(self, w, node, idx):
        return node == self.node and idx == self.spec["idx"] and not self.fixed(w)

    def log_lines(self, w, node, tt, rec, rng):
        s = self.spec
        if node == self.node and rec["flag"] == "skew" and rng.random() < .6:
            if s["offset_ms"] < 0:
                return [("ERROR", f"token validation failed: token not yet valid (nbf in the future by {rng.randint(60, 600)}s)")]
            return [("ERROR", f"token validation failed: token expired {rng.randint(60, 600)}s ago")]
        if (node != self.node and any(e.caller == node and e.callee == self.node for e in w.sc.edges)
                and w.rec[tt + 30][self.node]["flag"] == "skew" and rng.random() < .5):
            return [("WARN", f"upstream {self.node} returned 401 Unauthorized for a valid session")]
        return []

    def fix_plan(self):
        return [self._at("run_maintenance", {"service": self.node, "action": "sync_clock"}, self.onset)]

    def is_fix(self, tool, args):
        return ((tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == "sync_clock")
                or (tool == "drain_instance" and args.get("service") == self.node
                    and args.get("instance") == inst_name(self.node, self.spec["idx"])))


@_reg
class ExpiredCertDismissedAlert(Fault):
    """R7, Postmark 2024-09-16 (https://postmarkapp.com/blog/outbound-smtp-outage-on-september-15-2024) and Let's Encrypt 2021 (https://letsencrypt.org/docs/dst-root-ca-x3-expiration-september-2021)"""
    fault_class = "expired_cert_dismissed_alert"
    signals = ("get_logs", "get_business_metrics", "get_events", "get_config")
    silent = True

    def __init__(self, spec):
        super().__init__(spec)
        self.init = False

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if not self.init:
            self.init = True
            if s["variant"] == "cert":
                nd.cert_exp = self.onset
            else:
                nd.ca = s["old_ca"]
        if t == self.onset + 2:
            w.event(t, "message", "info", "status-feed", "mail provider status: all systems operational")
        if t < self.onset or self.fixed(w):
            return
        w.mail_ok = .03
        w.harm += s["frac"]         # receipts and password-reset mails never arrive
        w.tick_flags[self.node] = "tls"
        k = (t - self.onset) % 12   # the synthetic check flaps: it looks like a flaky probe
        msg = "synthetic check smtp-starttls failed (3 consecutive probes)"
        if k < 7:
            if k == 0:
                w.event(t, "warn", "WARN", self.node, f"{self.node}: {msg}")
            w.alerts[("synthetic", self.node)] = {"severity": "WARN", "service": self.node, "since": t - k, "until": t,
                                                  "message": msg}
        elif k == 7:
            w.event(t, "resolved", "INFO", self.node, f"{self.node}: synthetic check smtp-starttls recovered")

    def fixed(self, w):
        nd = w.nodes[self.node]
        return nd.rotated if self.spec["variant"] == "cert" else "update_ca_bundle" in nd.maint

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node or rec["flag"] != "tls":
            return []
        out = []
        if rng.random() < .5:
            why = ("certificate has expired (10)" if self.spec["variant"] == "cert"
                   else "unable to get local issuer certificate (20)")
            out.append(("ERROR", f"smtp: TLS handshake with mx.provider.example failed: certificate verify failed: {why}"))
        if rng.random() < .3:
            out.append(("WARN", f"mail queue: deferring {rng.randint(20, 400)} messages, retry in 300s"))
        return out

    def fix_plan(self):
        act = "rotate_cert" if self.spec["variant"] == "cert" else "update_ca_bundle"
        return [self._at("run_maintenance", {"service": self.node, "action": act}, self.onset)]

    def is_fix(self, tool, args):
        act = "rotate_cert" if self.spec["variant"] == "cert" else "update_ca_bundle"
        return tool == "run_maintenance" and args.get("service") == self.node and args.get("action") == act

    def allows(self, tool, args):
        return (tool == "run_maintenance" and args.get("service") == self.node
                and args.get("action") in ("rotate_cert", "update_ca_bundle"))


@_reg
class MailBacklogRamp(Fault):
    """R8, Postmark 2022-12-16: https://postmarkapp.com/blog/email-delays-december-16-2022"""
    fault_class = "mail_backlog_ramp"
    signals = ("get_business_metrics", "get_metrics", "get_events", "get_logs")
    silent = True
    # ponytail: receivers tolerate up to LIMIT x the normal mail volume; sending faster than that makes them defer almost everything
    # and the penalty (reputation) lingers: each tick above the limit adds COOL minutes of throttling, so full-rate draining is metastable.
    LIMIT, COOL, DEGRADED = 4.0, 3, .03

    def __init__(self, spec):
        super().__init__(spec)
        self.backlog, self.cool, self.purged, self.q = 0.0, -10 ** 9, -1, 1.0

    def rate(self, w):
        return w.nodes[self.node].cfg["send_rate_per_s"]

    def apply(self, w, t):
        from .scenarios import T
        s, nd = self.spec, w.nodes[self.node]
        t_rec = self.onset + s["dur"]
        if t == self.onset:
            w.event(t, "warn", "WARN", self.node, f"{self.node}: outbound mail provider degraded: delivery capacity "
                                                  f"reduced, messages are queueing")
        if t == t_rec:
            w.event(t, "info", "INFO", self.node, f"{self.node}: mail provider status: capacity restored; receivers are "
                                                   f"throttling large bursts, ramp sending up gradually")
        if t < self.onset:
            return
        nom0 = s["nom"]
        nom = nom0 * (1.5 if t >= T else 1.0)
        if nd.maint.get("purge_dlq", -1) > self.purged:        # the queue was purged: that mail is gone
            self.purged, self.backlog = nd.maint["purge_dlq"], 0.0
        avail = self.backlog + nom
        rate = self.rate(w)
        att = min(avail, rate if rate > 0 else 20 * nom0)
        acc = min(att, self.DEGRADED * nom0) if t < t_rec else att
        if t >= t_rec and att > self.LIMIT * nom0:
            self.cool = min(t + 30, max(self.cool, t) + self.COOL)
        throttled = t < self.cool
        deliv, bounce = (.1 * acc, .1 * acc) if throttled else (acc, 0.0)
        self.backlog = avail - deliv - bounce
        self.q = min(1.0, max(.03, deliv / avail))             # share of the mail wanting out that actually arrives now
        w.mail_ok = self.q
        w.harm += s["frac"] * (1 - self.q)                      # receipts / password resets that do not arrive
        w.mail = {"emails_sent": att, "emails_delivered": deliv, "emails_deferred": att - deliv - bounce + .01 * att,
                  "emails_bounced": bounce + .005 * att}
        w.xm.setdefault(self.node, {})["mail_lag"] = self.backlog / nom0
        w.tick_flags[self.node] = ("mail_throttle" if throttled else "mail_down" if t < t_rec
                                   else "mail_drain" if self.backlog > nom0 else "")

    def fixed(self, w):
        r = self.rate(w)
        return 0 < r <= self.LIMIT * self.spec["nom"] and self.backlog < 1.5 * self.spec["nom"]

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node:
            return []
        if rec["flag"] == "mail_down" and rng.random() < .6:
            return [("WARN", f"smtp: provider returned 421 4.7.0 try again later, deferring {rng.randint(20, 400)} messages")]
        if rec["flag"] == "mail_throttle" and rng.random() < .7:
            return [("WARN", f"smtp: 451 4.7.1 too many messages from this sender, receiver is rate limiting; "
                             f"deferring {rng.randint(100, 900)} messages")]
        if rec["flag"] == "mail_drain" and rng.random() < .3:
            return [("INFO", f"mail queue: {int(rec['lag'] * 60)} messages pending")]
        return []

    def dataloss(self, w, tool, args):
        if (tool == "run_maintenance" and args.get("action") == "purge_dlq" and args.get("service") == self.node
                and self.backlog > self.spec["nom"]):
            return "purged the mail queue: queued receipts and password-reset mails are lost"

    def fix_plan(self):
        return [self._at("set_config", {"service": self.node, "key": "send_rate_per_s",
                                        "value": math.ceil(3 * self.spec["nom"])}, self.onset)]

    def is_fix(self, tool, args):
        v = args.get("value")
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "send_rate_per_s"
                and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= self.LIMIT * self.spec["nom"])

    def allows(self, tool, args):       # ramping up in steps
        return self.is_fix(tool, args) or (tool == "set_config" and args.get("service") == self.node
                                           and args.get("key") == "send_rate_per_s")


@_reg
class CacheInvalidationLoop(Fault):
    """R9, Facebook 2010-09-23: https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/"""
    fault_class = "cache_invalidation_loop"
    signals = ("get_metrics", "get_config", "get_logs")

    def bad(self, w):
        return w.nodes[self.node].cfg["timeout_ms"] < self.spec["old"] / 2

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t == self.onset - 1:
            w.set_cfg(self.node, "timeout_ms", s["new"], t, by=s["by"])
        if t < self.onset:
            return
        # ponytail: clients that see an invalid value, or a db error, delete the key and refill it from the db: the loop closes
        # through the db error rate, so reverting the value alone does not stop it (the db stays saturated -> more deletes)
        x = min(1.0, max(0.0, (w.err[s["db"]] - .1) / .2))
        dele = (.4 if self.bad(w) else 0.0) + .5 * x
        if dele > 0:
            nd.hit = max(0.0, nd.hit * (1 - dele))
            w.tick_flags[self.node] = "loop"
        w.xm.setdefault(self.node, {})["key_deletes_per_s"] = 35 + 5000 * dele

    def recovered(self, w):
        nd = w.nodes[self.node]
        return not self.bad(w) and nd.hit >= nd.sp.hit_base - .02          # back to the normal hit rate: the db copes again

    def fixed(self, w):
        return self.recovered(w) and not w.throttled()

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "loop" and rng.random() < .6:
            return [("WARN", f"client-initiated DEL burst: {int(rec['x']['key_deletes_per_s'] * 60)} keys deleted in the last 60s")]
        if rec["flag"] != "loop" or node == self.node or rng.random() > .5:
            return []
        if any(e.caller == node and e.callee == self.node for e in w.sc.edges):
            return [("WARN", f"cache entry sess:{rng.getrandbits(24):06x} failed validation, deleting key and reloading from backing store")]
        return []

    def fix_plan(self):
        s = self.spec
        return [self._at("set_config", {"service": s["entry"], "key": "rate_limit_rps", "value": s["shed"]}, self.onset),
                self._at("set_config", {"service": self.node, "key": "timeout_ms", "value": s["old"]}, self.onset),
                (max(0, self.onset) + 3, "set_config", {"service": s["entry"], "key": "rate_limit_rps", "value": 0}, self.recovered)]

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "timeout_ms"
                and isinstance(args.get("value"), int) and args["value"] >= self.spec["old"] / 2)

    def allows(self, tool, args):       # shed load, revert, remove the limit again
        s = self.spec
        return (self.is_fix(tool, args) or (tool == "set_config" and args.get("service") == s["entry"]
                                            and args.get("key") == "rate_limit_rps")
                or (tool == "set_circuit_breaker" and args.get("dep") == s["db"]))


@_reg
class BadConfigPush(Fault):
    """R10, Cloudflare 2019-07-02: https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/"""
    fault_class = "bad_config_push"

    @property
    def signals(self):
        return (("get_flags" if self.spec["variant"] == "flag" else "get_config"), "get_metrics", "get_logs")

    def apply(self, w, t):
        s = self.spec
        if t == self.onset - 1:
            if s["variant"] == "flag":
                w.set_flag(s["flag"], True, t, by=s["by"])
            else:
                w.set_cfg(self.node, "waf_ruleset", "candidate", t, by=s["by"])
        if t >= self.onset and not self.fixed(w):
            # ponytail: a catastrophic-backtracking rule costs ~25x CPU per request; more replicas cannot make up for that
            w.cap_mult[self.node] = w.cap_mult.get(self.node, 1.0) * .04
            w.tick_flags[self.node] = "regex"

    def fixed(self, w):
        s = self.spec
        return (not w.flags[s["flag"]]["on"]) if s["variant"] == "flag" else w.nodes[self.node].cfg["waf_ruleset"] == "stable"

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "regex" and rng.random() < .5:
            return [("WARN", f"waf: rule rx-{rng.randint(100, 999)} exceeded the 50ms evaluation budget (backtrack limit)"),
                    ("WARN", "worker cpu 100% for 60s")][:rng.randint(1, 2)]
        return []

    def fix_plan(self):
        s = self.spec
        if s["variant"] == "flag":
            return [self._at("set_flag", {"flag": s["flag"], "on": False}, self.onset)]
        return [self._at("set_config", {"service": self.node, "key": "waf_ruleset", "value": "stable"}, self.onset)]

    def is_fix(self, tool, args):
        s = self.spec
        if s["variant"] == "flag":
            return tool == "set_flag" and args.get("flag") == s["flag"] and args.get("on") is False
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "waf_ruleset"
                and args.get("value") == "stable")


@_reg
class RedisMaxmemory(Fault):
    """R11, GitLab production#482: https://gitlab.com/gitlab-com/gl-infra/production/-/issues/482"""
    fault_class = "redis_maxmemory"
    signals = ("get_metrics", "get_config", "get_business_metrics", "get_logs")

    def __init__(self, spec):
        super().__init__(spec)
        self.init, self.storm = False, 0.0

    def active(self, w):
        return not self.fixed(w)

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if not self.init:
            self.init = True
            if s["variant"] == "policy":       # sessions carry no TTL: only volatile-lru keeps them
                nd.cfg["maxmemory_policy"] = "volatile-lru"
        if t == self.onset - 1:
            if s["variant"] == "shrink":
                w.set_cfg(self.node, "maxmemory_mb", s["new_mb"], t, by=s["by"])
            else:
                w.set_cfg(self.node, "maxmemory_policy", "allkeys-lru", t, by=s["by"])
        if t < self.onset:
            return
        # ponytail: the storm builds at once while keys are evicted and fades over ~5 min once memory is sufficient again
        self.storm = 1.0 if self.active(w) else self.storm * .7
        if self.storm < .05:
            return
        ev = w.xm.setdefault(self.node, {})
        ev["evicted_keys"] = 2600 * self.storm
        ev["used_memory_ratio"] = .62 + .38 * self.storm
        w.login_fail += .3 * self.storm
        w.harm += .12 * self.storm                       # sessions are gone: users are logged out
        w.xmul[s["auth"]] = 1 + 1.5 * self.storm          # everybody logs in again at once
        w.tick_flags[self.node] = "evict"
        w.tick_flags[s["auth"]] = "storm"
        if self.active(w):
            nd.hit = min(nd.hit, .85 * nd.sp.hit_base)

    def fixed(self, w):
        s, cfg = self.spec, w.nodes[self.node].cfg
        if s["variant"] == "policy":
            return cfg["maxmemory_policy"] == "volatile-lru"
        return cfg["maxmemory_mb"] >= .8 * s["old_mb"] or cfg["maxmemory_policy"] == "volatile-lru"

    def log_lines(self, w, node, tt, rec, rng):
        if node == self.node and rec["flag"] == "evict" and rng.random() < .6:
            cfg = w.nodes[node].cfg
            return [("WARN", f"used_memory at maxmemory ({cfg['maxmemory_mb']}mb): evicted {int(rec['x']['evicted_keys'])} keys "
                             f"in the last 60s (policy {cfg['maxmemory_policy']})")]
        if node == self.spec["auth"] and rec["flag"] == "storm" and rng.random() < .6:
            return [("WARN", f"session tok_{rng.getrandbits(32):08x} not found, forcing re-login")]
        return []

    def dataloss(self, w, tool, args):
        if tool == "restart" and args.get("service") == self.node and self.active(w):
            return "restarted the session cache while it was evicting: all sessions lost"

    def fix_plan(self):
        s = self.spec
        if s["variant"] == "policy":
            return [self._at("set_config", {"service": self.node, "key": "maxmemory_policy", "value": "volatile-lru"}, self.onset)]
        return [self._at("set_config", {"service": self.node, "key": "maxmemory_mb", "value": s["old_mb"]}, self.onset)]

    def is_fix(self, tool, args):
        s = self.spec
        if tool != "set_config" or args.get("service") != self.node:
            return False
        if args.get("key") == "maxmemory_policy" and args.get("value") == "volatile-lru":
            return True
        return (s["variant"] == "shrink" and args.get("key") == "maxmemory_mb" and isinstance(args.get("value"), int)
                and args["value"] >= .8 * s["old_mb"])


@_reg
class DuplicateEvents(Fault):
    """R12, CircleCI 2025-12-02: https://status.circleci.com/incidents/kvzp8x242n34"""
    fault_class = "duplicate_events"
    silent = True
    SHIP = .12      # share of the duplicate backlog shipped per minute (consumers' dedupe window / batch delay)

    @property
    def signals(self):
        return ("get_business_metrics", "get_metrics", "get_logs", "get_deploys" if self.spec["variant"] == "deploy" else "get_flags")

    def __init__(self, spec):
        super().__init__(spec)
        self.dups, self.purged = 0.0, -1

    def active(self, w):
        s = self.spec
        return w.flags[s["flag"]]["on"] if s["variant"] == "flag" else w.nodes[self.node].version == s["bad_version"]

    def apply(self, w, t):
        s, q = self.spec, w.nodes[self.spec["queue"]]
        if t == self.onset - 1:
            if s["variant"] == "flag":
                w.set_flag(s["flag"], True, t, by=s["by"])
            else:
                w.deploy(self.node, s["bad_version"], t, by="ci-bot")
        if q.maint.get("purge_dlq", -1) > self.purged:           # duplicates removed from the queue
            self.purged, self.dups = q.maint["purge_dlq"], 0.0
        on = t >= self.onset and self.active(w)
        if on:
            w.xmul[s["queue"]] = 2.0                              # every completed order is published twice
        wk = w.nodes[s["worker"]]
        self.dups += 1.0 if on else 0.0
        ship = min(1.0, self.SHIP * max(1.0, wk.replicas / s["wr0"]))        # more consumers ship the duplicates sooner
        sent, self.dups = ship * self.dups, (1 - ship) * self.dups
        w.dupship += sent
        w.harm += s["frac"] * sent
        w.tick_flags[self.node] = "dup" if on else ""

    def fixed(self, w):
        return not self.active(w)

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node:
            return []
        ids = [f"evt_{rng.getrandbits(40):010x}" for _ in range(rng.randint(1, 2))]
        twice = 2 if rec["flag"] == "dup" else 1
        return [("INFO", f"published event order.completed id={i}") for i in ids for _ in range(twice)]

    def fix_plan(self):
        s = self.spec
        if s["variant"] == "flag":
            first = self._at("set_flag", {"flag": s["flag"], "on": False}, self.onset)
        else:
            first = self._at("rollback", {"service": self.node, "version": s["prev_version"]}, self.onset)
        return [first, (max(0, self.onset) + 5, "run_maintenance", {"service": s["queue"], "action": "purge_dlq"})]

    def is_fix(self, tool, args):
        s = self.spec
        if s["variant"] == "flag":
            return tool == "set_flag" and args.get("flag") == s["flag"] and args.get("on") is False
        return tool == "rollback" and args.get("service") == self.node and args.get("version") != s["bad_version"]

    def allows(self, tool, args):       # then purge the duplicates still queued
        return self.is_fix(tool, args) or (tool == "run_maintenance" and args.get("service") == self.spec["queue"]
                                           and args.get("action") == "purge_dlq")


@_reg
class StuckFailover(Fault):
    """R13, GoCardless 2017-10-10: https://gocardless.com/blog/incident-review-api-and-dashboard-outage-on-10th-october/"""
    fault_class = "stuck_failover"
    signals = ("get_logs", "get_metrics", "get_topology")

    def __init__(self, spec):
        super().__init__(spec)
        self.seen, self.promoted = 0, False

    def apply(self, w, t):
        db = w.nodes[self.node]
        if self.promoted or t < self.onset:
            return
        if db.failovers > self.seen:
            self.seen = db.failovers
            if db.cfg["cluster_manager"] == "maintenance":
                self.promoted = True
                w.event(t, "info", "INFO", self.node, f"{self.node}: replica promoted to primary (manual promotion)")
                return
            w.event(t, "warn", "WARN", self.node, f"{self.node}: cluster manager reverted the promotion of the replica "
                                                  f"(constraint violated)")
        w.add_err(self.node, .97)
        w.tick_flags[self.node] = "io"

    def failover_ok(self, w):
        return not self.promoted and w.t >= self.onset and w.nodes[self.node].cfg["cluster_manager"] == "maintenance"

    def fixed(self, w):
        return self.promoted

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node:
            return []
        out = []
        if rec["flag"] == "io":
            if rng.random() < .8:
                out.append(("ERROR", f"I/O error: read error on /dev/nvme1n1 sector {rng.randint(10 ** 6, 10 ** 8)} (EIO)"))
            if rng.random() < .4:
                out.append(("ERROR", "PANIC: could not write to file pg_wal/xlogtemp: Input/output error"))
            if rng.random() < .4:
                out.append(("WARN", "cluster-manager: promotion of replica refused: constraint primary-preferred not satisfied"))
        if rng.random() < .4:      # a loud but unrelated warning
            out.append(("WARN", f"archiver: WAL segment {rng.getrandbits(48):012x} archive failed, will retry"))
        return out

    def fix_plan(self):
        return [self._at("set_config", {"service": self.node, "key": "cluster_manager", "value": "maintenance"}, 0),
                self._at("failover_db", {}, 0)]

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "cluster_manager"
                and args.get("value") == "maintenance")


@_reg
class AbusiveClient(Fault):
    """R14, Healthchecks.io 2025-11-01: https://blog.healthchecks.io/2025/11/post-mortem-outage-on-november-1/"""
    fault_class = "abusive_client"
    signals = ("get_metrics", "get_logs", "get_traces")

    def apply(self, w, t):
        s, nd = self.spec, w.nodes[self.node]
        if t < self.onset or self.fixed(w):
            return
        # ponytail: the client takes every connection slot it can get, so more replicas give the legitimate clients nothing more
        w.cap_mult[self.node] = w.cap_mult.get(self.node, 1.0) * min(1.0, s["left"] * s["r0"] / max(1, nd.live))
        x = w.xm.setdefault(self.node, {})
        x["conns"] = nd.ready_n * nd.cfg["pool_size"]
        x["slot_wait_ms"] = 2400.0
        w.tick_flags[self.node] = "abuse"

    def fixed(self, w):
        return w.nodes[self.node].cfg["block_client"] == self.spec["id"]

    def log_lines(self, w, node, tt, rec, rng):
        if node != self.node:
            return []
        c = self.spec["id"]
        if rec["flag"] == "abuse":
            return ([("ERROR", f"no free connection slot (maxconn reached): client={c} request queued {rng.randint(25, 31)}s then dropped")] * rng.randint(1, 3)
                    + [("WARN", f"client={c} GET /v1/items 499 client closed request after {rng.randint(29000, 31000)}ms")] * rng.randint(2, 4))
        if self.fixed(w) and rng.random() < .3:
            return [("INFO", f"client={c} blocked (403)")]
        return []

    def fix_plan(self):
        return [self._at("set_config", {"service": self.node, "key": "block_client", "value": self.spec["id"]}, self.onset)]

    def is_fix(self, tool, args):
        return (tool == "set_config" and args.get("service") == self.node and args.get("key") == "block_client"
                and args.get("value") == self.spec["id"])


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
    fl = rng.choice([f for f in sc.flags if not f.get("locked")])          # reuse one of the scenario's flags: off, with a big hidden latency effect
    flag, ms = fl["name"], rng.randint(900, 1500)
    fl.update(on=False, effect=(node, ms), locked=True)
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
    fl = _take_flag(sc, rng, f"{node}-canary")           # the canary flag replaces one of the scenario's flags
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


def _plan_dup(sc, rng, onset, used):
    biller = _role(sc, BILLER)
    if sc.cache in used or biller in used:
        raise ValueError("cache or billing service already used")
    _take_flag(sc, rng, "auto-recharge", on=True)           # the kill switch replaces one of the scenario's flags
    sc.flag_audit.append({"t": -rng.randint(2000, 3000), "flag": "auto-recharge", "on": True, "by": rng.choice(ADMINS)})
    return {"node": sc.cache, "biller": biller, "frac": round(rng.uniform(.25, .35), 3), "age": rng.randint(800, 3000),
            "by": rng.choice(ADMINS)}


def _plan_lag(sc, rng, onset, used):
    cl = [e.caller for e in sc.edges if e.callee == sc.db and not sc.nodes[e.caller].entry and e.caller not in used
          and sc.share[e.caller] >= .15]
    if sc.db in used or not cl:
        raise ValueError("db already used or no replica-reading client")
    sc.nodes[sc.db].in_sync = True        # the replica is healthy: only the lag makes a failover lossy
    mx = rng.randint(120, 600)
    return {"node": sc.db, "clients": rng.sample(cl, min(2, len(cl))), "max": mx, "rate": mx / rng.randint(6, 10),
            "age": rng.randint(800, 3000), "by": rng.choice(ADMINS)}


def _plan_lock(sc, rng, onset, used):
    cl = [n for n in _apps(sc, used, .3) if any(e.caller == n and e.callee == sc.db for e in sc.edges)]
    if sc.db in used:
        raise ValueError("db already used")
    node = _pick(rng, cl)
    prev = sc.deploys[node][-1]["version"]
    return {"node": sc.db, "deploy_node": node, "prev_version": prev, "bad_version": _bump(prev)}


def _plan_pool(sc, rng, onset, used):
    if sc.db in used:
        raise ValueError("db already used")
    clients = [e.caller for e in sc.edges if e.callee == sc.db]
    apps = [n for n in sc.order if sc.nodes[n].kind == "app" and not sc.nodes[n].entry]
    old = rng.choice((("14.9", "14.10"), ("15.3", "15.4"), ("16.1", "16.2")))
    return {"node": sc.db, "clients": clients, "bot": rng.choice(clients), "cron": rng.choice(apps), "old": old[0],
            "new": old[1]}


def _plan_gray(sc, rng, onset, used):
    if sc.entry in used:
        raise ValueError("entry already used")
    sp = sc.nodes[sc.entry]
    sp.replicas = max(sp.replicas, 3)
    return {"node": sc.entry, "order": rng.sample(range(sp.replicas), sp.replicas)}


def _plan_skew(sc, rng, onset, used):
    node = _role(sc, AUTHN)
    if node in used:
        raise ValueError("auth service already used")
    sp = sc.nodes[node]
    sp.replicas = max(sp.replicas, 3)
    return {"node": node, "idx": rng.randrange(sp.replicas), "offset_ms": rng.randint(90, 600) * 1000 * rng.choice((-1, 1))}


def _plan_sender(sc, rng, onset, used):
    node = _role(sc, SENDER)
    if node in used:
        raise ValueError("mail sender already used")
    return {"node": node, "variant": rng.choice(("cert", "ca")), "old_ca": "2020-09", "frac": round(rng.uniform(.1, .15), 3)}

def _plan_mail(sc, rng, onset, used):
    node = _role(sc, SENDER)
    if node in used:
        raise ValueError("mail sender already used")
    return {"node": node, "nom": round(.08 * sc.params["base_rps"], 2), "dur": rng.randint(14, 20),
            "frac": round(rng.uniform(.1, .15), 3)}


def _plan_loop(sc, rng, onset, used):
    if sc.cache in used or sc.db in used or sc.entry in used:
        raise ValueError("cache, db or entry already used")
    from .sim import HERD
    sh = {n: 0.0 for n in sc.order}      # db load with an empty cache, as a multiple of the nominal load: how deep must the entry shed?
    sh[sc.entry] = 1.0
    for n in sc.order:
        for e in sc.children(n):
            sh[e.callee] += sh[n] * e.fanout * ((1 + HERD * .75) if e.via_cache else 1)
    dbs = sc.nodes[sc.db]
    util0 = sh[sc.db] * sc.params["base_rps"] / (dbs.replicas * dbs.cap)
    return {"node": sc.cache, "entry": sc.entry, "db": sc.db, "old": sc.nodes[sc.cache].timeout_ms, "new": rng.randint(3, 12),
            "by": rng.choice(ADMINS), "shed": max(1, int(sc.params["base_rps"] * min(1.0, .4 / util0))),
            "also": [sc.entry, sc.db]}


def _plan_waf(sc, rng, onset, used):
    if sc.entry in used:
        raise ValueError("entry already used")
    spec = {"node": sc.entry, "variant": rng.choice(("flag", "config")), "by": rng.choice(ADMINS), "flag": ""}
    if spec["variant"] == "flag":
        spec["flag"] = _take_flag(sc, rng, "waf-managed-rules-v2")["name"]
    return spec


def _plan_redis(sc, rng, onset, used):
    auth = _role(sc, AUTHN)
    if sc.cache in used:
        raise ValueError("cache already used")
    old = sc.nodes[sc.cache].mem_mb
    return {"node": sc.cache, "auth": auth, "variant": rng.choice(("shrink", "policy")), "old_mb": old,
            "new_mb": max(64, int(old * .35)), "by": rng.choice(ADMINS)}


def _plan_dupev(sc, rng, onset, used):
    prod = next(e.caller for e in sc.edges if e.callee == sc.queue)
    if prod in used or sc.queue in used or sc.worker in used:
        raise ValueError("producer, queue or worker already used")
    prev = sc.deploys[prod][-1]["version"]
    spec = {"node": prod, "queue": sc.queue, "worker": sc.worker, "variant": rng.choice(("deploy", "flag")), "flag": "",
            "prev_version": prev, "bad_version": _bump(prev), "frac": round(rng.uniform(.1, .15), 3),
            "wr0": sc.nodes[sc.worker].replicas, "by": rng.choice(ADMINS), "also": [sc.queue, sc.worker]}
    if spec["variant"] == "flag":
        spec["flag"] = _take_flag(sc, rng, "order-events-retry")["name"]
    return spec


def _plan_stuck(sc, rng, onset, used):
    if sc.db in used:
        raise ValueError("db already used")
    sc.nodes[sc.db].in_sync = True        # the replica is healthy: failing over is right, once the cluster manager allows it
    return {"node": sc.db}


def _plan_abuse(sc, rng, onset, used):
    if sc.entry in used:
        raise ValueError("entry already used")
    sp = sc.nodes[sc.entry]
    u0 = sc.params["base_rps"] / (sp.replicas * sp.cap)          # nominal utilisation of the gateway
    return {"node": sc.entry, "id": f"{rng.choice(('shop', 'data', 'sync', 'crawl'))}-{rng.getrandbits(16):04x}",
            "left": round(u0 * rng.uniform(.5, .7), 3), "r0": sp.replicas}


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
            "bad_canary": _plan_canary, "thread_starvation": _plan_thread, "duplicate_charges": _plan_dup,
            "replica_lag_stale_reads": _plan_lag, "migration_lock": _plan_lock, "pool_sync_recycle": _plan_pool,
            "progressive_gray": _plan_gray, "clock_skew": _plan_skew, "expired_cert_dismissed_alert": _plan_sender,
            "mail_backlog_ramp": _plan_mail, "cache_invalidation_loop": _plan_loop, "bad_config_push": _plan_waf,
            "redis_maxmemory": _plan_redis, "duplicate_events": _plan_dupev, "stuck_failover": _plan_stuck,
            "abusive_client": _plan_abuse}


def build(spec):
    return CLASSES[spec["fault_class"]](spec)
