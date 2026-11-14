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


# 300 generated scenarios (60 easy, 100 medium, 140 hard): every family F1..F14 appears several times
SWEEP = ([Scenario(s, "easy") for s in range(3000, 3060)] + [Scenario(s, "medium") for s in range(4000, 4100)]
         + [Scenario(s, "hard") for s in range(5000, 5140)])


def test_sweep_covers_every_family_and_class():
    assert len(SWEEP) == 300
    assert {sc.family for sc in SWEEP} == set(scenarios.LABELS)
    assert {f["fault_class"] for sc in SWEEP for f in sc.faults} == set(scenarios.FAMILIES)


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


def visible(env, f, tool):
    s, node, cls = f.spec, f.node, f.fault_class
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
            return bool(_lines(env, node, "slow path" if s["variant"] == "flag" else "deadline exceeded"))
        if cls == "cert_expiry":
            return bool(_lines(env, node, "TLS"))
        if cls == "disk_full":
            return bool(_lines(env, node, "disk usage") or _lines(env, node, "no space"))
        if cls == "cache_stampede":
            return bool(_lines(env, node, "hit ratio"))
        if cls == "poison_message":
            return bool(_lines(env, node, f"msg_id={s['msg_id']}"))
        if cls == "bad_canary":
            return bool(_lines(env, node, "canary"))
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
    for sc in DEV:
        for spec in sc.faults:
            f = faults.build(spec)
            assert len(f.signals) >= 2 and len(set(f.signals)) == len(f.signals)
            seen.add((f.fault_class, spec.get("variant")))
    assert {c for c, _ in seen} == set(scenarios.FAMILIES) and len(seen) == 13     # + 2 config_drift variants


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
