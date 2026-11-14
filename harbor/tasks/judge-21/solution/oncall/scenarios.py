"""Scenario generator: 3 templates, seeded renaming/params, faults, herring, suites."""
import math
import os
from collections import namedtuple
from dataclasses import dataclass, field
from random import Random

from . import faults

T, E, WARM = 120, 45, 30            # episode ticks, epilog ticks, warm-up history ticks
FAMILIES = ("bad_deploy", "memory_leak", "retry_storm", "config_drift", "external_dependency", "cert_expiry",
            "disk_full", "cache_stampede", "poison_message", "bad_canary", "thread_starvation", "under_provisioned",
            "duplicate_charges", "replica_lag_stale_reads", "migration_lock", "pool_sync_recycle", "progressive_gray",
            "clock_skew", "expired_cert_dismissed_alert", "mail_backlog_ramp", "cache_invalidation_loop",
            "bad_config_push", "redis_maxmemory", "duplicate_events", "stuck_failover", "abusive_client")
# report labels = the primary mechanism of a scenario; F1, F3, F5, F6, F7, F8 only ever appear as components (F6 = bomb, F8 = second fault)
LABELS = tuple(f"F{i}" for i in range(1, 15)) + tuple(f"R{i}" for i in range(1, 15))
# (label, primary, components, trap, add-on) per difficulty; the recipe is seed % len(recipes) so consecutive seeds cover every one.
# components: further concurrent root causes, each a tuple of alternatives tried in order (a role-bound node may be taken already).
# trap: "herring" = innocent deploy, "message" = herring + misleading team message, "inherent" = the mechanism brings its own
# (R4 bot signups + cron, R5 provider banner, R7 dismissed alert, R14 heavy partner client, F12 loud caller); add-on: "bomb" = F6, "second" = F8.
SILENT = ("clock_skew", "expired_cert_dismissed_alert", "duplicate_charges", "replica_lag_stale_reads")
LOUD = ("bad_deploy", "config_drift", "memory_leak")
SLOTS = {
    "medium": (("R2", "replica_lag_stale_reads", (), "herring", None), ("R4", "pool_sync_recycle", (), "inherent", None),
               ("R5", "progressive_gray", (), "inherent", None), ("R6", "clock_skew", (), "herring", None),
               ("R7", "expired_cert_dismissed_alert", (), "inherent", None), ("R10", "bad_config_push", (), "herring", None),
               ("R11", "redis_maxmemory", (), "message", None), ("R14", "abusive_client", (), "inherent", None),
               ("F11", "bad_canary", (), "herring", None), ("F12", "thread_starvation", (), "inherent", None),
               ("F13", "config_drift", (), "message", None), ("F2", "memory_leak", (), "herring", None)),
    "hard": (("R1", "duplicate_charges", (), None, "second"), ("R3", "migration_lock", (), None, "bomb"),
             ("R8", "mail_backlog_ramp", (), None, "second"), ("R9", "cache_invalidation_loop", (), None, "bomb"),
             ("R12", "duplicate_events", (), None, "second"), ("R13", "stuck_failover", (), None, "bomb"),
             ("F9", "cache_stampede", (), None, "bomb"), ("F10", "poison_message", (), None, "second"),
             ("F14", "cascade", (), None, "second"),
             ("R2", "replica_lag_stale_reads", (("disk_full",) + LOUD,), None, None),
             ("R4", "pool_sync_recycle", (("clock_skew", "expired_cert_dismissed_alert", "duplicate_charges"),), None, None),
             ("R5", "progressive_gray", (LOUD + ("disk_full",),), None, None),
             ("R6", "clock_skew", (("bad_deploy", "retry_storm", "memory_leak"),), None, None),
             ("R7", "expired_cert_dismissed_alert", (("retry_storm", "bad_deploy", "config_drift"),), None, None),
             ("R14", "abusive_client", (("disk_full", "bad_deploy", "memory_leak"),), None, None),
             ("R10", "bad_config_push", (("clock_skew", "expired_cert_dismissed_alert", "replica_lag_stale_reads"),), None, None),
             ("R11", "redis_maxmemory", (("expired_cert_dismissed_alert", "clock_skew"),), None, None)),
    "expert": (("R9", "cache_invalidation_loop", (("clock_skew", "expired_cert_dismissed_alert"), LOUD), "herring", None),
               ("F14", "cascade", (("replica_lag_stale_reads", "clock_skew", "expired_cert_dismissed_alert"),), "herring", None),
               ("R3", "migration_lock", (("expired_cert_dismissed_alert", "duplicate_events", "mail_backlog_ramp", "duplicate_charges"),),
                "message", "bomb"),
               ("R8", "mail_backlog_ramp", (("progressive_gray",), ("config_drift", "bad_deploy")), "herring", None),
               ("R12", "duplicate_events", (("pool_sync_recycle", "clock_skew"), ("memory_leak", "bad_deploy")), "message", None),
               ("R13", "stuck_failover", (SILENT, ("bad_deploy", "config_drift")), "herring", None),
               ("R11", "redis_maxmemory", (("replica_lag_stale_reads", "expired_cert_dismissed_alert"),
                                           ("external_dependency", "bad_deploy")), "herring", None),
               ("F9", "cache_stampede", (SILENT,), "herring", "second"),
               ("F10", "poison_message", (("progressive_gray", "duplicate_charges", "clock_skew"), ("config_drift", "bad_deploy")),
                "message", None),
               ("R1", "duplicate_charges", (("clock_skew", "progressive_gray"), ("migration_lock", "bad_deploy")), "message", None)),
}
DB_FAULTS = ("replica_lag_stale_reads", "migration_lock", "pool_sync_recycle", "stuck_failover", "cache_invalidation_loop")     # a retry storm on top would blur the picture
SECOND_POOL = ("bad_deploy", "config_drift", "external_dependency", "retry_storm", "memory_leak")
Edge = namedtuple("Edge", "caller callee fanout critical fallback_ok via_cache")

# Roles are listed callers-first (topological). Edges: (caller, callee, fanout, critical,
# fallback_ok, via_cache) over roles. First node is the entry.
TEMPLATES = {
    "eshop": (
        [("gw", "app", ("gateway", "edge-api", "frontdoor", "web-gw")),
         ("search", "app", ("search", "search-svc", "finder")),
         ("catalog", "app", ("catalog", "catalog-svc", "products-api")),
         ("cart", "app", ("cart", "cart-svc", "basket-api")),
         ("recs", "app", ("recommendations", "recs-svc", "suggest-api")),
         ("checkout", "app", ("checkout", "checkout-svc", "purchase-api")),
         ("orders", "app", ("orders", "orders-api", "order-svc")),
         ("inventory", "app", ("inventory", "stock-svc", "warehouse-api")),
         ("queue", "queue", ("order-events", "jobs-queue", "orders-queue")),
         ("worker", "app", ("fulfillment-worker", "order-worker", "invoicer")),
         ("cache", "cache", ("redis-cache", "session-cache", "cache-main")),
         ("db", "db", ("orders-db", "postgres-main", "pg-primary")),
         ("pay", "external", ("payments-gw", "stripe-proxy", "psp-adapter"))],
        [("gw", "search", .4, 1, 0, 0), ("gw", "catalog", .8, 1, 0, 0), ("gw", "cart", .5, 1, 0, 0),
         ("gw", "checkout", .4, 1, 0, 0),
         ("search", "catalog", .3, 1, 0, 0),
         ("catalog", "cache", 1, 0, 1, 0), ("catalog", "db", 1, 1, 0, 1), ("catalog", "inventory", .4, 1, 0, 0),
         ("cart", "cache", 1, 0, 1, 0), ("cart", "db", .5, 1, 0, 1), ("cart", "recs", .5, 0, 1, 0),
         ("recs", "cache", 1, 0, 1, 0),
         ("checkout", "orders", 1, 1, 0, 0), ("checkout", "inventory", 1, 1, 0, 0), ("checkout", "pay", 1, 1, 1, 0),
         ("orders", "db", 1, 1, 0, 0), ("orders", "queue", 1, 1, 0, 0), ("queue", "worker", 1, 0, 1, 0)]),
    "saas": (
        [("api", "app", ("api-gateway", "public-api", "gateway", "api-edge")),
         ("auth", "app", ("auth", "auth-svc", "identity")),
         ("projects", "app", ("projects", "projects-api", "workspace-svc")),
         ("tenants", "app", ("tenants", "tenant-svc", "accounts")),
         ("reports", "app", ("reports", "report-svc", "analytics-api")),
         ("usage", "app", ("usage-meter", "metering", "usage-svc")),
         ("billing", "app", ("billing", "billing-svc", "invoicing")),
         ("notify", "app", ("notifications", "notify-svc", "alerts-api")),
         ("queue", "queue", ("jobs-queue", "billing-events", "task-queue")),
         ("worker", "app", ("invoice-worker", "jobs-runner", "ledger-worker")),
         ("cache", "cache", ("session-cache", "redis-main", "cache-cluster")),
         ("db", "db", ("saas-db", "postgres-core", "pg-main")),
         ("mail", "external", ("email-provider", "sendgrid-proxy", "mail-relay"))],
        [("api", "auth", 1, 1, 0, 0), ("api", "projects", .6, 1, 0, 0), ("api", "tenants", .3, 1, 0, 0),
         ("api", "reports", .5, 1, 0, 0), ("api", "billing", .4, 1, 0, 0),
         ("auth", "cache", 1, 0, 1, 0), ("auth", "db", .8, 1, 0, 1),
         ("projects", "db", .8, 1, 0, 0),
         ("tenants", "db", .4, 1, 0, 1),
         ("reports", "usage", 1, 1, 0, 0), ("reports", "cache", 1, 0, 1, 0),
         ("usage", "cache", 1, 0, 1, 0),
         ("billing", "db", .2, 1, 0, 0), ("billing", "notify", .5, 0, 1, 0), ("billing", "mail", 1, 1, 1, 0),
         ("billing", "queue", 1, 1, 0, 0), ("queue", "worker", 1, 0, 1, 0),
         ("notify", "cache", 1, 0, 1, 0)]),
    "media": (
        [("edge", "app", ("ingest-gateway", "media-edge", "frontline", "stream-gw")),
         ("playlist", "app", ("playlist", "playlist-svc", "queue-api")),
         ("catalog", "app", ("metadata", "catalog", "library-api")),
         ("accounts", "app", ("accounts", "user-svc", "profiles")),
         ("recs", "app", ("discover", "recs-svc", "for-you")),
         ("thumbs", "app", ("thumbnails", "thumb-svc", "preview-api")),
         ("upload", "app", ("upload", "upload-svc", "ingest-api")),
         ("transcode", "app", ("transcode", "encoder-coord", "transcode-svc")),
         ("queue", "queue", ("events-queue", "media-jobs", "task-bus")),
         ("worker", "app", ("notifier", "job-worker", "event-consumer")),
         ("cache", "cache", ("edge-cache", "redis-media", "cache-main")),
         ("db", "db", ("media-db", "postgres-media", "pg-primary")),
         ("origin", "external", ("cdn-origin", "origin-storage", "blob-origin"))],
        [("edge", "playlist", .7, 1, 0, 0), ("edge", "catalog", .6, 1, 0, 0), ("edge", "accounts", .8, 1, 0, 0),
         ("edge", "thumbs", .5, 0, 1, 0), ("edge", "upload", .4, 1, 0, 0),
         ("playlist", "catalog", .5, 1, 0, 0), ("playlist", "origin", 1, 1, 1, 0), ("playlist", "recs", .4, 0, 1, 0),
         ("catalog", "cache", 1, 0, 1, 0), ("catalog", "db", 1, 1, 0, 1),
         ("accounts", "db", .5, 1, 0, 0), ("accounts", "cache", 1, 0, 1, 0), ("accounts", "queue", .5, 1, 0, 0),
         ("recs", "cache", 1, 0, 1, 0), ("thumbs", "cache", 1, 0, 1, 0),
         ("upload", "transcode", 1, 1, 0, 0), ("transcode", "db", .1, 1, 0, 0),
         ("queue", "worker", 1, 0, 1, 0)]),
}

WARN_TEXTS = ("deprecated API v1 endpoint still receiving ~12 calls/min",
              "GC pause 480ms observed (p99 over 5m)",
              "disk usage 71% on /var/log",
              "TLS certificate expires in 54 days",
              "autoscaler cooldown active, skipping scale-in",
              "config reload took 1.8s",
              "slow query log: 3 queries >500ms in last 10m",
              "clock skew 140ms vs ntp pool")
# symptom-focused / flapping alerts that fire around the start of every shift (most are unrelated to the incident)
ALERT_NOISE = ("p99 latency {a}ms above 600ms for 3m (flapping, {b} occurrences in 1h)",
               "synthetic probe GET /healthz failed from eu-west-1 (1 of 5 probes)",
               "container restarts: {b} in 30m", "cpu above 80% for 5m",
               "error budget burn rate above 2x over the 6h window", "5xx ratio {b}% on the load balancer (flapping)",
               "request queue depth above 200 for 2m", "TLS handshake time above 300ms (p95)")
ACTORS = ("alice", "bob", "carol", "dave", "ci-bot")


@dataclass
class NodeSpec:
    name: str
    role: str
    kind: str                # app | db | cache | external | queue
    entry: bool = False
    replicas: int = 2
    cap: int = 100           # rps per replica
    threads: int = 100
    pool_size: int = 10
    base_ms: float = 12.0
    tail: float = 3.0
    cold_start: int = 3
    cost: int = 1
    mem_mb: int = 1024
    mem_base: float = 0.4    # fraction of limit
    disk: float = 0.5
    timeout_ms: int = 1000
    hit_base: float = 0.0
    max_conn: int = 0
    in_sync: bool = True


def _bump(version, minor=True):
    a, b, c = (int(x) for x in version[1:].split("."))
    return f"v{a}.{b + 1}.0" if minor else f"v{a}.{b}.{c + 1}"


@dataclass
class Scenario:
    seed: int
    difficulty: str
    salt: str = ""
    # derived (deterministic function of the three fields above)
    id: str = field(init=False)
    family: str = field(init=False)      # report label: the primary mechanism (F1..F14, R1..R14)
    template: str = field(init=False)
    nodes: dict = field(init=False)      # name -> NodeSpec, in topological order
    order: list = field(init=False)
    edges: list = field(init=False)
    entry: str = field(init=False)
    db: str = field(init=False)
    cache: str = field(init=False)
    external: str = field(init=False)
    queue: str = field(init=False)
    worker: str = field(init=False)      # the app consuming `queue`
    params: dict = field(init=False)
    share: dict = field(init=False)      # nominal share of entry traffic per node
    crit: dict = field(init=False)
    p50: dict = field(init=False)
    deploys: dict = field(init=False)    # name -> [deploy dict]
    flags: list = field(init=False)      # [{name,on,effect:(node,ms)|None}]
    flag_audit: list = field(init=False)
    cfg_audit: dict = field(init=False)  # name -> [audit dict]
    warns: list = field(init=False)      # [(t, service, text)]
    faults: list = field(init=False)     # truth: fault specs
    herring: dict = field(init=False)    # truth or None
    misleading: dict = field(init=False)  # F13 team message (truth) or None
    alert_noise: list = field(init=False)  # [(t, service, text, duration)]
    alert_target: int = field(init=False)

    def __post_init__(self):
        if self.difficulty not in SLOTS:
            raise ValueError(f"unknown difficulty {self.difficulty!r}")
        rng = Random(f"{self.seed}|{self.salt}|build")
        tname = rng.choice(sorted(TEMPLATES))
        self.template = tname
        roles, redges = TEMPLATES[tname]
        names = {r: rng.choice(pool) for r, _, pool in roles}
        self.order = [names[r] for r, _, _ in roles]
        pos = {r: i for i, (r, _, _) in enumerate(roles)}
        assert all(pos[a] < pos[b] for a, b, *_ in redges), "template edges must follow role order"
        self.entry, self.edges = self.order[0], [
            Edge(names[a], names[b], f, bool(c), bool(fb), bool(vc)) for a, b, f, c, fb, vc in redges]
        kinds = {names[r]: k for r, k, _ in roles}
        self.db = next(n for n in self.order if kinds[n] == "db")
        self.cache = next(n for n in self.order if kinds[n] == "cache")
        self.external = next(n for n in self.order if kinds[n] == "external")
        self.queue = next(n for n in self.order if kinds[n] == "queue")
        self.worker = next(e.callee for e in self.edges if e.caller == self.queue)
        hit = rng.uniform(.88, .94)
        base_rps = rng.uniform(300, 900)
        self.params = {"base_rps": base_rps, "phase": rng.randrange(1440), "hit_base": hit, "slo_ms": 800}
        # nominal traffic share per node (no errors, CB closed)
        share = {n: 0.0 for n in self.order}
        share[self.entry] = 1.0
        for n in self.order:
            for e in self.edges:
                if e.caller == n:
                    share[e.callee] += share[n] * e.fanout * ((1 - hit) if e.via_cache else 1)
        self.share = share
        crit = {n: 0.0 for n in self.order}     # share of entry traffic reached through critical edges only
        crit[self.entry] = 1.0
        for n in self.order:
            for e in self.edges:
                if e.caller == n and e.critical:
                    crit[e.callee] += crit[n] * e.fanout * ((1 - hit) if e.via_cache else 1)
        self.crit = crit
        self.p50 = {}                     # nominal p50 (ms) per node, used to plan latency-sensitive faults
        # node parameters
        self.nodes = {}
        for r, k, _ in roles:
            n = names[r]
            load = share[n] * base_rps
            sp = NodeSpec(name=n, role=r, kind=k, entry=(n == self.entry))
            if k == "app":
                sp.replicas = rng.randint(2, 6)
                sp.cap = max(20, math.ceil(load / (sp.replicas * rng.uniform(.3, .5))))
                sp.base_ms = rng.uniform(4, 9)
                sp.cost = rng.randint(1, 3)
            elif k == "db":
                sp.replicas = rng.randint(1, 3)
                sp.cap = max(20, math.ceil(load / (sp.replicas * rng.uniform(.48, .52))))
                sp.base_ms = rng.uniform(5, 8)
                sp.cost = rng.randint(4, 6)
                sp.in_sync = rng.random() < .5
            elif k == "queue":
                sp.replicas, sp.cost = 1, 1
                sp.cap = max(20, math.ceil(load / rng.uniform(.1, .2)))
                sp.base_ms = 3.0
            elif k == "cache":
                sp.replicas = rng.randint(2, 3)
                sp.cap = max(20, math.ceil(load / (sp.replicas * rng.uniform(.15, .25))))
                sp.base_ms = 2.0
                sp.cost = 2
                sp.hit_base = hit
            else:
                sp.replicas, sp.cost = 1, 0
                sp.cap = max(20, math.ceil(load / rng.uniform(.15, .25)))
                sp.base_ms = rng.uniform(15, 25)
            sp.threads = max(20, 2 * sp.cap)
            sp.tail = rng.uniform(2.5, 3.2)
            sp.cold_start = rng.randint(2, 4)
            sp.mem_mb = rng.choice((512, 1024, 2048, 4096))
            sp.mem_base = rng.uniform(.35, .5)
            sp.disk = rng.uniform(.35, .65)
            sp.timeout_ms = rng.choice((1000, 1500, 2000))
            sp.pool_size = rng.randint(8, 20)
            self.nodes[n] = sp
        conn_ratio = rng.uniform(.6, .75)     # max_connections is derived after planning (planners may resize clients)
        for n in reversed(self.order):
            sp = self.nodes[n]
            util = share[n] * base_rps / (sp.replicas * sp.cap)
            self.p50[n] = sp.base_ms / (1 - util) + sum(      # a queue's consumer is asynchronous
                e.fanout * ((1 - hit) if e.via_cache else 1) * self.p50[e.callee] for e in self.children(n)
                if sp.kind != "queue")
        # old deploy history (all t <= -200)
        self.deploys = {}
        for n in self.order:
            if self.nodes[n].kind == "external":
                continue
            k = rng.randint(2, 4)
            ts = sorted(-rng.randint(250, 3000) for _ in range(k))
            v = f"v{rng.randint(1, 3)}.{rng.randint(0, 9)}.0"
            hist = []
            for t in ts:
                hist.append({"version": v, "t": t, "by": rng.choice(ACTORS), "has_schema_migration": False,
                             "reversible": True})
                v = _bump(v, minor=rng.random() < .6)
            self.deploys[n] = hist
        # flags
        self.flags, self.flag_audit = [], []
        for fname in rng.sample(faults.FLAG_NAMES, rng.randint(4, 6)):
            on = rng.random() < .5
            eff = None
            if rng.random() < .3:
                eff = (rng.choice([n for n in self.order if self.nodes[n].kind == "app"]), rng.randint(20, 60))
            self.flags.append({"name": fname, "on": on, "effect": eff})
            if on:
                self.flag_audit.append({"t": -rng.randint(300, 3000), "flag": fname, "on": True,
                                        "by": rng.choice(ACTORS)})
        # faults: primary (+ F14 partner), concurrent components, then the trap and the add-on of the recipe
        used = []
        diff = self.difficulty
        slots = SLOTS[diff]
        label, prim, comps, trap, addon = slots[self.seed % len(slots)]
        self.family = label
        onset = rng.randint(-8, -3)
        if prim == "cascade":
            specs = faults.plan_cascade(self, rng, onset, used)
        else:
            specs = [faults.plan(prim, self, rng, onset, used)]

        def claim(ss):
            used.extend(n for s in ss for n in (s["node"], s.get("caller"), s.get("biller"), s.get("deploy_node"),
                                                *s.get("also", ())) if n)
        claim(specs)
        for alts in comps:
            for f2 in alts:
                if f2 == "retry_storm" and any(s["fault_class"] in DB_FAULTS for s in specs):
                    continue
                try:
                    s2 = faults.plan(f2, self, rng, onset, used, role="concurrent")
                except ValueError:
                    continue
                specs.append(s2)
                claim([s2])
                break
            else:
                raise ValueError(f"no component for {alts} in seed {self.seed}")
        self.herring = self.misleading = None
        if trap in ("herring", "message"):
            hn = specs[0]["node"] if (prim in ("config_drift", "clock_skew") and trap == "herring" and rng.random() < .5) else rng.choice(
                [n for n in self.order if self.nodes[n].kind == "app" and n not in used and self.nodes[n].role != "worker"
                 and not self.nodes[n].entry and self.share[n] >= .2])
            th = onset + rng.randint(-3, 3)
            self.herring = {"node": hn, "t": th, "version": _bump(self.deploys[hn][-1]["version"])}
            if hn not in used:
                used.append(hn)
            if trap == "message":
                self.misleading = {"node": hn, "t": rng.randint(0, 5), "text": (
                    f"{rng.choice(ACTORS[:4])} (platform-team): errors started right after the {hn} "
                    f"{self.herring['version']} deploy, recommend rolling back {hn} asap")}
        if addon == "bomb":
            specs.append(faults.plan("cert_expiry", self, rng, onset, used, role="bomb"))
        elif addon == "second":
            others = [f for f in SECOND_POOL if not (f == "retry_storm" and any(s["fault_class"] in DB_FAULTS for s in specs))]
            rng.shuffle(others)
            t2 = rng.randint(40, 50)
            for f2 in others:
                try:
                    specs.append(faults.plan(f2, self, rng, t2, used, role="second"))
                    break
                except ValueError:
                    continue
        self.faults = specs
        fnodes = [s["node"] for s in specs]
        self.id = f"{diff[:3]}-{label.lower()}-{self.seed}"
        demand = sum(self.nodes[e.caller].replicas * self.nodes[e.caller].pool_size
                     for e in self.edges if e.callee == self.db)
        self.nodes[self.db].max_conn = math.ceil(demand / conn_ratio)
        # irreversible migrations on 1-2 non-fault nodes (rolling back past them loses data)
        cand = [n for n in self.order if n in self.deploys and n not in fnodes
                and (not self.herring or n != self.herring["node"])]
        for n in rng.sample(cand, rng.randint(1, 2)):
            self.deploys[n][1].update(has_schema_migration=True, reversible=False)
        # innocent old config audit entries
        self.cfg_audit = {n: [] for n in self.order}
        for n in rng.sample([n for n in self.order if self.nodes[n].kind == "app"], 3):
            self.cfg_audit[n].append({"t": -rng.randint(300, 3000), "key": "log_level", "old": "WARN",
                                      "new": "INFO", "by": rng.choice(ACTORS)})
        # harmless WARN noise
        self.warns = []
        for _ in range(rng.randint(5, 8)):
            self.warns.append((rng.randint(-28, T - 5), rng.choice(self.order[:-1]), rng.choice(WARN_TEXTS)))
        self.warns.sort()
        self.alert_noise = sorted((rng.randint(-25, -1), rng.choice(self.order), rng.choice(ALERT_NOISE).format(
            a=rng.randint(610, 980), b=rng.randint(2, 7)), rng.randint(28, 60)) for _ in range(rng.randint(6, 8)))
        self.alert_target = rng.randint(6, 10)      # get_status pads the real alerts with noise up to this many

    @property
    def key(self):
        return (self.id, self.salt)

    def children(self, n):
        return [e for e in self.edges if e.caller == n]


# recipe indices per suite (see SLOTS); stratified so every R mechanism and every v1 hard mechanism is a primary or a component
DEV_MEDIUM = tuple(range(10))
DEV_HARD = tuple(range(10))
DEV_EXPERT = tuple(range(10))
JUDGE_MEDIUM = (1, 3, 5, 7, 8, 9)
JUDGE_HARD = tuple(range(10))
JUDGE_EXPERT = tuple(range(8))
FAST = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22)       # 3 medium, 5 hard, 4 expert


def _plan(diff, seeds, salt=""):
    return [Scenario(s, diff, salt) for s in seeds]


def _slots(diff, base, idxs):
    """One scenario per requested recipe index of `diff` (seed % len(recipes) == index), seeds close to `base`."""
    n = len(SLOTS[diff])
    return _plan(diff, [base + (i - base) % n for i in idxs])


MIX = ["medium"] * 25 + ["hard"] * 40 + ["expert"] * 35


def suite(name):
    if name == "dev":       # 10 / 10 / 10; every R1..R14 and the v1 hard mechanisms appear
        return (_slots("medium", 1000, DEV_MEDIUM) + _slots("hard", 1010, DEV_HARD) + _slots("expert", 1030, DEV_EXPERT))
    if name in ("judge", "judge-fast"):      # 6 / 10 / 8
        sc = (_slots("medium", 2000, JUDGE_MEDIUM) + _slots("hard", 2010, JUDGE_HARD) + _slots("expert", 2030, JUDGE_EXPERT))
        return sc if name == "judge" else [sc[i] for i in FAST]
    if name == "heldout":
        salt = os.environ.get("ONCALL_HELDOUT_SALT")
        if not salt:
            raise RuntimeError("ONCALL_HELDOUT_SALT is not set")
        rng = Random(f"heldout|{salt}")
        return [Scenario(rng.randrange(10 ** 6), d, salt) for d in MIX]
    if name == "train":
        return [Scenario(10000 + i, d) for i, d in enumerate(MIX)]
    raise ValueError(f"unknown suite {name!r}")
