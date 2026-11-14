import json
import statistics

import pytest

from oncall import faults, policies, scenarios
from oncall.scenarios import Scenario, suite
from oncall.sim import Env

DEV = suite("dev")


@pytest.mark.parametrize("sc", DEV, ids=lambda s: s.id)
def test_reference_solves_every_dev_scenario(sc):
    b = policies.run_policy("reference", sc)
    assert b["score"] >= 0.8, b
    assert b["R_fixed"] == 1 and b["R_diag"] == 1 and b["M_dataloss"] == 1 and b["P_collateral"] == 0


def test_reference_mean():
    scores = [policies.run_policy("reference", sc)["score"] for sc in DEV]
    assert statistics.mean(scores) >= 0.85


def test_reference_on_judge_suite():
    for sc in suite("judge"):
        assert policies.run_policy("reference", sc)["score"] >= 0.8, sc.id


# 300 generated scenarios (100 per level): every mechanism appears as a primary or a component several times
SWEEP = ([Scenario(s, "medium") for s in range(4000, 4100)] + [Scenario(s, "hard") for s in range(5000, 5100)]
         + [Scenario(s, "expert") for s in range(6000, 6100)])


def test_sweep_covers_every_family_and_class():
    assert len(SWEEP) == 300
    primaries = {sc.family for sc in SWEEP}
    assert primaries <= set(scenarios.LABELS) and {f"R{i}" for i in range(1, 15)} | {"F2", "F9", "F10", "F11", "F12", "F13", "F14"} <= primaries
    assert {f["fault_class"] for sc in SWEEP for f in sc.faults} == set(scenarios.FAMILIES)
    for cls in scenarios.FAMILIES:
        assert sum(f["fault_class"] == cls for sc in SWEEP for f in sc.faults) >= 5, cls


def test_reference_minimum_per_mechanism_on_the_sweep():
    """The per-R / per-F minimum of the tool-only reference over the whole sweep (every scenario holding the mechanism)."""
    worst = {}
    for sc in SWEEP:
        b = policies.run_policy("reference", sc)
        for f in sc.faults:
            worst[f["fault_class"]] = min(worst.get(f["fault_class"], 1.0), b["score"])
    assert min(worst.values()) >= .8, worst


def test_reference_and_oracle_on_broad_sweep():
    for sc in SWEEP:
        assert policies.run_policy("reference", sc)["score"] >= 0.8, sc.id
        n, o = policies.run_policy("noop", sc), policies.run_policy("oracle", sc)
        assert o["U"] - n["U"] > 0.04 and o["score"] >= 0.99, sc.id


def test_reference_uses_only_the_call_interface():
    import inspect
    src = inspect.getsource(policies.reference)
    assert "__self__" not in src and "env" not in src.replace("environment", "")
    assert inspect.signature(policies.reference).parameters.keys() == {"call"}


# ---- every fault declares >= 2 signals and they are really visible through the tools -----------------

def _wait_until(env, t):
    while env.t < t:
        env.call("wait", minutes=min(30, t - env.t))


def _series(env, svc, metric, window=15):
    return env.call("get_metrics", services=[svc], window=window)["result"]["metrics"][svc][metric]


def _lines(env, svc, grep):
    return env.call("get_logs", service=svc, level="ALL", grep=grep, limit=200)["result"]["lines"]


def _endpoints(env):
    topo = env.call("get_topology")["result"]
    entry = next(n["name"] for n in topo["nodes"] if n["entry"])
    return ["/" + e["callee"] for e in topo["edges"] if e["caller"] == entry]


def _fanout(env, a, b):
    return next(e["fanout"] for e in env.call("get_topology")["result"]["edges"] if e["caller"] == a and e["callee"] == b)


def _biz(env, metric, window=5):
    return env.call("get_business_metrics", window=window)["result"]["metrics"][metric]


def _events(env, text):
    return any(text in e["text"] for e in env.call("get_events")["result"]["events"])


def _instances(env, svc):
    return env.call("get_instances", service=svc)["result"]["instances"]


def visible_r(env, f, tool):
    """The R1..R7 mechanisms: every declared signal must be readable through its tool."""
    s, node, cls = f.spec, f.node, f.fault_class
    if cls == "duplicate_charges":
        return {"get_business_metrics": lambda: max(_biz(env, "payment_attempts_per_order", 30)) > 1.3,
                "get_logs": lambda: bool(_lines(env, s["biller"], "triggering auto-recharge")),
                "get_metrics": lambda: max(_series(env, node, "repl_backlog_mb", 30)) > 50,
                "get_config": lambda: env.call("get_config", service=s["biller"])["result"]["config"]["read_from"] == "replica",
                }[tool]()
    if cls == "replica_lag_stale_reads":
        return {"get_metrics": lambda: max(_series(env, node, "replica_lag_s", 5)) > 60,
                "get_logs": lambda: any(_lines(env, c, "not found right after create") for c in s["clients"]),
                "get_business_metrics": lambda: sum(_biz(env, "stale_read_reports")) > 0,
                "get_config": lambda: any(env.call("get_config", service=c)["result"]["config"]["read_from"] == "replica"
                                          for c in s["clients"])}[tool]()
    if cls == "migration_lock":
        return {"get_metrics": lambda: _series(env, node, "locks_waiting", 3)[-1] > 20 and _series(env, node, "cpu", 3)[-1] < .7,
                "get_logs": lambda: bool(_lines(env, node, "ShareLock") or _lines(env, s["deploy_node"], "lock wait timeout")),
                "get_deploys": lambda: any(x.get("migration_in_progress") for x in
                                           env.call("get_deploys", service=s["deploy_node"])["result"]["deploys"][s["deploy_node"]]["history"])
                }[tool]()
    if cls == "pool_sync_recycle":
        return {"get_metrics": lambda: max(_series(env, node, "error_rate", 30)) > .3 and min(_series(env, node, "error_rate", 30)) < .05,
                "get_events": lambda: _events(env, "minor version upgraded"),
                "get_logs": lambda: bool(_lines(env, node, "too many clients"))}[tool]()
    if cls == "progressive_gray":
        return {"get_instances": lambda: any(i["error_rate"] > .9 and i["health_check"] == "passing" for i in _instances(env, node)),
                "get_events": lambda: _events(env, "unattended-upgrades"),
                "get_metrics": lambda: max(_series(env, node, "error_rate", 5)) > .1}[tool]()
    if cls == "clock_skew":
        return {"get_instances": lambda: any(abs(i["clock_offset_ms"]) > 60000 for i in _instances(env, node)),
                "get_logs": lambda: bool(_lines(env, node, "token validation failed")),
                "get_business_metrics": lambda: min(_biz(env, "login_success_rate", 5)) < .95}[tool]()
    if cls == "expired_cert_dismissed_alert":
        cfg = lambda: env.call("get_config", service=node)["result"]
        return {"get_logs": lambda: bool(_lines(env, node, "certificate verify failed")),
                "get_business_metrics": lambda: sum(_biz(env, "emails_delivered")) < .3 * sum(_biz(env, "emails_sent")),
                "get_events": lambda: _events(env, "synthetic check"),
                "get_config": lambda: (cfg()["cert_expires_at"] <= env.t if s["variant"] == "cert" else cfg()["ca_bundle"] == s["old_ca"])}[tool]()
    if cls == "mail_backlog_ramp":
        return {"get_business_metrics": lambda: sum(_biz(env, "emails_deferred", 30)) > 2 * sum(_biz(env, "emails_sent", 30)) * .05
                and max(_biz(env, "emails_deferred", 30)) > max(_biz(env, "emails_delivered", 30)),
                "get_metrics": lambda: max(_series(env, node, "queue_lag", 30)) > 3,
                "get_events": lambda: _events(env, "mail provider degraded"),
                "get_logs": lambda: bool(_lines(env, node, "deferring"))}[tool]()
    if cls == "cache_invalidation_loop":
        return {"get_metrics": lambda: min(_series(env, node, "cache_hit_rate", 30)) < .2 and max(_series(env, node, "key_deletes_per_s", 30)) > 500
                and max(_series(env, s["db"], "error_rate", 30)) > .5,
                "get_config": lambda: any(x["key"] == "timeout_ms" and x["new"] < x["old"] / 2
                                          for x in env.call("get_config", service=node)["result"]["audit"]),
                "get_logs": lambda: bool(_lines(env, node, "DEL burst"))}[tool]()
    if cls == "bad_config_push":
        entry = env.call("get_config", service=node)["result"]
        return {"get_flags": lambda: any(x["flag"] == s["flag"] and x["on"] for x in env.call("get_flags")["result"]["audit"]),
                "get_config": lambda: any(x["key"] == "waf_ruleset" and x["new"] == "candidate" for x in entry["audit"]),
                "get_metrics": lambda: min(_series(env, node, "cpu", 5)) > .9 and max(_series(env, node, "error_rate", 5)) > .3,
                "get_logs": lambda: bool(_lines(env, node, "evaluation budget"))}[tool]()
    if cls == "redis_maxmemory":
        return {"get_metrics": lambda: max(_series(env, node, "evicted_keys", 5)) > 500 and min(_series(env, node, "used_memory_ratio", 5)) > .85,
                "get_config": lambda: any(x["key"] in ("maxmemory_mb", "maxmemory_policy")
                                          for x in env.call("get_config", service=node)["result"]["audit"]),
                "get_business_metrics": lambda: min(_biz(env, "login_success_rate", 5)) < .9,
                "get_logs": lambda: bool(_lines(env, node, "evicted"))}[tool]()
    if cls == "duplicate_events":
        q = s["queue"]
        return {"get_business_metrics": lambda: sum(_biz(env, "duplicate_shipments", 10)) > 0,
                "get_metrics": lambda: _series(env, q, "rps", 3)[-1] > 1.8 * _fanout(env, node, q) * _series(env, node, "rps", 3)[-1],
                "get_logs": lambda: any(a["msg"] == b["msg"] for a, b in zip(_lines(env, node, "published event"), _lines(env, node, "published event")[1:])),
                "get_deploys": lambda: any(x["version"] == s["bad_version"] for x in env.call("get_deploys", service=node)["result"]["deploys"][node]["history"]),
                "get_flags": lambda: any(x["flag"] == s["flag"] and x["on"] for x in env.call("get_flags")["result"]["audit"])}[tool]()
    if cls == "stuck_failover":
        return {"get_logs": lambda: bool(_lines(env, node, "I/O error")) and bool(_lines(env, node, "promotion of replica refused")),
                "get_topology": lambda: next(n for n in env.call("get_topology")["result"]["nodes"] if n["name"] == node)["replica_in_sync"],
                "get_metrics": lambda: min(_series(env, node, "error_rate", 5)) > .9 and max(_series(env, node, "replica_lag_s", 5)) < 5
                }[tool]()
    if cls == "abusive_client":
        cfg = lambda: env.call("get_config", service=node)["result"]
        return {"get_metrics": lambda: _series(env, node, "conns", 1)[-1] >= cfg()["max_connections"],
                "get_logs": lambda: len({l["msg"].split("client=")[1].split()[0] for l in
                                         env.call("get_logs", service=node, level="ERROR", grep="client=", limit=100)["result"]["lines"]}) == 1
                and bool(_lines(env, node, s["id"])),
                "get_traces": lambda: any("gateway_wait_ms" in sp for ep in _endpoints(env)
                                          for tr in env.call("get_traces", endpoint=ep, n=5)["result"]["traces"] for sp in tr["spans"])}[tool]()
    raise AssertionError(cls)


R_CLASSES = ("duplicate_charges", "replica_lag_stale_reads", "migration_lock", "pool_sync_recycle", "progressive_gray",
             "clock_skew", "expired_cert_dismissed_alert", "mail_backlog_ramp", "cache_invalidation_loop", "bad_config_push",
             "redis_maxmemory", "duplicate_events", "stuck_failover", "abusive_client")


def visible(env, f, tool):
    s, node, cls = f.spec, f.node, f.fault_class
    if cls in R_CLASSES:
        return visible_r(env, f, tool)
    if tool == "get_deploys":
        d = env.call("get_deploys", service=node)["result"]["deploys"][node]
        if cls == "bad_canary":
            return bool(d["canary"] and d["canary"]["weight"] > 0)
        return any(x["version"] == s["bad_version"] and abs(x["t"] - (f.onset - 1)) <= 1 for x in d["history"])
    if tool == "get_flags":
        a = env.call("get_flags")["result"]["audit"]
        return any(x["flag"] == s["flag"] and x["on"] and x["t"] == f.onset - 1 for x in a)
    if tool == "get_config":
        c = env.call("get_config", service=node)["result"]
        if cls == "cert_expiry":
            return c["cert_expires_at"] == s["t_exp"]
        if cls == "disk_full":
            return any(x["key"] == "log_level" and x["new"] == "DEBUG" for x in c["audit"])
        key = "max_retries" if cls == "retry_storm" else "timeout_ms"
        return any(x["key"] == key and x["t"] in (f.onset - 1, f.onset - 2) and x["new"] != x["old"] for x in c["audit"])
    if tool == "get_topology":
        n = next(n for n in env.call("get_topology")["result"]["nodes"] if n["name"] == node)
        return n["replicas"] == s["small"] < s["full"]
    if tool == "get_events":
        evs = env.call("get_events")["result"]["events"]
        if cls == "cert_expiry":
            return any(node in e["text"] and "expires at" in e["text"] for e in evs)
        if cls == "disk_full":
            return any(node in e["text"] and "disk usage" in e["text"] for e in evs)
        if cls == "cache_stampede":
            return any(node in e["text"] and "flushed" in e["text"] for e in evs)
        if cls == "under_provisioned":
            return any(node in e["text"] and "scaled in" in e["text"] for e in evs)
        return any(node in e["text"] and "status page" in e["text"] for e in evs)
    if tool == "get_traces":
        for ep in _endpoints(env):
            for tr in env.call("get_traces", endpoint=ep, n=10)["result"]["traces"]:
                for sp in tr["spans"]:
                    if cls == "poison_message" and sp["service"] == s["queue"] and sp.get("message_id") == s["msg_id"]:
                        return True
                    if cls == "thread_starvation" and sp["service"] == node and sp["duration_ms"] > 400:
                        return True
        return False
    if tool == "get_logs":
        if cls == "bad_deploy":
            return bool(_lines(env, node, "NullPointerException"))
        if cls == "memory_leak":
            return bool(_lines(env, node, "GC overhead") or _lines(env, node, "OOMKilled"))
        if cls == "retry_storm":
            return bool(_lines(env, node, "retrying call to"))
        if cls == "config_drift":
            if s["variant"] == "flag":
                return any(int(x["msg"].split("dur=")[1].split("ms")[0]) >= 900 for x in _lines(env, node, "slow request dur="))
            return bool(_lines(env, node, "deadline exceeded"))
        if cls == "cert_expiry":
            return bool(_lines(env, node, "TLS"))
        if cls == "disk_full":
            return bool(_lines(env, node, "disk usage") or _lines(env, node, "no space"))
        if cls == "cache_stampede":
            return bool(_lines(env, node, "hit ratio"))
        if cls == "poison_message":
            return bool(_lines(env, node, f"msg_id={s['msg_id']}"))
        if cls == "bad_canary":
            return bool(_lines(env, node, "upstream timeout after 4000ms"))
        if cls == "thread_starvation":
            return bool(_lines(env, node, "slow responses"))
        return bool(_lines(env, s["caller"], node))
    if tool == "get_metrics":
        if cls in ("bad_deploy", "external_dependency"):
            return max(_series(env, node, "error_rate", 5)) > 0.3
        if cls == "memory_leak":
            mem = _series(env, node, "mem")
            return max(mem) - min(mem) > 0.2
        if cls == "retry_storm":
            return max(_series(env, s["db"], "error_rate", 5)) > 0.3 and max(_series(env, node, "retries", 5)) > 10
        if cls == "config_drift":
            return (_series(env, node, "p50", 3)[-1] > 500 if s["variant"] == "flag"
                    else max(_series(env, node, "error_rate", 5)) > 0.1)
        if cls == "disk_full":
            return max(_series(env, node, "disk", 5)) > 0.9
        if cls == "cache_stampede":
            return min(_series(env, node, "cache_hit_rate", 5)) < 0.2
        if cls == "poison_message":
            return max(_series(env, s["queue"], "queue_lag", 5)) > 2
        if cls == "bad_canary":
            p50, p99, err = (_series(env, node, m, 3)[-1] for m in ("p50", "p99", "error_rate"))
            return p99 > 8 * p50 and 0.01 < err < 0.1
        if cls == "thread_starvation":
            return (max(_series(env, s["caller"], "worker_util", 3)) > 1 and max(_series(env, node, "error_rate", 3)) < .02
                    and _series(env, node, "p99", 3)[-1] > 1500)
        raise AssertionError(cls)
    raise AssertionError(tool)


def test_every_fault_class_declares_two_signals():
    assert set(faults.CLASSES) == set(scenarios.FAMILIES)
    seen = set()
    for sc in DEV + suite("judge"):
        for spec in sc.faults:
            f = faults.build(spec)
            assert len(f.signals) >= 2 and len(set(f.signals)) == len(f.signals)
            assert f.fault_class not in " ".join(f.signals)
            seen.add((f.fault_class, spec.get("variant")))
    assert {c for c, _ in seen} == set(scenarios.FAMILIES)
    assert {v for c, v in seen if c == "config_drift"} == {"flag", "timeout"}


@pytest.mark.parametrize("sc", DEV, ids=lambda s: s.id)
def test_declared_signals_are_visible_through_tools(sc):
    env = Env(sc)
    for f in sorted(env.w.faults, key=lambda f: f.onset):
        _wait_until(env, max(f.onset + 20, 25))
        for tool in f.signals:
            assert visible(env, f, tool), f"{sc.id}: {f.fault_class} not visible via {tool}"


# ---- scenario sanity --------------------------------------------------------------------------------

@pytest.mark.parametrize("sc", suite("dev") + suite("judge"), ids=lambda s: s.id)
def test_template_and_scenario_invariants(sc):
    kinds = [n.kind for n in sc.nodes.values()]
    assert [kinds.count(k) for k in ("db", "cache", "external")] == [1, 1, 1]
    assert 6 <= kinds.count("app") - 1 <= 8 and sum(n.entry for n in sc.nodes.values()) == 1
    pos = {n: i for i, n in enumerate(sc.order)}
    assert all(pos[e.caller] < pos[e.callee] for e in sc.edges)              # DAG
    demand = sum(sc.nodes[e.caller].replicas * sc.nodes[e.caller].pool_size for e in sc.edges if e.callee == sc.db)
    assert 0.6 - 1e-9 <= demand / sc.nodes[sc.db].max_conn <= 0.75 + 1e-9
    for n, hist in sc.deploys.items():
        assert 2 <= len(hist) <= 4 and all(d["t"] <= -200 for d in hist)
    irrev = [n for n, h in sc.deploys.items() if any(not d["reversible"] for d in h)]
    assert 1 <= len(irrev) <= 2 and not set(irrev) & {f["node"] for f in sc.faults}
    assert 4 <= len(sc.flags) <= 6 and 5 <= len(sc.warns) <= 8
    assert kinds.count("queue") == 1 and sc.nodes[sc.worker].role == "worker"
    if sc.herring:
        assert abs(sc.herring["t"] - sc.faults[0]["onset"]) <= 3
    for f in sc.faults:
        if f["fault_class"] == "retry_storm":
            assert sc.share[f["node"]] >= 0.3


@pytest.mark.parametrize("sc", suite("dev") + suite("judge"), ids=lambda s: s.id)
def test_healthy_system_stays_healthy_through_the_epilog(sc):
    healthy = Scenario(sc.seed, sc.difficulty, sc.salt)
    healthy.faults, healthy.herring = [], None
    env = Env(healthy)
    env.finish()
    from oncall.scoring import utility
    assert utility(env.w.offered, env.w.good) > 0.999
    assert not [e for e in env.w.events if e["type"] == "alert"]


@pytest.mark.parametrize("sc", DEV, ids=lambda s: s.id)
def test_agent_outputs_do_not_leak_the_truth(sc):
    env = policies.run_env("reference", sc)
    blob = json.dumps([e["result"] for e in env.log])
    for word in ("fault_class", "onset", "herring", "salt", "seed", sc.id):
        assert word not in blob, word


@pytest.mark.parametrize("sc", suite("judge") + suite("train")[:40], ids=lambda s: s.id)
def test_every_suite_scenario_has_a_real_outage_to_fix(sc):
    n, o = policies.run_policy("noop", sc), policies.run_policy("oracle", sc)
    assert o["U"] - n["U"] > 0.04 and o["score"] >= 0.99
