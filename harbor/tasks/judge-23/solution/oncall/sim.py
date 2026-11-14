"""World state + tick loop + the Env tool API (env.call(tool, **args) -> dict)."""
import inspect
import json
import math
from random import Random

from . import faults as F
from .scenarios import FAMILIES, T, E, WARM

SLO_MS = 800
MAX_CALLS = 150
INF = 9.99
CONFIG_KEYS = ("max_retries", "timeout_ms", "pool_size", "rate_limit_rps", "log_level", "dlq_enabled")
HERD = 5.0     # thundering herd: concurrent misses on cold keys multiply the db queries per miss
MAINT = {"rotate_cert": ("app", "db", "cache", "queue"), "prune_logs": ("app", "db", "cache", "queue"),
         "purge_dlq": ("app", "queue"), "warm_cache": ("cache",), "vacuum_db": ("db",), "rebalance_shards": ("db",),
         "compact_wal": ("db",), "flush_dns": ("app", "db", "cache", "queue")}
HARMFUL = ("vacuum_db", "rebalance_shards", "compact_wal")
OBS_COST = {"get_status": 1, "get_events": 1, "get_topology": 1, "get_metrics": 1, "get_logs": 1,
            "get_traces": 2, "get_deploys": 1, "get_config": 1, "get_flags": 1, "get_runbook": 1}
ACT_COST = {"rollback": 5, "restart": 3, "scale": 4, "set_config": 2, "set_flag": 1,
            "set_circuit_breaker": 2, "failover_db": 6, "run_maintenance": 3, "resolve_incident": 0}
TOOLS = tuple(OBS_COST) + tuple(ACT_COST) + ("wait",)
METRICS = ("rps", "error_rate", "p50", "p99", "cpu", "mem", "conns", "worker_util", "disk", "retries",
           "queue_lag", "cache_hit_rate")
RUNBOOKS = {
    "bad_deploy": "Errors that start at a deploy: compare error onset with get_deploys, read ERROR logs for a stack trace with the build version, roll back to the previous version.",
    "memory_leak": "Memory that rises steadily and drops on OOMKilled restarts (sawtooth) after a deploy: restarting only resets the clock, roll back the release.",
    "retry_storm": "Dependency saturated while its clients show high retry rates: reduce client retries first (set_config max_retries), scaling clients or restarting the dependency makes it worse (connection limits, cold start).",
    "circuit_breaker": "closed = normal; open = fail fast (critical edges fail); fallback = serve degraded response. Use fallback for a failing external dependency that has a fallback.",
    "schema_migration": "Deploys with has_schema_migration and reversible=false cannot be rolled back past without data loss.",
    "cache_stampede": "After a cache flush the hit rate is near 0 and the database sees all traffic. If the database saturates, the hit rate cannot recover by itself: relieve it (warm_cache, or throttle), wait for the hit rate to recover, then remove the throttle.",
    "maintenance": "vacuum_db, rebalance_shards and compact_wal on a busy database halve its capacity for several minutes.",
    "cert_expiry": "Certificates expire at a fixed time: rotate_cert before the expiry avoids TLS handshake failures; rotating after it ends them.",
    "disk_full": "A disk near 100% makes writes fail. Freeing space (prune_logs) is not durable while debug logging keeps filling it: lower the log level too. Restarting does not free disk.",
    "poison_message": "A message that crashes its consumer blocks the queue head: new replicas crash on it too. Move it to the dead-letter queue (dlq_enabled) instead of rolling back or scaling.",
    "canary": "A canary serves a small share of traffic: look at p99 against p50 and at get_deploys / get_flags, not only at the average error rate. Turn the canary flag off or roll back.",
    "thread_starvation": "A slow dependency holds worker threads of its caller (worker_util > 1) even with 0% errors: cut it off with a circuit breaker in fallback mode instead of fixing the caller.",
    "capacity": "Scaling adds cost; clients of a database also add connections (replicas x pool_size) and can exhaust max_connections.",
}
NOISE = (("INFO", "GET /healthz 200 {a}ms"), ("INFO", "request completed status=200 dur={b}ms"),
         ("INFO", "cache refresh ok keys={c}"), ("INFO", "connection pool stats active={d} idle={e}"),
         ("INFO", "gc cycle completed in {a}ms"), ("INFO", "config reload: no changes"),
         ("INFO", "metrics flushed ({c} series)"), ("INFO", "heartbeat ok peer=lb-{d}"),
         ("INFO", "background job reindex finished in {b}ms"), ("INFO", "tls session resumed"),
         ("WARN", "slow request dur={g}ms path=/v1/items"), ("WARN", "deprecated header X-Legacy-Auth present"),
         ("WARN", "client disconnected before response was written"),
         ("ERROR", "client closed request (499) path=/v1/items"))


class ToolError(Exception):
    pass


def comb(a, b):
    return 1 - (1 - a) * (1 - b)


def slow_frac(p50, p99, limit):
    """Share of requests slower than `limit`, log-linear between p99 (0) and p50 (0.5), then to 1."""
    if p99 <= limit:
        return 0.0
    if limit >= p50:
        return 0.5 * math.log(p99 / limit) / math.log(p99 / p50) if p99 > p50 else 0.0
    return 0.5 + 0.5 * (1 - limit / p50)


class Node:
    def __init__(self, sp, deploys, cfg_audit, clients):
        self.sp, self.name, self.kind = sp, sp.name, sp.kind
        self.replicas = self.ready_n = sp.replicas
        self.warm_until = -10 ** 9
        self.cap_penalty_until = -10 ** 9
        # ponytail: only db clients retry by default; chained retries at every tier make healthy systems metastable
        self.cfg = {"max_retries": 1 if sp.kind == "app" and sp.name in clients else 0, "timeout_ms": sp.timeout_ms, "pool_size": sp.pool_size,
                    "rate_limit_rps": 0, "log_level": "INFO", "dlq_enabled": False}
        self.mem, self.hit = sp.mem_base, sp.hit_base
        self.disk, self.canary, self.rotated = sp.disk, None, False
        self.cert_exp = 30000 + 137 * len(sp.name)       # tick at which the TLS certificate expires
        self.releases = [dict(d) for d in deploys]       # release order (for rollback ordering)
        self.dlog = [dict(d) for d in deploys]           # what get_deploys shows
        self.version = self.releases[-1]["version"] if self.releases else "n/a"
        self.audit = [dict(a) for a in cfg_audit]


class World:
    def __init__(self, sc):
        self.sc = sc
        self.t = -WARM
        clients = [e.caller for e in sc.edges if e.callee == sc.db]
        self.nodes = {n: Node(sc.nodes[n], sc.deploys.get(n, []), sc.cfg_audit[n], clients) for n in sc.order}
        self.out = {n: sc.children(n) for n in sc.order}
        self.clients = clients
        self.cb = {(e.caller, e.callee): "closed" for e in sc.edges}
        self.flags = {f["name"]: {"on": f["on"], "effect": f["effect"]} for f in sc.flags}
        self.flag_audit = [dict(a) for a in sc.flag_audit]
        self.events, self.alerts = [], {}
        self.err = {n: 0.0 for n in sc.order}
        self.rec, self.offered, self.good, self.spend = [], [], [], []
        self.fault_err, self.fault_lat, self.lat_mult, self.tick_flags = {}, {}, {}, {}
        self.cap_mult, self.drop, self.p99_add = {}, {}, {}
        self.lag, self.bp = 0.0, 0.0                      # queue backlog (rate-ticks) and the enqueue rejection share
        self.q_nom = sc.share[sc.queue] * sc.params["base_rps"]
        self.faults = [F.build(s) for s in sc.faults]
        self.seed_key = f"{sc.seed}|{sc.salt}"

    # ---- helpers used by faults / actions -------------------------------------------------
    def event(self, t, typ, sev, svc, text):
        self.events.append({"t": t, "type": typ, "severity": sev, "service": svc, "text": text})

    def add_err(self, node, e):
        self.fault_err[node] = comb(self.fault_err.get(node, 0.0), e)

    def deploy(self, node, version, t, by, migration=False, reversible=True):
        nd = self.nodes[node]
        d = {"version": version, "t": t, "by": by, "has_schema_migration": migration, "reversible": reversible}
        nd.releases.append(d)
        nd.dlog.append(dict(d))
        nd.version = version
        nd.mem = nd.sp.mem_base
        self.event(t, "deploy", "INFO", node, f"deploy of {node} {version} completed (by {by})")

    def set_cfg(self, node, key, value, t, by):
        nd = self.nodes[node]
        nd.audit.append({"t": t, "key": key, "old": nd.cfg[key], "new": value, "by": by})
        nd.cfg[key] = value

    def set_flag(self, name, on, t, by):
        self.flags[name]["on"] = on
        self.flag_audit.append({"t": t, "flag": name, "on": on, "by": by})

    def weight(self, e):
        if not e.via_cache:
            return e.fanout
        miss = 1 - self.nodes[self.sc.cache].hit
        return e.fanout * miss * (1 + HERD * max(0.0, miss - 0.25))

    def throttled(self):
        """True while traffic is held back to protect the db: entry rate limit or a breaker on a cache-miss path."""
        return (self.nodes[self.sc.entry].cfg["rate_limit_rps"] > 0
                or any(self.cb[(e.caller, e.callee)] != "closed" for e in self.sc.edges if e.via_cache))

    # ---- one tick -----------------------------------------------------------------------------
    def step(self):
        sc, t = self.sc, self.t
        nodes, order = self.nodes, self.sc.order
        self.fault_err, self.fault_lat, self.lat_mult, self.tick_flags = {}, {}, {}, {}
        self.cap_mult, self.drop, self.p99_add = {}, {}, {}
        cache = nodes[sc.cache]          # hit rate recovers only while the db is healthy (else metastable)
        cache.hit = min(cache.sp.hit_base, cache.hit + 0.08 * max(0.0, 1 - 2 * self.err[sc.db]))
        h = sc.herring
        if h and t == h["t"]:
            self.deploy(h["node"], h["version"], t, by="release-bot")
            self.event(t, "warn", "WARN", h["node"], f"{h['node']} {h['version']}: deploy finished with 2 warnings "
                                                   f"(deprecated API usage)")
        m = sc.misleading
        if m and t == m["t"]:
            self.event(t, "message", "info", "team-chat", m["text"])
        for i, (wt, svc, text) in enumerate(sc.warns):
            if wt == t:
                self.event(t, "warn", "WARN", svc, f"{svc}: {text}")
                self.alerts[("warn", i)] = {"severity": "WARN", "service": svc, "message": text, "since": t, "until": t + 20}
        for f in self.faults:
            f.apply(self, t)
            if f.spec["role"] == "second" and t == f.onset:
                self.event(t, "message", "info", "support", "support: new customer reports of failed or very slow requests")
        for fl in self.flags.values():
            if fl["on"] and fl["effect"]:
                node, ms = fl["effect"]
                self.fault_lat[node] = self.fault_lat.get(node, 0.0) + ms
        for nd in nodes.values():
            nd.ready_n = nd.replicas if t >= nd.warm_until else min(nd.ready_n, nd.replicas)
        # traffic
        p = sc.params
        offered = p["base_rps"] * (1 + .05 * math.sin(2 * math.pi * (t + p["phase"]) / 1440))
        offered *= 1 + Random(f"{self.seed_key}|traffic|{t}").uniform(-.05, .05)
        if t >= T:
            offered *= 1.5
        entry = nodes[sc.entry]
        rl = entry.cfg["rate_limit_rps"]
        shed = max(0.0, offered - rl) if rl > 0 else 0.0
        # load, top-down (retries amplify load on the previous tick's callee error)
        load = {n: 0.0 for n in order}
        load[sc.entry] = offered - shed
        retries = {n: 0.0 for n in order}
        bp_in = self.bp
        for n in order:
            if nodes[n].kind == "queue":     # asynchronous: the worker consumes what it can, the rest piles up as lag
                wk = nodes[self.out[n][0].callee]
                take = min(self.lag + load[n] * (1 - bp_in), wk.ready_n * wk.sp.cap * self.cap_mult.get(wk.name, 1.0))
                self.lag += load[n] * (1 - bp_in) - take
                load[wk.name] += take
                self.bp = min(1.0, max(0.0, (self.lag / self.q_nom - 3) / 3))     # rejects enqueues beyond 3 min of lag
                continue
            r = nodes[n].cfg["max_retries"]
            for e in self.out[n]:
                if self.cb[(n, e.callee)] != "closed":
                    continue
                base = load[n] * (1 - self.drop.get(n, 0.0)) * self.weight(e)
                extra = base * r * self.err[e.callee]
                load[e.callee] += base + extra
                retries[n] += extra
        # latency + errors, bottom-up
        p50, p99, err, rec, xt = {}, {}, {}, {}, {}
        for n in reversed(order):
            nd = nodes[n]
            sp = nd.sp
            cap = nd.ready_n * sp.cap * (0.5 if t < nd.cap_penalty_until else 1.0) * self.cap_mult.get(n, 1.0)
            if nd.kind == "db":     # ponytail: db goodput drops while it is erroring (thrash) -> storms are self-sustaining
                cap *= 1 - 0.5 * self.err[n]
            ld = load[n]
            if cap <= 0:
                util, overload = INF, 1.0
            else:
                util = ld / cap
                overload = 1 - 1 / util if util > 1 else 0.0
            fe = self.fault_err.get(n, 0.0)
            own = comb(overload, fe)
            if nd.kind == "queue":
                own = comb(own, bp_in)
            conn = 0.0
            if nd.kind == "db":
                demand = sum(nodes[c].ready_n * nodes[c].cfg["pool_size"] for c in self.clients
                             if self.cb[(c, n)] == "closed")
                if demand > sp.max_conn:
                    conn = (demand - sp.max_conn) / demand
                own = comb(own, conn)
            lat = (sp.base_ms / max(0.05, 1 - min(util, 0.99)) * self.lat_mult.get(n, 1.0)
                   + self.fault_lat.get(n, 0.0))
            prod, to, ce, to_callee, xtail = 1.0, 0.0, {}, "", 0.0
            for e in ([] if nd.kind == "queue" else self.out[n]):
                c, mode, w = e.callee, self.cb[(n, e.callee)], self.weight(e)
                if mode == "closed":
                    lat += w * p50[c]
                    xtail = max(xtail, min(1.0, w) * xt[c])      # a callee's extra tail (canary, ...) reaches its callers
                    ce[c] = err[c]
                    if e.critical:
                        ts = slow_frac(p50[c], p99[c], nd.cfg["timeout_ms"])
                        prod *= 1 - min(1.0, w * comb(err[c], ts))
                        if ts > to:
                            to, to_callee = ts, c
                elif e.critical and (mode == "open" or not e.fallback_ok):
                    prod *= 1 - min(1.0, w)
            xt[n] = self.p99_add.get(n, 0.0) + xtail
            p50[n], p99[n] = lat, lat * sp.tail + xt[n]
            wu = 0.0
            if nd.kind == "app":
                wu = ld * lat / 1000 / (nd.ready_n * sp.threads) if nd.ready_n > 0 else INF
                if wu > 1:
                    own = comb(own, 1 - 1 / wu)
            err[n] = 1 - (1 - own) * prod
            conns = (min(sp.max_conn, sp.max_conn * (0.2 + 0.8 * min(1.0, util))) if nd.kind == "db"
                     else nd.ready_n * nd.cfg["pool_size"] * min(1.0, util) * .5)
            rec[n] = {"rps": ld, "err": err[n], "p50": lat, "p99": p99[n], "util": util,
                      "mem": nd.mem, "conns": conns, "wu": wu, "disk": nd.disk, "retries": retries[n],
                      "lag": self.lag / self.q_nom if n in (sc.queue, sc.worker) else 0.0,
                      "bp": bp_in if nd.kind == "queue" else 0.0,
                      "hit": nd.hit, "ver": nd.version, "flag": self.tick_flags.get(n, ""), "ce": ce,
                      "to": (to_callee, to), "conn": conn, "overload": overload, "cold": nd.ready_n == 0,
                      "own": own}
        e0 = sc.entry
        good = load[e0] * (1 - err[e0]) * (1 - slow_frac(p50[e0], p99[e0], SLO_MS))
        self.rec.append(rec)
        self.err = err
        if t >= 0:
            self.offered.append(offered)
            self.good.append(good)
            self.spend.append(sum(nd.replicas * nd.sp.cost for nd in nodes.values()))
        self._alerts(t, rec, offered, good)
        self.t += 1

    def _alerts(self, t, rec, offered, good):
        for k in [k for k, a in self.alerts.items() if a.get("until", 10 ** 9) < t]:
            del self.alerts[k]
        for n, r in rec.items():
            key = ("err", n)
            if r["err"] > .05 and key not in self.alerts:
                msg = f"error rate {r['err']:.0%} (threshold 5%)"
                self.alerts[key] = {"severity": "CRIT", "service": n, "message": msg, "since": t}
                self.event(t, "alert", "CRIT", n, f"{n}: {msg}")
            elif r["err"] < .02 and key in self.alerts:
                del self.alerts[key]
                self.event(t, "resolved", "INFO", n, f"{n}: error rate back to normal")
        burn = (offered - good) / offered
        key = ("slo", self.sc.entry)
        if burn > .05 and key not in self.alerts:
            msg = f"SLO burn: {burn:.0%} of requests failing or slow"
            self.alerts[key] = {"severity": "CRIT", "service": self.sc.entry, "message": msg, "since": t}
            self.event(t, "alert", "CRIT", self.sc.entry, f"{self.sc.entry}: {msg}")
        elif burn < .02 and key in self.alerts:
            del self.alerts[key]
            self.event(t, "resolved", "INFO", self.sc.entry, f"{self.sc.entry}: SLO burn cleared")

    # ---- logs (generated from per-tick records) ---------------------------------------------
    def log_lines(self, node, t_from, t_to):
        out = []
        sc = self.sc
        for tt in range(max(t_from, -WARM), t_to):
            r = self.rec[tt + WARM][node]
            rng = Random(f"{self.seed_key}|noise|log|{node}|{tt}")
            for _ in range(rng.randint(3, 5)):
                lvl, msg = NOISE[rng.randrange(len(NOISE))] if rng.random() < .25 else NOISE[rng.randrange(10)]
                out.append((tt, lvl, msg.format(a=rng.randint(1, 9), b=rng.randint(8, 60), c=rng.randint(100, 900),
                                                d=rng.randint(2, 30), e=rng.randint(2, 30), g=rng.randint(180, 420))))
            nd = self.nodes[node]
            for c, e in r["ce"].items():
                if e > .05 and sc.nodes[c].kind != "cache" and rng.random() < min(1.0, .3 + e):
                    if sc.nodes[c].kind == "external":
                        msg = (f"upstream {c} timeout after {rng.randint(900, 3000)}ms" if rng.random() < .5
                               else f"HTTP 503 from {c}")
                    else:
                        msg = f"call to {c} failed: {rng.choice(('503 Service Unavailable', 'connection reset'))}"
                    out.append((tt, "ERROR", msg))
            if r["to"][1] > .02 and rng.random() < .8:
                out.append((tt, "ERROR", f"deadline exceeded after {nd.cfg['timeout_ms']}ms calling {r['to'][0]}"))
            if r["bp"] > .05:
                out.append((tt, "ERROR", f"enqueue rejected: consumer lag {r['lag']:.1f}m exceeds the backpressure threshold"))
            if r["conn"] > .05:
                out.append((tt, "ERROR", f"too many connections: pool exhausted (max_connections={nd.sp.max_conn})"))
            if r["overload"] > .05 and nd.kind != "app":
                out.append((tt, "ERROR", f"statement timeout: query cancelled (queue depth {int(r['rps'] / 4)})"))
            if r["wu"] > 1:
                out.append((tt, "WARN", f"worker pool exhausted: rejecting requests ({r['wu']:.1f}x busy)"))
            if r["cold"]:
                out.append((tt, "INFO", "starting up: warming caches, not ready for traffic"))
            for f in self.faults:
                out.extend((tt, lvl, msg) for lvl, msg in f.log_lines(self, node, tt, r, rng))
        return out

    # ---- actions ------------------------------------------------------------------------------
    def restart(self, node):
        nd = self.nodes[node]
        nd.ready_n, nd.warm_until, nd.mem = 0, self.t + nd.sp.cold_start, nd.sp.mem_base
        if nd.kind == "cache":
            nd.hit = 0.0

    def rollback(self, node, version):
        nd = self.nodes[node]
        vs = [d["version"] for d in nd.releases]
        lost = any(d["has_schema_migration"] and not d["reversible"]
                   for d in nd.releases[vs.index(version) + 1: vs.index(nd.version) + 1])
        nd.version, nd.mem = version, nd.sp.mem_base
        nd.dlog.append({"version": version, "t": self.t, "by": "oncall-agent (rollback)",
                        "has_schema_migration": False, "reversible": True})
        return lost

    def scale(self, node, n):
        nd = self.nodes[node]
        if n > nd.replicas:
            nd.warm_until = max(nd.warm_until, self.t + nd.sp.cold_start)
        nd.replicas = n


class Env:
    """One episode. `call()` is the agent API; `finalize()` runs the rest of the clock and scores."""

    def __init__(self, scenario):
        self.sc = scenario
        self.w = World(scenario)
        self.log, self.n_calls, self.done = [], 0, False
        self.resolution = None            # frozenset of (service, fault_class) from the first resolve
        self.t_resolve = None
        self.data_loss = []
        self.faults_at_resolve = None
        self._breakdown = None
        while self.w.t < 0:
            self.w.step()

    @property
    def t(self):
        return self.w.t

    # ---- public API ---------------------------------------------------------------------------
    def call(self, tool, **args):
        w = self.w
        if self.done:
            return {"ok": False, "t": w.t, "error": "episode over"}
        t0, cost, res, effect, err = w.t, 1, None, None, None
        try:
            if tool not in TOOLS:
                raise ToolError(f"unknown tool {tool!r}")
            fn = getattr(self, "t_" + tool)
            try:
                inspect.signature(fn).bind(**args)
            except TypeError as e:
                raise ToolError(f"bad arguments for {tool}: {e}")
            try:
                cost, res, effect = fn(**args)
            except TypeError as e:           # e.g. an unhashable value where a name was expected
                raise ToolError(f"invalid argument types for {tool}: {e}")
        except ToolError as e:
            err, cost, effect = str(e), 1, None
        for _ in range(cost):
            if w.t < T + E:
                w.step()
        if effect:
            effect()
        out = {"ok": err is None, "t": w.t}
        out["result" if err is None else "error"] = res if err is None else err
        self.n_calls += 1
        self.log.append({"i": self.n_calls, "tool": tool, "args": args, "t_before": t0, "t_after": w.t,
                         "result": out})
        if self.n_calls >= MAX_CALLS or w.t >= T:
            self.done = True
        return out

    def finish(self):
        self.done = True
        while self.w.t < T + E:
            self.w.step()

    def finalize(self):
        if self._breakdown is None:
            from . import scoring
            self.finish()
            self._breakdown = scoring.breakdown(self)
        return self._breakdown

    # ---- validation helpers -------------------------------------------------------------------
    def _node(self, name, managed=True):
        if not isinstance(name, str) or name not in self.w.nodes:
            raise ToolError(f"unknown service {name!r}")
        if managed and self.w.nodes[name].kind == "external":
            raise ToolError(f"{name} is an external dependency, not managed by this team")
        return self.w.nodes[name]

    @staticmethod
    def _int(name, v, lo, hi):
        if isinstance(v, bool) or not isinstance(v, int):
            raise ToolError(f"{name} must be an integer")
        if not lo <= v <= hi:
            raise ToolError(f"{name} must be between {lo} and {hi}")
        return v

    def _rng(self, tool, args):
        return Random(f"{self.w.seed_key}|noise|{tool}|{json.dumps(args, sort_keys=True, default=str)}|{self.w.t}")

    # ---- observation tools: return (cost, result, effect) -------------------------------------
    def t_get_status(self):
        w = self.w
        alerts = [{k: v for k, v in a.items() if k != "until"} for a in w.alerts.values()]
        return 1, {"as_of": w.t, "remaining_minutes": max(0, T - w.t), "alerts": alerts,
                   "spend": round(float(sum(w.spend)), 1)}, None

    def t_get_events(self, since=0):
        self._int("since", since, -WARM, T + E)
        ev = [e for e in self.w.events if since == 0 or e["t"] >= since]
        return 1, {"as_of": self.w.t, "events": ev[-100:]}, None

    def t_get_topology(self):
        w = self.w
        nodes = []
        for n, nd in w.nodes.items():
            d = {"name": n, "kind": nd.kind, "entry": nd.sp.entry, "replicas": nd.replicas}
            if nd.kind == "db":
                d["replica_in_sync"] = nd.sp.in_sync
            nodes.append(d)
        edges = [{"caller": e.caller, "callee": e.callee, "fanout": e.fanout, "critical": e.critical,
                  "fallback_ok": e.fallback_ok, "via_cache": e.via_cache, "circuit_breaker": w.cb[(e.caller, e.callee)],
                  "async": w.nodes[e.caller].kind == "queue"} for e in w.sc.edges]
        return 1, {"nodes": nodes, "edges": edges}, None

    def t_get_metrics(self, services, window=5):
        w = self.w
        if not isinstance(services, list) or not 1 <= len(services) <= 5:
            raise ToolError("services must be a list of 1-5 service names")
        for s in services:
            self._node(s, managed=False)
        self._int("window", window, 1, 30)
        rng = self._rng("get_metrics", {"services": services, "window": window})
        ticks = list(range(max(-WARM, w.t - window), w.t))
        res = {}
        for s in services:
            series = {m: [] for m in METRICS}
            for tt in ticks:
                r = w.rec[tt + WARM][s]
                g = [rng.gauss(0, 1) for _ in range(8)]
                cpu = min(1.0, .1 + .85 * min(r["util"], 1.0))
                vals = {"rps": round(r["rps"] * (1 + .02 * g[0]), 1),
                        "error_rate": round(max(0.0, r["err"] + .003 * g[1]), 4),
                        "p50": round(r["p50"] * (1 + .03 * g[2]), 1), "p99": round(r["p99"] * (1 + .04 * g[3]), 1),
                        "cpu": round(min(1.0, max(0.0, cpu + .01 * g[4])), 3),
                        "mem": round(r["mem"] + .005 * g[5], 3), "conns": int(r["conns"]),
                        "worker_util": round(min(r["wu"], 99.0) * (1 + .03 * g[6]), 3), "disk": round(r["disk"], 3),
                        "retries": round(r["retries"] * (1 + .03 * g[7]), 1), "queue_lag": round(r["lag"], 2),
                        "cache_hit_rate": round(r["hit"], 3) if w.nodes[s].kind == "cache" else None}
                for m in METRICS:
                    series[m].append(vals[m])
            res[s] = series
        return 1, {"as_of": w.t, "ticks": ticks, "metrics": res}, None

    def t_get_logs(self, service, level="ALL", grep="", limit=50):
        w = self.w
        self._node(service, managed=False)
        if level not in ("ALL", "ERROR", "WARN", "INFO"):
            raise ToolError("level must be one of ALL, ERROR, WARN, INFO")
        if not isinstance(grep, str):
            raise ToolError("grep must be a string")
        self._int("limit", limit, 1, 200)
        rank = {"INFO": 0, "WARN": 1, "ERROR": 2}
        lo = {"ALL": 0, "INFO": 0, "WARN": 1, "ERROR": 2}[level]
        lines = [{"t": tt, "level": lvl, "msg": f"{service}: {msg}"}
                 for tt, lvl, msg in w.log_lines(service, w.t - 60, w.t)
                 if rank[lvl] >= lo and grep.lower() in msg.lower()]
        return 1, {"as_of": w.t, "lines": lines[-limit:], "truncated": len(lines) > limit}, None

    def t_get_traces(self, endpoint, n=5):
        w, sc = self.w, self.sc
        kids = [e.callee for e in sc.children(sc.entry)]
        if endpoint not in ["/" + k for k in kids]:
            raise ToolError(f"unknown endpoint {endpoint!r}; endpoints are " + ", ".join("/" + k for k in kids))
        self._int("n", n, 1, 10)
        rng = self._rng("get_traces", {"endpoint": endpoint, "n": n})
        last = w.rec[w.t - 1 + WARM]
        poison = next((f.spec["msg_id"] for f in w.faults if f.fault_class == "poison_message" and not f.fixed(w)), None)
        traces = []
        for _ in range(n):
            spans = []

            def walk(node, parent, depth):
                r = last[node]
                span = {"service": node, "parent": parent, "duration_ms": round(r["p50"] * rng.uniform(.6, 1.6), 1),
                        "status": "error" if rng.random() < r["err"] else "ok"}
                if node == sc.queue:      # the message at the head of the queue (the same one while a poison message blocks it)
                    span["message_id"] = poison or f"m-{rng.getrandbits(32):08x}"
                spans.append(span)
                if depth < 4:
                    for e in ([] if w.nodes[node].kind == "queue" else sc.children(node)):
                        if w.cb[(node, e.callee)] == "closed" and rng.random() < w.weight(e):
                            walk(e.callee, node, depth + 1)
            walk(endpoint[1:], sc.entry, 0)
            traces.append({"trace_id": f"{rng.getrandbits(48):012x}", "message_id": f"m-{rng.getrandbits(32):08x}",
                           "spans": spans})
        return 2, {"as_of": w.t, "traces": traces}, None

    def t_get_deploys(self, service=None):
        w = self.w
        names = [n for n in w.nodes if w.nodes[n].kind != "external"]
        if service is not None:
            self._node(service)
            names = [service]
        return 1, {"as_of": w.t, "deploys": {n: {"current": w.nodes[n].version, "canary": w.nodes[n].canary,
                                                 "history": w.nodes[n].dlog} for n in names}}, None

    def t_get_config(self, service):
        nd = self._node(service, managed=False)
        res = {"service": service, "kind": nd.kind, "version": nd.version, "replicas": nd.replicas,
               "config": dict(nd.cfg), "worker_threads": nd.sp.threads, "mem_limit_mb": nd.sp.mem_mb,
               "audit": list(nd.audit), "cert_expires_at": nd.cert_exp}
        if nd.kind == "db":
            res.update(max_connections=nd.sp.max_conn, replica_in_sync=nd.sp.in_sync)
        return 1, res, None

    def t_get_flags(self):
        w = self.w
        return 1, {"flags": [{"name": n, "on": f["on"]} for n, f in w.flags.items()],
                   "audit": list(w.flag_audit)}, None

    def t_get_runbook(self, topic):
        if topic not in RUNBOOKS:
            raise ToolError(f"unknown topic; available: {', '.join(RUNBOOKS)}")
        return 1, {"topic": topic, "text": RUNBOOKS[topic]}, None

    # ---- action tools -------------------------------------------------------------------------
    def t_rollback(self, service, version):
        nd = self._node(service)
        vs = [d["version"] for d in nd.releases]
        if version not in vs or vs.index(version) >= vs.index(nd.version):
            raise ToolError(f"version must be an older release of {service}; known: {', '.join(vs)}")

        def eff():
            if self.w.rollback(service, version):
                self.data_loss.append(f"rollback {service} to {version} crosses irreversible migration")
        return 5, {"service": service, "version": version, "status": "rolled back"}, eff

    def t_restart(self, service):
        self._node(service)
        return 3, {"service": service, "status": "restarted"}, lambda: self.w.restart(service)

    def t_scale(self, service, replicas):
        self._node(service)
        self._int("replicas", replicas, 1, 20)
        return 4, {"service": service, "replicas": replicas}, lambda: self.w.scale(service, replicas)

    def t_set_config(self, service, key, value):
        self._node(service)
        if key not in CONFIG_KEYS:
            raise ToolError(f"unknown key; valid keys: {', '.join(CONFIG_KEYS)}")
        ranges = {"max_retries": (0, 10), "timeout_ms": (10, 30000), "pool_size": (1, 100)}
        if key in ranges:
            self._int("value", value, *ranges[key])
        elif key == "rate_limit_rps":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100000:
                raise ToolError("rate_limit_rps must be a number between 0 and 100000 (0 = off)")
        elif key == "log_level":
            value = value.upper() if isinstance(value, str) else value
            if value not in ("DEBUG", "INFO", "WARN", "ERROR"):
                raise ToolError("log_level must be one of DEBUG, INFO, WARN, ERROR")
        elif not isinstance(value, bool):
            raise ToolError("dlq_enabled must be a boolean")
        return 2, {"service": service, "key": key, "value": value}, \
            lambda: self.w.set_cfg(service, key, value, self.w.t, by="oncall-agent")

    def t_set_flag(self, flag, on):
        if flag not in self.w.flags:
            raise ToolError(f"unknown flag {flag!r}")
        if not isinstance(on, bool):
            raise ToolError("on must be a boolean")
        return 1, {"flag": flag, "on": on}, lambda: self.w.set_flag(flag, on, self.w.t, by="oncall-agent")

    def t_set_circuit_breaker(self, service, dep, mode):
        self._node(service)
        if (service, dep) not in self.w.cb:
            raise ToolError(f"{service} has no dependency {dep!r}")
        if mode not in ("closed", "open", "fallback"):
            raise ToolError("mode must be one of closed, open, fallback")

        def eff():
            self.w.cb[(service, dep)] = mode
        return 2, {"service": service, "dep": dep, "mode": mode}, eff

    def t_failover_db(self):
        db = self.w.nodes[self.sc.db]

        def eff():
            if not db.sp.in_sync:
                self.data_loss.append("failover to a replica that is not in sync")
            db.ready_n, db.warm_until = 0, self.w.t + 2
        return 6, {"status": "failed over"}, eff

    def t_run_maintenance(self, service, action):
        nd = self._node(service)
        if action not in MAINT:
            raise ToolError(f"unknown action; valid: {', '.join(MAINT)}")
        if nd.kind not in MAINT[action]:
            raise ToolError(f"{action} is not valid for a {nd.kind} service")

        def eff():
            if action in HARMFUL:
                nd.cap_penalty_until = self.w.t + 6
            elif action == "warm_cache":
                nd.hit = min(nd.sp.hit_base, nd.hit + .25)
            elif action == "rotate_cert":
                nd.rotated, nd.cert_exp = True, self.w.t + 129600
                self.w.alerts.pop(("cert", service), None)
            elif action == "prune_logs":
                nd.disk = min(nd.disk, .4)
        return 3, {"service": service, "action": action, "status": "done"}, eff

    def t_wait(self, minutes):
        self._int("minutes", minutes, 1, 30)
        return minutes, {"waited": minutes}, None

    def t_resolve_incident(self, root_causes, summary=""):
        if not isinstance(root_causes, list) or len(root_causes) > 100:
            raise ToolError("root_causes must be a list of {service, fault_class}")
        pairs = []
        for rc in root_causes:
            if (not isinstance(rc, dict) or rc.get("service") not in self.w.nodes
                    or rc.get("fault_class") not in FAMILIES):
                raise ToolError(f"each root cause needs a known service and fault_class in {list(FAMILIES)}")
            pairs.append((rc["service"], rc["fault_class"]))
        if not isinstance(summary, str):
            raise ToolError("summary must be a string")

        def eff():
            self.resolution = frozenset(pairs)
            self.t_resolve = self.w.t
            self.faults_at_resolve = [f.fixed(self.w) for f in self.w.faults]
            self.done = True
        return 0, {"status": "incident closed; the world keeps running"}, eff
