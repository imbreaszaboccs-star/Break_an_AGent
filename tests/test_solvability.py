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


def test_reference_generalises_beyond_dev():
    for sc in suite("judge-fast") + suite("train")[:30]:
        assert policies.run_policy("reference", sc)["score"] >= 0.8, sc.id


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


def visible(env, f, tool):
    s, node, cls = f.spec, f.node, f.fault_class
    if tool == "get_deploys":
        h = env.call("get_deploys", service=node)["result"]["deploys"][node]["history"]
        return any(d["version"] == s["bad_version"] and abs(d["t"] - (f.onset - 1)) <= 1 for d in h)
    if tool == "get_flags":
        a = env.call("get_flags")["result"]["audit"]
        return any(x["flag"] == s["flag"] and x["on"] and x["t"] == f.onset - 1 for x in a)
    if tool == "get_config":
        a = env.call("get_config", service=node)["result"]["audit"]
        key = "max_retries" if cls == "retry_storm" else "timeout_ms"
        return any(x["key"] == key and x["t"] in (f.onset - 1, f.onset - 2) and x["new"] != x["old"] for x in a)
    if tool == "get_events":
        return any(node in e["text"] and "status page" in e["text"] for e in env.call("get_events")["result"]["events"])
    if tool == "get_logs":
        if cls == "bad_deploy":
            return bool(_lines(env, node, "NullPointerException"))
        if cls == "memory_leak":
            return bool(_lines(env, node, "GC overhead") or _lines(env, node, "OOMKilled"))
        if cls == "retry_storm":
            return bool(_lines(env, node, "retrying call to"))
        if cls == "config_drift":
            return bool(_lines(env, node, "slow path" if s["variant"] == "flag" else "deadline exceeded"))
        return bool(_lines(env, s["caller"], node))
    if tool == "get_metrics":
        if cls == "bad_deploy":
            return max(_series(env, node, "error_rate", 5)) > 0.2
        if cls == "memory_leak":
            mem = _series(env, node, "mem")
            return max(mem) - min(mem) > 0.2
        if cls == "retry_storm":
            return max(_series(env, s["db"], "error_rate", 5)) > 0.3 and max(_series(env, node, "retries", 5)) > 10
        if cls == "config_drift":
            return (_series(env, node, "p50", 3)[-1] > 500 if s["variant"] == "flag"
                    else max(_series(env, node, "error_rate", 5)) > 0.1)
        return max(_series(env, node, "error_rate", 5)) > 0.3
    raise AssertionError(tool)


def test_every_fault_class_declares_two_signals():
    assert set(faults.CLASSES) == set(scenarios.FAMILIES)
    seen = set()
    for sc in DEV:
        for spec in sc.faults:
            f = faults.build(spec)
            assert len(f.signals) >= 2 and len(set(f.signals)) == len(f.signals)
            seen.add((f.fault_class, spec.get("variant")))
    assert len(seen) == 6        # 4 classes + 2 config_drift variants


@pytest.mark.parametrize("sc", DEV, ids=lambda s: s.id)
def test_declared_signals_are_visible_through_tools(sc):
    env = Env(sc)
    for f in env.w.faults:
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
