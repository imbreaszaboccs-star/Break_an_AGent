"""Scenario generator: 3 templates, seeded renaming/params, faults, herring, suites."""
import math
import os
from collections import namedtuple
from dataclasses import dataclass, field
from random import Random

from . import faults

T, E, WARM = 120, 45, 30            # episode ticks, epilog ticks, warm-up history ticks
FAMILIES = ("bad_deploy", "memory_leak", "retry_storm", "config_drift", "external_dependency")
EASY_FAMILIES = ("bad_deploy", "retry_storm", "config_drift", "external_dependency")
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
         ("cache", "cache", ("redis-cache", "session-cache", "cache-main")),
         ("db", "db", ("orders-db", "postgres-main", "pg-primary")),
         ("pay", "external", ("payments-gw", "stripe-proxy", "psp-adapter"))],
        [("gw", "search", .4, 1, 0, 0), ("gw", "catalog", .8, 1, 0, 0), ("gw", "cart", .5, 1, 0, 0),
         ("gw", "recs", .5, 0, 1, 0), ("gw", "checkout", .4, 1, 0, 0),
         ("search", "catalog", .3, 1, 0, 0),
         ("catalog", "cache", 1, 0, 1, 0), ("catalog", "db", .5, 1, 0, 1), ("catalog", "inventory", .4, 1, 0, 0),
         ("cart", "cache", 1, 0, 1, 0), ("cart", "db", .2, 1, 0, 1),
         ("recs", "cache", 1, 0, 1, 0),
         ("checkout", "orders", 1, 1, 0, 0), ("checkout", "inventory", 1, 1, 0, 0), ("checkout", "pay", 1, 1, 1, 0),
         ("orders", "db", 1, 1, 0, 0)]),
    "saas": (
        [("api", "app", ("api-gateway", "public-api", "gateway", "api-edge")),
         ("auth", "app", ("auth", "auth-svc", "identity")),
         ("projects", "app", ("projects", "projects-api", "workspace-svc")),
         ("tenants", "app", ("tenants", "tenant-svc", "accounts")),
         ("reports", "app", ("reports", "report-svc", "analytics-api")),
         ("usage", "app", ("usage-meter", "metering", "usage-svc")),
         ("billing", "app", ("billing", "billing-svc", "invoicing")),
         ("notify", "app", ("notifications", "notify-svc", "alerts-api")),
         ("cache", "cache", ("session-cache", "redis-main", "cache-cluster")),
         ("db", "db", ("saas-db", "postgres-core", "pg-main")),
         ("mail", "external", ("email-provider", "sendgrid-proxy", "mail-relay"))],
        [("api", "auth", 1, 1, 0, 0), ("api", "projects", .6, 1, 0, 0), ("api", "tenants", .3, 1, 0, 0),
         ("api", "usage", .5, 0, 1, 0), ("api", "reports", .25, 1, 0, 0), ("api", "billing", .4, 1, 0, 0),
         ("auth", "cache", 1, 0, 1, 0), ("auth", "db", .3, 1, 0, 1),
         ("projects", "db", .8, 1, 0, 0),
         ("tenants", "db", .1, 1, 0, 1),
         ("usage", "cache", 1, 0, 1, 0),
         ("reports", "usage", 1, 1, 0, 0), ("reports", "cache", 1, 0, 1, 0),
         ("billing", "db", .2, 1, 0, 0), ("billing", "notify", .5, 0, 1, 0), ("billing", "mail", 1, 1, 1, 0),
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
         ("cache", "cache", ("edge-cache", "redis-media", "cache-main")),
         ("db", "db", ("media-db", "postgres-media", "pg-primary")),
         ("origin", "external", ("cdn-origin", "origin-storage", "blob-origin"))],
        [("edge", "playlist", .7, 1, 0, 0), ("edge", "catalog", .6, 1, 0, 0), ("edge", "accounts", .8, 1, 0, 0),
         ("edge", "recs", .4, 0, 1, 0), ("edge", "thumbs", .5, 0, 1, 0), ("edge", "upload", .15, 1, 0, 0),
         ("playlist", "catalog", .5, 1, 0, 0), ("playlist", "origin", 1, 1, 1, 0),
         ("catalog", "cache", 1, 0, 1, 0), ("catalog", "db", .4, 1, 0, 1),
         ("accounts", "db", .5, 1, 0, 0), ("accounts", "cache", 1, 0, 1, 0),
         ("recs", "cache", 1, 0, 1, 0), ("thumbs", "cache", 1, 0, 1, 0),
         ("upload", "transcode", 1, 1, 0, 0), ("transcode", "db", .1, 1, 0, 0)]),
}

WARN_TEXTS = ("deprecated API v1 endpoint still receiving ~12 calls/min",
              "GC pause 480ms observed (p99 over 5m)",
              "disk usage 71% on /var/log",
              "TLS certificate expires in 54 days",
              "autoscaler cooldown active, skipping scale-in",
              "config reload took 1.8s",
              "slow query log: 3 queries >500ms in last 10m",
              "clock skew 140ms vs ntp pool")
ACTORS = ("alice", "bob", "carol", "dave", "ci-bot")


@dataclass
class NodeSpec:
    name: str
    role: str
    kind: str                # app | db | cache | external
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
    template: str = field(init=False)
    nodes: dict = field(init=False)      # name -> NodeSpec, in topological order
    order: list = field(init=False)
    edges: list = field(init=False)
    entry: str = field(init=False)
    db: str = field(init=False)
    cache: str = field(init=False)
    external: str = field(init=False)
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

    def __post_init__(self):
        if self.difficulty not in ("easy", "medium", "hard"):
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
        demand = sum(self.nodes[e.caller].replicas * self.nodes[e.caller].pool_size
                     for e in self.edges if e.callee == self.db)
        self.nodes[self.db].max_conn = math.ceil(demand / rng.uniform(.6, .75))
        for n in reversed(self.order):
            sp = self.nodes[n]
            util = share[n] * base_rps / (sp.replicas * sp.cap)
            self.p50[n] = sp.base_ms / (1 - util) + sum(
                e.fanout * ((1 - hit) if e.via_cache else 1) * self.p50[e.callee] for e in self.children(n))
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
        # faults
        used = []
        diff = self.difficulty
        fams = EASY_FAMILIES if diff == "easy" else FAMILIES
        fam = fams[self.seed % len(fams)]
        onset = rng.randint(-8, -3)
        specs = [faults.plan(fam, self, rng, onset, used)]
        used.extend(n for n in (specs[0]["node"], specs[0].get("caller")) if n)
        self.herring = None
        if diff != "easy":
            hn = specs[0]["node"] if (fam == "config_drift" and rng.random() < .5) else rng.choice(
                [n for n in self.order if self.nodes[n].kind == "app" and n not in used
                 and not self.nodes[n].entry and self.share[n] >= .2])
            th = onset + rng.randint(-3, 3)
            self.herring = {"node": hn, "t": th, "version": _bump(self.deploys[hn][-1]["version"])}
            if hn not in used:
                used.append(hn)
        if diff == "hard":
            others = [f for f in FAMILIES if f != fam]
            rng.shuffle(others)
            t2 = rng.randint(40, 50)
            for f2 in others:
                try:
                    specs.append(faults.plan(f2, self, rng, t2, used))
                    break
                except ValueError:
                    continue
        self.faults = specs
        fnodes = [s["node"] for s in specs]
        self.id = f"{diff[:3]}-f{FAMILIES.index(fam) + 1}-{self.seed}"
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

    @property
    def key(self):
        return (self.id, self.salt)

    def children(self, n):
        return [e for e in self.edges if e.caller == n]


def _plan(diff, seeds, salt=""):
    return [Scenario(s, diff, salt) for s in seeds]


def suite(name):
    if name == "dev":
        return (_plan("easy", range(1000, 1010)) + _plan("medium", range(1010, 1020))
                + _plan("hard", range(1020, 1030)))
    if name == "judge":
        return (_plan("easy", range(2000, 2004)) + _plan("medium", range(2004, 2012))
                + _plan("hard", range(2012, 2024)))
    if name == "judge-fast":
        return (_plan("easy", (2000, 2001)) + _plan("medium", range(2004, 2008))
                + _plan("hard", range(2012, 2018)))
    if name == "heldout":
        salt = os.environ.get("ONCALL_HELDOUT_SALT")
        if not salt:
            raise RuntimeError("ONCALL_HELDOUT_SALT is not set")
        rng = Random(f"heldout|{salt}")
        diffs = ["easy"] * 20 + ["medium"] * 30 + ["hard"] * 50
        return [Scenario(rng.randrange(10 ** 6), d, salt) for d in diffs]
    if name == "train":
        diffs = ["easy"] * 20 + ["medium"] * 30 + ["hard"] * 50
        return [Scenario(10000 + i, d) for i, d in enumerate(diffs)]
    raise ValueError(f"unknown suite {name!r}")
