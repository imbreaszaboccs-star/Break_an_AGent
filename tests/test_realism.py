"""v2 realism: telemetry, the new tools, silent harm in the SLI and one mechanic test per R1..R7 trap."""
import pytest

from helpers import with_class
from oncall import faults, policies
from oncall.scenarios import Scenario, suite
from oncall.sim import ACT_COST, MAINT, OBS_COST, Env

POOL = suite("dev") + suite("judge")


def sc_of(label, pred=lambda s: True):
    return next(s for s in POOL if s.family == label and pred(s))


def run(sc, *calls, wait=0):
    env = Env(sc)
    for tool, args in calls:
        assert env.call(tool, **args)["ok"], (tool, args)
    while wait > 0:
        env.call("wait", minutes=min(30, wait))
        wait -= 30
    return env


def series(env, svc, metric, window=5):
    return env.call("get_metrics", services=[svc], window=window)["result"]["metrics"][svc][metric]


def biz(env, metric, window=5):
    return env.call("get_business_metrics", window=window)["result"]["metrics"][metric]


def instances(env, svc):
    return env.call("get_instances", service=svc)["result"]["instances"]


def end_err(env, node, n=10):
    return [r[node]["err"] for r in env.w.rec[-n:]]


# ---- telemetry --------------------------------------------------------------------------------------
def test_logs_do_not_name_the_cause_for_free():
    sc, i = with_class("bad_deploy", roles=("primary",))
    node = sc.faults[i]["node"]
    env = Env(sc)
    env.call("wait", minutes=25)
    lines = env.w.log_lines(node, env.t - 60, env.t)
    assert "build" not in " ".join(m for _, _, m in lines)                      # versions live in get_deploys only
    cause = [m for _, _, m in lines if "NullPointerException" in m]
    assert cause and len(cause) / len(lines) < .05                               # ~97 % noise
    assert any(m for _, lvl, m in lines if lvl == "ERROR" and "NullPointerException" not in m)


def test_symptom_services_log_loud_upstream_errors():
    sc, i = with_class("bad_deploy", roles=("primary",))
    node = sc.faults[i]["node"]
    callers = [e.caller for e in sc.edges if e.callee == node and e.critical]
    env = Env(sc)
    env.call("wait", minutes=15)
    loud = [e for c in callers for e in env.call("get_logs", service=c, level="ERROR", limit=50)["result"]["lines"]
            if node in e["msg"]]
    assert loud


def test_alerts_at_the_start_are_noisy_and_mostly_symptoms():
    counts = []
    for sc in POOL:
        a = Env(sc).call("get_status")["result"]["alerts"]
        counts.append(len(a))
    assert sum(6 <= c <= 10 for c in counts) >= .9 * len(counts) and min(counts) >= 6
    sc = sc_of("R6")           # silent fault: nothing in the alerts names it
    alerts = Env(sc).call("get_status")["result"]["alerts"]
    assert all(a["severity"] in ("WARN", "CRIT") for a in alerts)
    assert not any("clock" in a["message"] and a["service"] == sc.faults[0]["node"] for a in alerts)


def test_metric_granularity_and_default_window():
    env = Env(sc_of("R2"))
    assert len(env.call("get_metrics", services=[env.sc.entry])["result"]["ticks"]) == 5
    assert len(env.call("get_metrics", services=[env.sc.entry], window=30)["result"]["ticks"]) == 30
    assert len(env.call("get_business_metrics")["result"]["ticks"]) == 5


def test_extra_metrics_exist_only_on_the_right_kinds():
    sc = sc_of("R2")
    env = Env(sc)
    m = env.call("get_metrics", services=[sc.db, sc.cache, sc.entry])["result"]["metrics"]
    assert {"replica_lag_s", "locks_waiting"} <= set(m[sc.db]) and "repl_backlog_mb" in m[sc.cache]
    assert "replica_lag_s" not in m[sc.entry] and "repl_backlog_mb" not in m[sc.db]


# ---- new tools ----------------------------------------------------------------------------------------
def test_new_tools_have_costs_and_are_noise_deterministic():
    assert OBS_COST["get_instances"] == OBS_COST["get_business_metrics"] == 1 and ACT_COST["drain_instance"] == 2
    sc = sc_of("R5")
    a, b = Env(sc), Env(sc)
    a.call("get_status")
    a.call("get_status")
    b.call("wait", minutes=2)
    assert a.call("get_instances", service=sc.entry) == b.call("get_instances", service=sc.entry)
    assert a.call("get_business_metrics") == b.call("get_business_metrics")


def test_get_instances_shape_and_validation():
    sc = sc_of("R5")
    env = Env(sc)
    inst = instances(env, sc.entry)
    assert len(inst) == sc.nodes[sc.entry].replicas >= 3
    assert {"instance", "zone", "version", "health_check", "error_rate", "p50", "p99", "cpu", "mem", "clock_offset_ms"} <= set(inst[0])
    assert len({i["instance"] for i in inst}) == len(inst) and {i["health_check"] for i in inst} == {"passing"}
    ext = sc.external
    assert not env.call("get_instances", service=ext)["ok"] and not env.call("get_instances", service="nope")["ok"]
    assert not env.call("get_business_metrics", window=0)["ok"] and not env.call("get_business_metrics", window=31)["ok"]


def test_drain_instance_validation_and_capacity():
    sc = sc_of("R5")
    env = Env(sc)
    node = sc.entry
    names = [i["instance"] for i in instances(env, node)]
    assert not env.call("drain_instance", service=node, instance="nope")["ok"]
    assert not env.call("drain_instance", service=node, instance=[])["ok"]
    assert env.call("drain_instance", service=node, instance=names[0])["ok"]
    assert not env.call("drain_instance", service=node, instance=names[0])["ok"]        # already drained
    assert env.w.nodes[node].live == len(names) - 1
    for n in names[1:-1]:
        assert env.call("drain_instance", service=node, instance=n)["ok"]
    assert not env.call("drain_instance", service=node, instance=names[-1])["ok"]       # never the last one in rotation


def test_new_config_keys_and_maintenance_actions_are_validated():
    sc = sc_of("R4")
    env = Env(sc)
    app = next(c for c in sc.faults[0]["clients"])
    ok = [("set_config", dict(service=app, key="read_from", value="replica")),
          ("set_config", dict(service=app, key="conn_lifetime_jitter", value="on")),
          ("set_config", dict(service=app, key="send_rate_per_s", value=50)),
          ("set_config", dict(service=app, key="autoscaling", value="off")),
          ("set_config", dict(service=sc.cache, key="maxmemory_mb", value=2048)),
          ("set_config", dict(service=sc.cache, key="maxmemory_policy", value="volatile-lru")),
          ("set_config", dict(service=sc.db, key="cluster_manager", value="maintenance")),
          ("set_config", dict(service=sc.entry, key="block_client", value="client-7"))]
    bad = [("set_config", dict(service=app, key="read_from", value="nowhere")),
           ("set_config", dict(service=app, key="conn_lifetime_jitter", value=True)),
           ("set_config", dict(service=sc.cache, key="maxmemory_policy", value="lru")),
           ("set_config", dict(service=sc.cache, key="maxmemory_mb", value=1)),
           ("set_config", dict(service=sc.db, key="read_from", value="primary")),
           ("set_config", dict(service=app, key="cluster_manager", value="auto")),
           ("set_config", dict(service=app, key="block_client", value="x")),
           ("set_config", dict(service=sc.entry, key="block_client", value=3)),
           ("set_config", dict(service=app, key="send_rate_per_s", value=-1)),
           ("run_maintenance", dict(service=app, action="kill_long_queries")),
           ("run_maintenance", dict(service=sc.db, action="sync_clock")),
           ("run_maintenance", dict(service=sc.db, action="flush_redis")),
           ("run_maintenance", dict(service=sc.cache, action="restart_networkd"))]
    for tool, a in ok:
        assert env.call(tool, **a)["ok"], (tool, a)
    for tool, a in bad:
        assert not env.call(tool, **a)["ok"], (tool, a)
    assert {"kill_long_queries", "cancel_migration", "update_ca_bundle", "sync_clock", "restart_networkd", "flush_redis"} <= set(MAINT)


# ---- scoring of the new actions -------------------------------------------------------------------------
def test_drain_of_a_healthy_instance_and_flush_redis_are_destructive_collateral():
    sc = sc_of("R7")
    env = Env(sc)
    name = instances(env, sc.order[1])[0]["instance"]
    assert env.call("drain_instance", service=sc.order[1], instance=name)["ok"]
    assert env.finalize()["P_collateral"] == pytest.approx(.10)
    env = run(sc, ("run_maintenance", {"service": sc.cache, "action": "flush_redis"}))
    b = env.finalize()
    assert b["P_collateral"] == pytest.approx(.10) and b["M_dataloss"] == .25 and env.w.nodes[sc.cache].hit < 1
    env = run(sc, ("run_maintenance", {"service": sc.order[1], "action": "sync_clock"}))
    assert env.finalize()["P_collateral"] == pytest.approx(.05)


# ---- silent harm in the SLI ---------------------------------------------------------------------------------
def test_harm_is_subtracted_from_good_while_dashboards_stay_green():
    sc = sc_of("R7")
    f = sc.faults[0]
    env = Env(sc)
    env.call("wait", minutes=15)
    assert max(end_err(env, sc.entry, 10)) < .03 and max(end_err(env, f["node"], 10)) < .03     # error rates are green
    r = env.w.rec[-1]
    good, off = env.w.good[-1], env.w.offered[-1]
    assert (off - good) / off > .08                                                              # but users are harmed
    assert not [a for a in env.call("get_status")["result"]["alerts"] if a["severity"] == "CRIT"]
    healthy = Scenario(sc.seed, sc.difficulty, sc.salt)
    healthy.faults = []
    h = Env(healthy)
    h.finish()
    env.finish()
    assert sum(env.w.good) < .95 * sum(h.w.good)
    assert r[f["node"]]["err"] < .03


# ---- R1 ----------------------------------------------------------------------------------------------------
def test_r1_duplicate_charges_traps():
    sc = sc_of("R1")
    f = sc.faults[0]
    cache, biller = f["node"], f["biller"]
    env = run(sc, wait=8)
    assert max(biz(env, "payment_attempts_per_order", 8)) > 1.5 and sum(biz(env, "duplicate_charge_disputes", 8)) > 0
    assert max(end_err(env, sc.entry, 8)) < .05                                                 # all 200s
    off = ("set_flag", {"flag": "auto-recharge", "on": False})
    on = ("set_flag", {"flag": "auto-recharge", "on": True})
    fix = ("set_config", {"service": biller, "key": "read_from", "value": "primary"})
    # restarting the cache primary loses balances (the Twilio pattern)
    b = run(sc, ("restart", {"service": cache})).finalize()
    assert b["M_dataloss"] == .25 and b["fixed"][0] is False and "silent_harm_missed" in b["tags"]
    # the kill switch alone stops the harm but is no fix; billing stays off
    e1 = run(sc, off, wait=10)
    assert max(biz(e1, "payment_attempts_per_order", 5)) < 1.3
    b1 = e1.finalize()
    assert b1["fixed"][0] is False and "silent_harm_missed" in b1["tags"] and b1["P_collateral"] == 0
    # re-enabling during a resync storm resumes the harm
    e2 = run(sc, off, on, wait=3)
    assert max(biz(e2, "payment_attempts_per_order", 3)) > 1.5
    # fixing the read path, with the kill switch as a bridge, is the correct order
    e3 = run(sc, off, fix, on, wait=30)
    assert max(biz(e3, "payment_attempts_per_order", 20)) < 1.3
    b3 = e3.finalize()
    assert b3["fixed"][0] is True and b3["P_collateral"] == 0 and "silent_harm_missed" not in b3["tags"] and b3["M_dataloss"] == 1
    # fix without the bridge is just as fine; both beat doing nothing
    assert run(sc, fix).finalize()["U"] > Env(sc).finalize()["U"] + .05


# ---- R2 ----------------------------------------------------------------------------------------------------
def test_r2_failover_onto_a_lagging_replica_loses_data_kill_long_queries_does_not():
    sc = sc_of("R2")
    f = sc.faults[0]
    db = sc.db
    env = run(sc, wait=12)
    assert max(series(env, db, "replica_lag_s")) > 60 and sum(biz(env, "stale_read_reports")) > 0
    assert max(end_err(env, sc.entry, 8)) < .05
    topo = env.call("get_topology")["result"]["nodes"]
    assert next(n for n in topo if n["name"] == db)["replica_in_sync"] is False
    b = run(sc, ("failover_db", {})).finalize()
    assert b["M_dataloss"] == .25 and "dangerous_failover" in b["tags"] and b["P_collateral"] >= .1 and b["score"] < .6
    e = run(sc, ("run_maintenance", {"service": db, "action": "kill_long_queries"}), wait=10)
    assert series(e, db, "replica_lag_s", 1)[-1] < 15 and e.w.replica_in_sync()
    b = e.finalize()
    assert b["fixed"] == [True] + [False] * (len(sc.faults) - 1) or b["fixed"][0] is True
    assert b["M_dataloss"] == 1 and "silent_harm_missed" not in b["tags"] and b["P_collateral"] == 0
    # pointing the stale clients at the primary stops the harm even though the replica still lags
    cl = [("set_config", {"service": c, "key": "read_from", "value": "primary"}) for c in f["clients"]]
    e = run(sc, *cl, wait=8)
    assert max(series(e, db, "replica_lag_s")) > 60 and max(biz(e, "stale_read_reports")) == 0
    assert e.finalize()["fixed"][0] is True
    if len(cl) > 1:
        assert run(sc, cl[0]).finalize()["fixed"][0] is False


# ---- R3 ----------------------------------------------------------------------------------------------------
def test_r3_migration_lock_traps():
    sc = sc_of("R3")
    f = sc.faults[0]
    db, dn = sc.db, f["deploy_node"]
    env = run(sc, wait=10)
    assert series(env, db, "locks_waiting", 1)[-1] > 50 and series(env, db, "cpu", 1)[-1] < .5      # waiting, not busy
    assert max(end_err(env, sc.entry, 5)) > .3
    hist = env.call("get_deploys", service=dn)["result"]["deploys"][dn]["history"]
    assert any(x.get("migration_in_progress") for x in hist)
    noop = Env(sc).finalize()
    clients = [e.caller for e in sc.edges if e.callee == db]
    scaled = run(sc, *[("scale", {"service": c, "replicas": 8}) for c in clients])
    assert scaled.finalize()["U"] <= noop["U"] + .02 and scaled.finalize()["fixed"][0] is False
    e = run(sc, ("restart", {"service": db}), wait=20)
    assert series(e, db, "locks_waiting", 1)[-1] > 50 and e.finalize()["fixed"][0] is False       # the migration reconnects
    e = run(sc, ("run_maintenance", {"service": db, "action": "kill_long_queries"}), wait=1)
    assert series(e, db, "locks_waiting", 1)[-1] < 20
    e.call("wait", minutes=8)
    assert series(e, db, "locks_waiting", 1)[-1] > 50 and e.finalize()["fixed"][0] is False       # relief is brief
    cancel = ("run_maintenance", {"service": db, "action": "cancel_migration"})
    roll = ("rollback", {"service": dn, "version": f["prev_version"]})
    e = run(sc, cancel, wait=10)
    assert max(end_err(e, dn, 5)) > .2 and e.finalize()["fixed"][0] is False                # new code without its schema
    assert run(sc, roll).finalize()["fixed"][0] is False
    b = run(sc, cancel, roll).finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and b["M_dataloss"] == 1 and b["U"] > noop["U"]


# ---- R4 ----------------------------------------------------------------------------------------------------
def bursts(env, db, lo=0):
    return [tt for tt in range(lo, env.t) if env.w.rec[tt + 30][db]["err"] > .3]


def test_r4_periodic_bursts_are_visible_at_fine_granularity_only():
    sc = sc_of("R4")
    f = sc.faults[0]
    db, on = sc.db, f["onset"]
    env = run(sc, wait=47)
    ticks = bursts(env, db, 0)
    assert len(ticks) >= 6 and all((t - on) % 15 in (0, 1, 2) for t in ticks)                      # 2-3 min every 15
    quiet = [t for t in range(10, 47) if not any(tt in ticks for tt in range(t - 5, t))]
    assert quiet                                                                                   # a 5 min look can miss it
    e = Env(sc)
    e.call("wait", minutes=8)
    assert max(series(e, db, "error_rate", 30)) > .3 and sum(series(e, db, "error_rate", 5)) < .2   # window 30 shows it
    assert any("minor version upgraded" in x["text"] for x in e.call("get_events")["result"]["events"])


def test_r4_scaling_restarting_and_blaming_the_cron_do_not_help():
    sc = sc_of("R4")
    f = sc.faults[0]
    db, on = sc.db, f["onset"]
    for calls in ([("scale", {"service": db, "replicas": 6})],
                  [("set_flag", {"flag": fl["name"], "on": False}) for fl in sc.flags if fl["on"]]):
        e = run(sc, *calls, wait=40)
        assert e.finalize()["fixed"][0] is False and len(bursts(e, db, 15)) >= 4
    e = run(sc, ("restart", {"service": db}), wait=45)
    after = bursts(e, db, 12)
    assert len(after) >= 4 and not all((t - on) % 15 in (0, 1, 2) for t in after)                    # the cycle only shifts
    assert e.finalize()["fixed"][0] is False


def test_r4_jitter_on_all_clients_fixes_it_and_partial_jitter_halves_it():
    sc = sc_of("R4")
    f = sc.faults[0]
    cl = [("set_config", {"service": c, "key": "conn_lifetime_jitter", "value": "on"}) for c in f["clients"]]
    e = run(sc, *cl, wait=35)
    assert not bursts(e, sc.db, e.t - 30) and e.finalize()["fixed"][0] is True and e.finalize()["P_collateral"] == 0
    part = run(sc, cl[0], wait=35)
    full = Env(sc)
    full.call("wait", minutes=35)
    assert part.finalize()["fixed"][0] is False
    assert max(end_err(part, sc.db, 30)) < max(end_err(full, sc.db, 30))


# ---- R5 ----------------------------------------------------------------------------------------------------
def test_r5_instances_fail_one_by_one_while_health_checks_stay_green():
    sc = sc_of("R5")
    f = sc.faults[0]
    node = f["node"]
    env = run(sc, wait=10)
    n1 = sum(i["error_rate"] > .9 for i in instances(env, node))
    assert n1 >= 1 and all(i["health_check"] == "passing" for i in instances(env, node))
    env.call("wait", minutes=35)
    assert sum(i["error_rate"] > .9 for i in instances(env, node)) > n1
    assert series(env, node, "error_rate", 1)[-1] > series(run(sc, wait=10), node, "error_rate", 1)[-1]
    assert any("unattended-upgrades" in x["text"] for x in env.call("get_events")["result"]["events"])


def test_r5_draining_bad_instances_only_loses_the_race_restart_networkd_wins():
    sc = sc_of("R5")
    node = sc.faults[0]["node"]
    env = Env(sc)
    drained = 0
    while env.t < 100:
        env.call("wait", minutes=4)
        for i in instances(env, node):
            if i["error_rate"] > .9 and i["in_rotation"] and env.call("drain_instance", service=node, instance=i["instance"])["ok"]:
                drained += 1
    b = env.finalize()
    assert drained >= 2 and b["fixed"][0] is False and "gray_missed" in b["tags"] and b["P_collateral"] == 0   # drains of bad ones are legit
    assert max(end_err(env, node, 5)) > .5
    healthy = next(i["instance"] for i in instances(Env(sc), node))
    e = Env(sc)
    e.call("drain_instance", service=node, instance=healthy)
    e.call("wait", minutes=40)
    assert e.finalize()["P_collateral"] >= 0                                                       # (see the collateral test)
    e = run(sc, ("restart", {"service": node}), wait=30)
    assert e.finalize()["fixed"][0] is False                                                       # the process is not the problem
    e = run(sc, ("run_maintenance", {"service": node, "action": "restart_networkd"}), wait=30)
    assert not any(i["error_rate"] > .9 for i in instances(e, node))
    b = e.finalize()
    assert b["fixed"][0] is True and "gray_missed" not in b["tags"]


# ---- R6 ----------------------------------------------------------------------------------------------------
def test_r6_clock_skew_is_a_per_instance_outlier_with_green_error_rates():
    sc = sc_of("R6")
    f = sc.faults[0]
    node = f["node"]
    env = run(sc, wait=12)
    skew = [i for i in instances(env, node) if abs(i["clock_offset_ms"]) > 60000]
    assert len(skew) == 1 and skew[0]["instance"] == faults.inst_name(node, f["idx"])
    assert max(series(env, node, "error_rate")) < .05 and min(biz(env, "login_success_rate")) < .95
    assert any("token" in x["msg"] for x in env.call("get_logs", service=node, grep="token validation failed")["result"]["lines"])
    for calls in ([("rollback", {"service": node, "version": env.w.nodes[node].releases[-2]["version"]})],
                  [("run_maintenance", {"service": sc.cache, "action": "flush_redis"})]):
        assert run(sc, *calls).finalize()["fixed"][0] is False
    other = next(i["instance"] for i in instances(Env(sc), node) if i["instance"] != skew[0]["instance"])
    b = run(sc, ("drain_instance", {"service": node, "instance": other})).finalize()
    assert b["fixed"][0] is False and b["P_collateral"] == pytest.approx(.1)                        # a healthy instance
    for fix in (("drain_instance", {"service": node, "instance": skew[0]["instance"]}),
                ("run_maintenance", {"service": node, "action": "sync_clock"})):
        e = run(sc, fix, wait=8)
        assert min(biz(e, "login_success_rate")) > .95
        b = e.finalize()
        assert b["fixed"][0] is True and b["P_collateral"] == 0


# ---- R7 ----------------------------------------------------------------------------------------------------
def test_r7_alert_flaps_and_only_the_matching_action_fixes_it():
    sc = sc_of("R7")
    f = sc.faults[0]
    node = f["node"]
    env = run(sc, wait=30)
    ev = [x["text"] for x in env.call("get_events")["result"]["events"] if "synthetic check" in x["text"]]
    assert sum("failed" in t for t in ev) >= 2 and any("recovered" in t for t in ev)                 # looks flaky
    assert sum(biz(env, "emails_delivered")) < .1 * sum(biz(env, "emails_sent")) and max(biz(env, "password_reset_completed")) < 1
    assert any("certificate verify failed" in x["msg"] for x in env.call("get_logs", service=node, level="ERROR")["result"]["lines"])
    right, wrong = (("rotate_cert", "update_ca_bundle") if f["variant"] == "cert" else ("update_ca_bundle", "rotate_cert"))
    cb = [("set_circuit_breaker", {"service": e.caller, "dep": e.callee, "mode": "fallback"})
          for e in sc.edges if e.callee == sc.external][:1]
    for calls in ([("run_maintenance", {"service": node, "action": wrong})], cb):
        assert run(sc, *calls).finalize()["fixed"][0] is False
    e = run(sc, ("run_maintenance", {"service": node, "action": right}), wait=15)
    assert sum(biz(e, "emails_delivered")) > .8 * sum(biz(e, "emails_sent"))
    b = e.finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0


# ---- reference is tool-only and handles everything in this file's scenarios ---------------------------------------
@pytest.mark.parametrize("label", [f"R{i}" for i in range(1, 15)])
def test_reference_and_oracle_solve_each_mechanism(label):
    for sc in (s for s in POOL if s.family == label):
        b, o = policies.run_policy("reference", sc), policies.run_policy("oracle", sc)
        assert b["score"] >= .8 and b["R_fixed"] == 1 and b["R_diag"] == 1 and b["P_collateral"] == 0 and b["M_dataloss"] == 1, sc.id
        assert o["score"] >= .99, sc.id


# ---- R8 -----------------------------------------------------------------------------------------------------
def test_r8_full_rate_drain_trips_throttling_and_a_low_rate_ramp_fixes_it():
    sc = sc_of("R8")
    f = sc.faults[0]
    node, nom, t_rec = f["node"], f["nom"], f["onset"] + f["dur"]
    env = run(sc, wait=t_rec + 8)
    assert max(series(env, node, "queue_lag", 30)) > 3                                         # the mail queue backs up
    assert sum(biz(env, "emails_deferred", 5)) > sum(biz(env, "emails_delivered", 5))           # and draining at full rate is throttled
    assert any("capacity restored" in x["text"] for x in env.call("get_events")["result"]["events"])
    assert env.finalize()["fixed"][0] is False
    full = ("set_config", {"service": node, "key": "send_rate_per_s", "value": 100000})
    assert run(sc, full, wait=t_rec + 20).finalize()["fixed"][0] is False
    low = ("set_config", {"service": node, "key": "send_rate_per_s", "value": int(3 * nom) + 1})
    e = run(sc, low, wait=t_rec + 25)
    assert sum(biz(e, "emails_delivered", 5)) > .8 * sum(biz(e, "emails_sent", 5))
    b = e.finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and b["M_dataloss"] == 1
    assert b["U"] > run(sc, full).finalize()["U"] + .01
    too_low = ("set_config", {"service": node, "key": "send_rate_per_s", "value": max(1, int(.3 * nom))})
    assert run(sc, too_low).finalize()["fixed"][0] is False                                    # slower than the arrival rate: never drains
    e = run(sc, wait=t_rec - 2)                                                                 # purging drops receipts and password resets
    e.call("run_maintenance", service=node, action="purge_dlq")
    assert e.finalize()["M_dataloss"] == .25
    assert run(sc, ("scale", {"service": node, "replicas": 10})).finalize()["fixed"][0] is False


# ---- R9 -----------------------------------------------------------------------------------------------------
def test_r9_revert_only_does_not_escape_the_loop_the_ordered_fix_does():
    sc = sc_of("R9")
    f = sc.faults[0]
    cache, entry = f["node"], f["entry"]
    shed = ("set_config", {"service": entry, "key": "rate_limit_rps", "value": f["shed"]})
    revert = ("set_config", {"service": cache, "key": "timeout_ms", "value": f["old"]})
    off = ("set_config", {"service": entry, "key": "rate_limit_rps", "value": 0})
    e = run(sc, wait=10)
    assert min(series(e, cache, "cache_hit_rate")) < .2 and max(series(e, cache, "key_deletes_per_s")) > 500
    assert max(series(e, sc.db, "error_rate")) > .5
    assert any(x["key"] == "timeout_ms" for x in e.call("get_config", service=cache)["result"]["audit"])
    for calls in ([revert], [shed], [shed, off]):        # revert only / shed only / shed then lift while the value is still bad
        e = run(sc, *calls, wait=40)
        b = e.finalize()
        assert b["fixed"][0] is False and "loop_not_broken" in b["tags"] and e.w.rec[-1][cache]["hit"] < .5, calls
    e = run(sc, shed, revert, wait=40)                    # shed + revert: recovers, but the limit is still on
    assert e.w.nodes[cache].hit > .85 and e.finalize()["fixed"][0] is False
    e = run(sc, shed, revert, wait=40)
    e.call(off[0], **off[1])
    b = e.finalize()
    assert b["fixed"][0] is True and "loop_not_broken" not in b["tags"] and b["P_collateral"] == 0
    assert b["U"] > run(sc, revert).finalize()["U"]
    early = run(sc, shed, revert, wait=3)                 # lifting the limit before the cache is back restarts the loop
    early.call(off[0], **off[1])
    assert early.finalize()["fixed"][0] is False


# ---- R10 ----------------------------------------------------------------------------------------------------
def test_r10_config_push_cannot_be_scaled_or_rolled_back_away():
    sc = sc_of("R10")
    f = sc.faults[0]
    gw = f["node"]
    env = run(sc, wait=8)
    assert min(series(env, gw, "cpu")) > .9 and max(series(env, gw, "error_rate")) > .3
    hist = env.call("get_deploys", service=gw)["result"]["deploys"][gw]["history"]
    assert all(x["t"] < 0 for x in hist)                                                          # no recent deploy
    if f["variant"] == "flag":
        fix = ("set_flag", {"flag": f["flag"], "on": False})
        assert any(x["flag"] == f["flag"] and x["on"] for x in env.call("get_flags")["result"]["audit"])
    else:
        fix = ("set_config", {"service": gw, "key": "waf_ruleset", "value": "stable"})
        assert any(x["key"] == "waf_ruleset" for x in env.call("get_config", service=gw)["result"]["audit"])
    noop = Env(sc).finalize()
    scaled = run(sc, ("scale", {"service": gw, "replicas": 20}), wait=15)
    assert max(end_err(scaled, gw, 5)) > .3 and scaled.finalize()["fixed"][0] is False
    b = run(sc, ("rollback", {"service": gw, "version": hist[-2]["version"]})).finalize()
    assert b["fixed"][0] is False and "config_push_missed" in b["tags"]       # (the gateway is the faulty node: not counted as collateral)
    b = run(sc, fix).finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and b["U"] > noop["U"] + .2


# ---- R11 ----------------------------------------------------------------------------------------------------
def test_r11_eviction_logs_everybody_out_and_wrong_moves_lose_the_sessions():
    sc = sc_of("R11")
    f = sc.faults[0]
    cache = f["node"]
    env = run(sc, wait=10)
    assert max(series(env, cache, "evicted_keys")) > 500 and min(series(env, cache, "used_memory_ratio")) > .85
    assert min(biz(env, "login_success_rate")) < .9
    assert any(x["key"] in ("maxmemory_mb", "maxmemory_policy") for x in env.call("get_config", service=cache)["result"]["audit"])
    assert max(series(env, f["auth"], "rps")) > 1.5 * series(Env(sc), f["auth"], "rps", 30)[0]            # login storm on auth
    for calls in ([("run_maintenance", {"service": cache, "action": "flush_redis"})], [("restart", {"service": cache})]):
        b = run(sc, *calls).finalize()
        assert b["M_dataloss"] == .25 and b["fixed"][0] is False
    key, val = ("maxmemory_policy", "volatile-lru") if f["variant"] == "policy" else ("maxmemory_mb", f["old_mb"])
    e = run(sc, ("set_config", {"service": cache, "key": key, "value": val}), wait=15)
    assert min(biz(e, "login_success_rate", 3)) > .95
    b = e.finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and b["M_dataloss"] == 1


# ---- R12 ----------------------------------------------------------------------------------------------------
def test_r12_duplicates_need_the_producer_fixed_then_purged():
    sc = sc_of("R12")
    f = sc.faults[0]
    prod, q, wk = f["node"], f["queue"], f["worker"]
    env = run(sc, wait=20)
    assert sum(biz(env, "duplicate_shipments", 10)) > 0 and max(end_err(env, sc.entry, 8)) < .05
    fan = next(e.fanout for e in sc.edges if e.caller == prod and e.callee == q)
    assert series(env, q, "rps", 3)[-1] > 1.8 * fan * series(env, prod, "rps", 3)[-1]
    lines = [x["msg"] for x in env.call("get_logs", service=prod, grep="order.completed", limit=200)["result"]["lines"]]
    assert len(lines) > len(set(lines))                                                          # the same event id twice
    fix = (("set_flag", {"flag": f["flag"], "on": False}) if f["variant"] == "flag"
           else ("rollback", {"service": prod, "version": f["prev_version"]}))
    purge = ("run_maintenance", {"service": q, "action": "purge_dlq"})
    assert run(sc, ("scale", {"service": wk, "replicas": 12}), wait=10).finalize()["fixed"][0] is False
    limit = ("set_config", {"service": sc.entry, "key": "rate_limit_rps", "value": int(sc.params["base_rps"] * .5)})
    assert run(sc, limit).finalize()["fixed"][0] is False
    plain, both = run(sc, fix), run(sc, fix, purge)
    pb, bb = plain.finalize(), both.finalize()
    assert pb["fixed"][0] is bb["fixed"][0] is True and bb["P_collateral"] == 0
    assert sum(r["duplicate_shipments"] for r in both.w.biz_rec) < sum(r["duplicate_shipments"] for r in plain.w.biz_rec)


# ---- R13 ----------------------------------------------------------------------------------------------------
def test_r13_failover_without_maintenance_mode_is_reverted():
    sc = sc_of("R13")
    db = sc.faults[0]["node"]
    env = run(sc, wait=6)
    assert series(env, db, "error_rate", 3)[-1] > .9 and max(series(env, db, "replica_lag_s", 3)) < 5
    assert next(n for n in env.call("get_topology")["result"]["nodes"] if n["name"] == db)["replica_in_sync"]
    errs = [x["msg"] for x in env.call("get_logs", service=db, level="ERROR")["result"]["lines"]]
    assert any("I/O error" in m for m in errs)
    assert env.call("get_logs", service=db, grep="WAL segment")["result"]["lines"]                # the red herring
    fo, mm = ("failover_db", {}), ("set_config", {"service": db, "key": "cluster_manager", "value": "maintenance"})
    e = run(sc, fo, fo, wait=10)
    assert any("reverted" in x["text"] for x in e.call("get_events")["result"]["events"])
    b = e.finalize()
    assert b["fixed"][0] is False and b["P_collateral"] >= .2 and b["M_dataloss"] == 1
    assert run(sc, ("restart", {"service": db}), wait=10).finalize()["fixed"][0] is False
    assert run(sc, mm).finalize()["fixed"][0] is False                                           # maintenance mode alone is no fix
    b = run(sc, mm, fo).finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and b["M_dataloss"] == 1
    assert b["U"] > Env(sc).finalize()["U"] + .1


# ---- R14 ----------------------------------------------------------------------------------------------------
def test_r14_one_client_holds_the_slots_scaling_restarting_or_global_limits_do_not_help():
    sc = sc_of("R14")
    f = sc.faults[0]
    gw = f["node"]
    env = run(sc, wait=8)
    assert series(env, gw, "conns", 1)[-1] >= env.call("get_config", service=gw)["result"]["max_connections"]
    err = env.call("get_logs", service=gw, level="ERROR", grep="client=", limit=100)["result"]["lines"]
    assert err and {x["msg"].split("client=")[1].split()[0] for x in err} == {f["id"]}
    ep = "/" + next(e.callee for e in sc.edges if e.caller == gw)
    assert any("gateway_wait_ms" in sp for tr in env.call("get_traces", endpoint=ep, n=5)["result"]["traces"] for sp in tr["spans"])
    noop = Env(sc).finalize()
    assert run(sc, ("scale", {"service": gw, "replicas": 20}), wait=20).finalize()["fixed"][0] is False
    assert run(sc, ("scale", {"service": gw, "replicas": 20})).finalize()["U"] < noop["U"] + .05
    b = run(sc, ("restart", {"service": gw})).finalize()
    assert b["fixed"][0] is False and b["U"] <= noop["U"] + .01
    rl = run(sc, ("set_config", {"service": gw, "key": "rate_limit_rps", "value": int(sc.params["base_rps"] * .5)})).finalize()
    assert rl["fixed"][0] is False and rl["U"] < noop["U"] + .05
    top = ("set_config", {"service": gw, "key": "block_client", "value": "mobile-ios"})
    assert run(sc, top).finalize()["U"] < noop["U"]                                              # a real customer is rejected
    b = run(sc, ("set_config", {"service": gw, "key": "block_client", "value": f["id"]})).finalize()
    assert b["fixed"][0] is True and b["P_collateral"] == 0 and b["U"] > noop["U"] + .2


# ---- truth leaks / easy is gone ---------------------------------------------------------------------------------
def test_agent_visible_outputs_never_contain_fault_class_names():
    from oncall.scenarios import FAMILIES
    obs = ("get_status", "get_events", "get_topology", "get_flags", "get_deploys", "get_business_metrics")
    for sc in suite("dev"):
        env = policies.run_env("reference", sc)
        blob = " ".join(str(e["result"]) for e in env.log)
        env = Env(sc)
        env.call("wait", minutes=30)
        out = [env.call(t)["result"] for t in obs]
        for n in sc.order:
            out += [env.call("get_logs", service=n, limit=200)["result"], env.call("get_config", service=n)["result"],
                    env.call("get_metrics", services=[n], window=30)["result"]]
            if sc.nodes[n].kind != "external":
                out.append(env.call("get_instances", service=n)["result"])
        blob += " ".join(map(str, out))
        for cls in FAMILIES:
            assert cls not in blob, (sc.id, cls)


def test_no_easy_level_remains_anywhere():
    import re
    from pathlib import Path
    from oncall import cli
    root = Path(__file__).resolve().parents[1]
    for p in (root / "src" / "oncall").glob("*.py"):
        assert not re.search(r"\beasy\b", p.read_text(encoding="utf-8"), re.I), p.name
    assert not re.search(r"\beasy\b", cli.instruction(), re.I)
    assert "easy" not in cli.render_md(cli.make_report({"suite": "x", "scenarios": [], "policies": {}}))
