import hashlib
import json

import pytest

from oncall import policies, scenarios
from oncall.scenarios import Scenario, suite
from oncall.sim import Env

PICKS = [("easy", 1003), ("medium", 1011), ("hard", 1021), ("hard", 1027)]


def digest(env, breakdown):
    blob = json.dumps({"log": env.log, "bd": breakdown}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def run(name, diff, seed):
    env = policies.run_env(name, Scenario(seed, diff))
    return env, env.finalize()


@pytest.mark.parametrize("name", ["reference", "oracle", "exploit_fuzz", "exploit_restart_all"])
@pytest.mark.parametrize("diff,seed", PICKS)
def test_same_actions_same_hash(name, diff, seed):
    a, b = run(name, diff, seed), run(name, diff, seed)
    assert digest(*a) == digest(*b)


def test_scenario_is_pure_function_of_inputs():
    a, b = Scenario(1021, "hard"), Scenario(1021, "hard")
    assert repr(a) == repr(b) and a.id == b.id
    assert repr(Scenario(1021, "hard", salt="x")) != repr(a)
    before = repr(a)
    policies.run_env("reference", a).finalize()
    assert repr(a) == before, "running an episode must not mutate the scenario"


class Observer:
    """Only observes, in a fixed rotation, until the episode is over."""

    def __call__(self, call):
        topo = call("get_topology")["result"]
        names = [n["name"] for n in topo["nodes"]]
        i = 0
        while True:
            r = [call("get_status"), call("get_metrics", services=names[:5], window=7),
                 call("get_logs", service=names[i % len(names)], limit=20), call("get_events"),
                 call("get_flags"), call("get_deploys")][i % 6]
            i += 1
            if not r["ok"]:
                return


@pytest.mark.parametrize("diff,seed", PICKS)
def test_observing_does_not_change_the_world(diff, seed):
    sc = Scenario(seed, diff)
    noop = Env(sc)
    noop.finish()
    obs = Env(sc)
    Observer()(obs.call)
    obs.finish()
    assert obs.n_calls > 20
    assert obs.w.offered == noop.w.offered and obs.w.good == noop.w.good
    assert obs.w.spend == noop.w.spend


@pytest.mark.parametrize("diff,seed", PICKS)
def test_traffic_and_faults_are_common_random_numbers(diff, seed):
    sc = Scenario(seed, diff)
    offered = []
    for name in ("noop", "reference", "oracle", "exploit_scale_max"):
        env = policies.run_env(name, sc)
        env.finish()
        offered.append(env.w.offered)
    assert all(o == offered[0] for o in offered)


def test_metric_noise_is_keyed_by_call_not_by_history():
    sc = Scenario(1011, "medium")
    a, b = Env(sc), Env(sc)
    a.call("get_status")                       # extra call history on `a`, brought back to the same clock
    a.call("get_status")
    b.call("wait", minutes=2)
    names = [n for n in sc.order][:3]
    assert a.call("get_metrics", services=names) == b.call("get_metrics", services=names)


def test_invalid_calls_cost_one_tick_and_change_nothing():
    env = Env(Scenario(1000, "easy"))
    t0 = env.t
    for tool, args in [("nope", {}), ("get_metrics", {"services": []}), ("scale", {"service": "zzz", "replicas": 3}),
                       ("get_logs", {"service": env.sc.entry, "limit": 9999}), ("wait", {"minutes": 0}),
                       ("get_status", {"extra": 1})]:
        r = env.call(tool, **args)
        assert r["ok"] is False and "error" in r
    assert env.t == t0 + 6


def test_garbage_argument_types_are_rejected_not_raised():
    env = Env(Scenario(1000, "easy"))
    for tool, args in [("set_flag", {"flag": [], "on": True}), ("run_maintenance", {"service": {}, "action": []}),
                       ("get_runbook", {"topic": []}), ("set_circuit_breaker", {"service": "a", "dep": [], "mode": "x"}),
                       ("resolve_incident", {"root_causes": [{"service": [], "fault_class": {}}]}),
                       ("rollback", {"service": 1, "version": None}), ("get_metrics", {"services": [[]]})]:
        assert env.call(tool, **args)["ok"] is False


def test_episode_end_conditions():
    env = Env(Scenario(1000, "easy"))
    assert env.call("resolve_incident", root_causes=[], summary="x")["ok"]
    assert env.call("get_status") == {"ok": False, "t": 0, "error": "episode over"}
    env = Env(Scenario(1000, "easy"))
    while not env.done:
        env.call("wait", minutes=30)
    assert env.t >= scenarios.T and env.call("get_status")["error"] == "episode over"
    assert env.finalize() is env.finalize()


def test_suites():
    dev, judge, fast = suite("dev"), suite("judge"), suite("judge-fast")
    assert [len(s) for s in (dev, judge, fast)] == [30, 24, 12]
    assert {s.id for s in fast} <= {s.id for s in judge}
    for s in (dev, judge):      # every report label F1..F14 and every fault class appears
        assert {sc.family for sc in s} == set(scenarios.LABELS)
        assert {f["fault_class"] for sc in s for f in sc.faults} == set(scenarios.FAMILIES)
    assert [sc.difficulty for sc in dev].count("hard") == 10 and [sc.difficulty for sc in judge].count("hard") == 12
    for sc in dev + judge:
        roles = [f["role"] for f in sc.faults]
        assert roles[0] == "primary" and -8 <= sc.faults[0]["onset"] <= -3
        if sc.difficulty == "easy":
            assert len(sc.faults) == 1 and sc.herring is None and sc.misleading is None
            assert sc.faults[0]["fault_class"] in ("bad_deploy", "retry_storm", "external_dependency", "disk_full")
        if sc.difficulty == "medium":     # exactly one fault and one trap
            assert len(sc.faults) == 1 and (bool(sc.herring) or sc.family in ("F11", "F12"))
            assert bool(sc.misleading) == (sc.family == "F13")
        if sc.difficulty == "hard":
            assert ("second" in roles) != ("bomb" in roles) and sc.misleading is None
            assert sc.faults[0]["fault_class"] in ("cache_stampede", "poison_message", "bad_deploy", "memory_leak")
        for f in sc.faults:
            if f["role"] == "second":
                assert 40 <= f["onset"] <= 50
            if f["role"] == "bomb":
                assert 55 <= f["onset"] <= 75 and f["warn_t"] < 0
        if sc.family == "F14":
            assert [f["fault_class"] for f in sc.faults[:2]] == [sc.faults[0]["fault_class"], "under_provisioned"]
            assert sc.faults[0]["cascade"]
    assert [sc.id for sc in suite("dev")] == [sc.id for sc in dev]


def test_heldout_needs_salt(monkeypatch):
    monkeypatch.delenv("ONCALL_HELDOUT_SALT", raising=False)
    with pytest.raises(RuntimeError):
        suite("heldout")
    monkeypatch.setenv("ONCALL_HELDOUT_SALT", "s3cret")
    a, b = suite("heldout"), suite("heldout")
    assert len(a) == 100 and [x.seed for x in a] == [x.seed for x in b]
    monkeypatch.setenv("ONCALL_HELDOUT_SALT", "other")
    assert [x.seed for x in suite("heldout")] != [x.seed for x in a]
