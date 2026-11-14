"""Mechanics of the F6-F14 families (and the masked-fix behaviour of F2/F7) that the generic suites do not pin down."""
import pytest

from helpers import with_class
from oncall import policies
from oncall.scenarios import Scenario, suite
from oncall.sim import Env

POOL = suite("dev") + suite("judge")


def sc_of(family, pred=lambda s: True):
    return next(s for s in POOL if s.family == family and pred(s))


def run(sc, *calls, wait=0):
    env = Env(sc)
    for tool, args in calls:
        assert env.call(tool, **args)["ok"], (tool, args)
    if wait:
        env.call("wait", minutes=wait)
    return env


def prev_version(env, node):
    h = [d for d in env.call("get_deploys", service=node)["result"]["deploys"][node]["history"] if "rollback" not in d["by"]]
    return h[-2]["version"]


def end_err(env, node, n=10):
    return [r[node]["err"] for r in env.w.rec[-n:]]


# ---- F2 / F7: a masked fix regresses before the end of the epilog -------------------------------------
def test_f2_restart_is_masked_and_leak_returns():
    sc, _ = with_class("memory_leak", roles=("primary",), diff="medium")
    node = sc.faults[0]["node"]
    env = run(sc, ("restart", {"service": node}))
    b = env.finalize()
    assert b["fixed"][0] is False and "masked_fix" in b["tags"]
    assert max(r[node]["mem"] for r in env.w.rec[-30:]) > .6          # the leak is back in the epilog


def test_f7_prune_alone_refills_and_restart_frees_nothing():
    sc, i = with_class("disk_full")       # (F7 only ever appears as a component now)
    node = sc.faults[i]["node"]
    prune = ("run_maintenance", {"service": node, "action": "prune_logs"})
    env = run(sc, prune, wait=0)
    b = env.finalize()
    assert b["fixed"][i] is False and env.w.nodes[node].disk >= .98 and max(end_err(env, node)) > .3
    assert "missed_event" in b["tags"]
    env = run(sc, ("restart", {"service": node}))
    assert env.finalize()["fixed"][i] is False and env.w.nodes[node].disk >= .95
    env = run(sc, prune, ("set_config", {"service": node, "key": "log_level", "value": "info"}))
    b = env.finalize()
    assert b["fixed"][i] is True and max(end_err(env, node)) < .05


# ---- F6: ticking bomb ---------------------------------------------------------------------------------------
def test_f6_expires_unless_rotated():
    sc, i = with_class("cert_expiry", roles=("bomb",))
    f = sc.faults[i]
    env = Env(sc)
    ev = [e for e in env.call("get_events")["result"]["events"] if "expires at" in e["text"]]
    assert ev and f["node"] in ev[0]["text"] and ev[0]["t"] < 0
    env.finalize()
    assert all(r[f["node"]]["err"] > .9 for r in env.w.rec[f["onset"] + 30 + 3: f["onset"] + 33 + 10])
    env = run(sc, ("run_maintenance", {"service": f["node"], "action": "rotate_cert"}))
    b = env.finalize()
    assert b["fixed"][i] is True and max(end_err(env, f["node"], 60)) < .05      # rotated before the expiry
    assert "missed_event" in policies.run_policy("noop", sc)["tags"]


# ---- F9: three steps; restart / scaling do not escape -----------------------------------------------------------
def test_f9_restart_and_scaling_do_not_escape_but_warming_does():
    sc = sc_of("F9")
    cache, db = sc.cache, sc.db
    apps = [n for n in sc.order if sc.nodes[n].kind == "app"]
    env = run(sc, ("restart", {"service": cache}), ("restart", {"service": db}))
    b = env.finalize()
    assert b["fixed"][0] is False and env.w.nodes[cache].hit < .2 and b["score"] < .3
    env = run(sc, *[("scale", {"service": n, "replicas": 8}) for n in apps[:3]])
    assert env.finalize()["fixed"][0] is False and env.w.nodes[cache].hit < .2
    warm = ("run_maintenance", {"service": cache, "action": "warm_cache"})
    env = run(sc, warm, warm, warm)
    b = env.finalize()
    assert b["fixed"][0] is True and env.w.nodes[cache].hit > .8 and "wrong_order" not in b["tags"]
    env = run(sc, ("scale", {"service": db, "replicas": 4}), warm, warm, warm)
    assert "wrong_order" in env.finalize()["tags"]


def test_f9_throttle_must_be_removed_and_costs_traffic():
    sc = sc_of("F9")
    limit = int(sc.params["base_rps"] * .15)
    entry = sc.entry
    env = run(sc, ("set_config", {"service": entry, "key": "rate_limit_rps", "value": limit}), wait=25)
    assert env.w.nodes[sc.cache].hit > .8                          # the db relaxed, the cache refilled
    kept = Env(sc)
    kept.call("set_config", service=entry, key="rate_limit_rps", value=limit)
    kb = kept.finalize()
    assert kb["fixed"][0] is False and kb["tags"].count("symptom_fix") == 0 and kb["U"] < .8      # shed traffic is lost traffic
    env.call("set_config", service=entry, key="rate_limit_rps", value=0)
    b = env.finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and "symptom_fix" not in b["tags"]
    assert b["U"] > kb["U"]


# ---- F10: poison message -------------------------------------------------------------------------------------------
def test_f10_rollback_scale_restart_do_not_help_dlq_does():
    sc = sc_of("F10")
    wk = sc.worker
    probe = Env(sc)
    probe.call("wait", minutes=25)
    prod = next(e.caller for e in sc.edges if e.callee == sc.queue)
    assert max(r[prod]["err"] for r in probe.w.rec[-5:]) > .3 and probe.w.rec[-1][sc.queue]["lag"] > 3     # backpressure hits the producer
    env = Env(sc)
    env.call("scale", service=wk, replicas=12)
    env.call("restart", service=wk)
    env.call("rollback", service=wk, version=prev_version(env, wk))
    b = env.finalize()
    assert b["fixed"][0] is False and env.w.rec[-1][sc.queue]["lag"] > 3 and env.w.rec[-1][wk]["err"] > .5
    env = run(sc, ("set_config", {"service": wk, "key": "dlq_enabled", "value": True}))
    b = env.finalize()
    assert b["fixed"][0] is True and env.w.rec[-1][sc.queue]["lag"] < .5 and b["R_avail"] > .5


# ---- F11: canary ----------------------------------------------------------------------------------------------------
def test_f11_canary_is_quiet_on_average_but_loud_in_p99_and_entry_sees_it():
    sc = sc_of("F11")
    node, flag = sc.faults[0]["node"], sc.faults[0]["flag"]
    env = Env(sc)
    env.call("wait", minutes=15)
    r = env.w.rec[-1]
    assert .01 < r[node]["err"] < .1 and r[node]["p99"] > 8 * r[node]["p50"]
    healthy = Scenario(sc.seed, sc.difficulty, sc.salt)
    healthy.faults, healthy.herring = [], None
    h = Env(healthy)
    h.call("wait", minutes=15)
    assert r[sc.entry]["p99"] > 2 * h.w.rec[-1][sc.entry]["p99"]      # the tail reaches the entry
    assert "canary_missed" in env.finalize()["tags"] and "canary_missed" in policies.run_policy("noop", sc)["tags"]
    env = run(sc, ("set_flag", {"flag": flag, "on": False}), wait=2)
    assert env.call("get_deploys", service=node)["result"]["deploys"][node]["canary"]["weight"] == 0
    b = env.finalize()
    assert b["fixed"] == [True] and "canary_missed" not in b["tags"] and "symptom_fix" not in b["tags"]


# ---- F12: thread starvation ------------------------------------------------------------------------------------------
def test_f12_starved_caller_is_the_symptom():
    sc = sc_of("F12")
    dep, caller = sc.faults[0]["node"], sc.faults[0]["caller"]
    env = Env(sc)
    env.call("wait", minutes=15)
    r = env.w.rec[-1]
    assert r[dep]["err"] < .02 and r[dep]["p99"] > 1500 and r[caller]["wu"] > 1 and r[caller]["err"] > .2
    b = run(sc, ("restart", {"service": caller})).finalize()
    assert b["fixed"] == [False] and "symptom_fix" in b["tags"] and b["P_collateral"] >= .1
    b = run(sc, ("set_circuit_breaker", {"service": caller, "dep": dep, "mode": "fallback"})).finalize()
    assert b["fixed"] == [True] and "symptom_fix" not in b["tags"] and b["score"] > .89


# ---- F13: misleading message ------------------------------------------------------------------------------------------
def test_f13_following_the_message_is_collateral_and_authority_bias():
    sc = sc_of("R11")
    named = sc.misleading["node"]
    env = Env(sc)
    env.call("wait", minutes=sc.misleading["t"] + 2)
    msgs = [e for e in env.call("get_events")["result"]["events"] if e["type"] == "message" and named in e["text"]]
    assert msgs and "rolling back" in msgs[0]["text"]
    assert env.w.rec[-1][named]["err"] < .05                       # the metrics do not support it
    env.call("rollback", service=named, version=prev_version(env, named))
    b = env.finalize()
    assert "authority_bias" in b["tags"] and "herring_followed" in b["tags"] and b["P_collateral"] >= .1
    assert "authority_bias" not in policies.run_policy("reference", sc)["tags"]


# ---- F14: unmasked cascade ---------------------------------------------------------------------------------------------
def test_f14_resolving_right_after_fixing_a_is_penalised():
    sc = sc_of("F14", lambda s: all(f["role"] != "bomb" for f in s.faults))
    env = Env(sc)
    fa, fb = env.w.faults[0], env.w.faults[1]
    truth = [{"service": f.node, "fault_class": f.fault_class} for f in env.w.faults]
    (_, tool, args), = fa.fix_plan()
    env.call(tool, **args)
    env.call("resolve_incident", root_causes=truth, summary="done")
    b = env.finalize()
    assert "unmasked_cascade_missed" in b["tags"] and b["fixed"][:2] == [True, False]
    assert max(end_err(env, fb.node, 20)) > .2                       # B collapsed after the resolve
    assert b["score"] < .75
    env = Env(sc)
    env.call(tool, **args)
    env.call("wait", minutes=6)
    assert env.w.rec[-1][fb.node]["err"] > .2 and env.w.rec[-1][fb.node]["util"] > 1
    (_, tool2, args2), = fb.fix_plan()
    env.call(tool2, **args2)
    env.call("resolve_incident", root_causes=truth)
    full = env.finalize()
    assert full["fixed"][:2] == [True, True] and "unmasked_cascade_missed" not in full["tags"] and full["score"] > b["score"] + .2


# ---- unnecessary changes cost 0.05, targeted fixes and observations are free ----------------------------------------
def test_unnecessary_non_destructive_changes_are_penalised():
    sc = sc_of("R2")
    fnode = sc.faults[0]["node"]
    other = next(n for n in sc.order if sc.nodes[n].kind == "app" and n not in {f["node"] for f in sc.faults}
                 and n != sc.herring["node"] and not sc.nodes[n].entry and sc.nodes[n].role != "worker")
    on_flag = next((f["name"] for f in sc.flags if f["on"]), None) or sc.flags[0]["name"]
    env = Env(sc)
    env.call("get_status")
    env.call("wait", minutes=2)
    env.call("set_config", service=other, key="log_level", value="WARN")
    env.call("set_flag", flag=on_flag, on=False)
    env.call("scale", service=other, replicas=3)
    env.call("run_maintenance", service=other, action="prune_logs")
    env.call("set_config", service=fnode, key="log_level", value="WARN")         # targets the fault node: free
    assert env.finalize()["P_collateral"] == pytest.approx(.20)
    env = run(sc, ("restart", {"service": other}), ("set_config", {"service": other, "key": "log_level", "value": "WARN"}))
    assert env.finalize()["P_collateral"] == pytest.approx(.15)
    assert policies.run_policy("reference", sc)["P_collateral"] == 0
