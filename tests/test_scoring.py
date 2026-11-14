from functools import partial

import pytest

from helpers import with_class
from oncall import policies, scoring
from oncall.scenarios import Scenario, suite
from oncall.sim import Env

DEV = suite("dev")


@pytest.mark.parametrize("sc", DEV, ids=lambda s: s.id)
def test_noop_is_zero_and_oracle_is_one(sc):
    n = policies.run_policy("noop", sc)
    assert n["score"] == 0 and n["R_avail"] == 0 and n["R_fixed"] == 0 and n["R_diag"] == 0
    assert n["U"] == n["U_noop"]
    o = policies.run_policy("oracle", sc)
    assert o["score"] >= 0.99 and o["R_fixed"] == 1 and o["R_diag"] == 1 and o["R_avail"] == 1
    assert o["P_collateral"] == 0 and o["P_cost"] == 0 and o["M_dataloss"] == 1
    assert o["U_oracle"] - o["U_noop"] > 0.04, "scenario has no real outage to fix"


def delayed(delay):
    return partial(policies.oracle, delay=delay)


@pytest.mark.parametrize("sc", DEV[:16], ids=lambda s: s.id)       # (a delayed second fault shifts the later scenarios' timeline)
def test_fixing_earlier_scores_at_least_as_much(sc):
    scores = []
    for d in (0, 3, 8, 15):
        env = Env(sc)
        delayed(d)(env.call)
        scores.append(env.finalize()["score"])
    assert scores == sorted(scores, reverse=True), scores
    assert scores[0] > scores[-1]


def test_utility_weights_error_budget():
    assert scoring.utility([100.0] * 30, [100.0] * 30) == 1.0
    # 20 minutes fully down: w=1 while the minutes lost so far are <= 15 (ticks 0..15), w=2 from then on
    off, good = [1.0] * 40, [0.0] * 20 + [1.0] * 20
    num, den = 16 + 4 * 2, 16 + 4 * 2 + 20 * 2
    assert scoring.utility(off, good) == pytest.approx(1 - num / den)


def test_cost_penalty_on_scale_to_max():
    b = policies.run_policy("exploit_scale_max", DEV[0])
    assert b["P_cost"] == 0.1 and b["spend_mean"] > 1.3 * b["spend_noop_mean"]
    assert policies.run_policy("reference", DEV[0])["P_cost"] == 0


def _migration_node(env):
    d = env.call("get_deploys")["result"]["deploys"]
    for n, v in d.items():
        if any(x["has_schema_migration"] and not x["reversible"] for x in v["history"]):
            return n, min(v["history"], key=lambda x: x["t"])["version"], v
    raise AssertionError("no irreversible migration in scenario")


@pytest.mark.parametrize("sc", DEV[:6], ids=lambda s: s.id)
def test_dataloss_on_irreversible_rollback(sc):
    env = Env(sc)
    n, oldest, v = _migration_node(env)
    assert env.call("rollback", service=n, version=oldest)["ok"]
    b = env.finalize()
    assert b["M_dataloss"] == 0.25 and b["data_loss"] and b["P_collateral"] >= 0.1
    # rolling back to the previous release (not past the migration) is data-safe
    env = Env(sc)
    cur = [x for x in v["history"] if x["version"] == v["current"]][0]
    prev = [x for x in v["history"] if x["t"] < cur["t"]][-1]["version"]
    if not any(x["has_schema_migration"] and not x["reversible"] for x in v["history"] if x["t"] >= cur["t"]):
        assert env.call("rollback", service=n, version=prev)["ok"]
        assert env.finalize()["M_dataloss"] == 1.0


def test_dataloss_on_failover_without_sync():
    seen = set()
    for sc in DEV:
        env = Env(sc)
        in_sync = next(n for n in env.call("get_topology")["result"]["nodes"] if n["kind"] == "db")["replica_in_sync"]
        env.call("failover_db")
        b = env.finalize()
        assert b["M_dataloss"] == (1.0 if in_sync else 0.25)
        assert b["P_collateral"] >= 0.1
        seen.add(in_sync)
    assert seen == {True, False}


def test_collateral_only_for_non_fault_nodes():
    sc = DEV[0]
    healthy = next(n for n in sc.order if n != sc.faults[0]["node"] and sc.nodes[n].kind == "app")
    env = Env(sc)
    env.call("restart", service=healthy)
    env.call("restart", service=healthy)
    assert env.finalize()["P_collateral"] == pytest.approx(0.2)
    env = Env(sc)
    env.call("restart", service=sc.faults[0]["node"])
    assert env.finalize()["P_collateral"] == 0


def test_masked_fix_and_tags():
    sc, _ = with_class("memory_leak", roles=("primary",), diff="medium")
    env = Env(sc)
    env.call("restart", service=sc.faults[0]["node"])
    env.call("resolve_incident", root_causes=[{"service": sc.faults[0]["node"], "fault_class": "memory_leak"}])
    b = env.finalize()
    assert b["R_fixed"] == 0 and b["R_diag"] == 1 and "masked_fix" in b["tags"] and "premature_resolve" in b["tags"]
    ref = policies.run_policy("reference", sc)
    assert ref["tags"] == [] or ref["tags"] == ["symptom_fix"]


def test_herring_and_wrong_order_tags():
    sc = next(s for s in DEV if s.difficulty == "medium" and s.herring and s.herring["node"] != s.faults[0]["node"])
    env = Env(sc)
    v = env.call("get_deploys", service=sc.herring["node"])["result"]["deploys"][sc.herring["node"]]["history"]
    env.call("rollback", service=sc.herring["node"], version=v[-2]["version"])
    assert "herring_followed" in env.finalize()["tags"]
    sc, i = with_class("retry_storm")
    env = Env(sc)
    env.call("scale", service=sc.faults[i]["node"], replicas=8)
    env.call("set_config", service=sc.faults[i]["node"], key="max_retries", value=1)
    assert "wrong_order" in env.finalize()["tags"]


def test_breakdown_is_complete_and_json_safe():
    import json
    b = policies.run_policy("reference", DEV[20])
    json.dumps(b)
    for k in ("score", "R_avail", "R_fixed", "R_diag", "M_dataloss", "P_collateral", "P_cost", "U", "U_noop",
              "U_oracle", "tags", "scenario", "n_calls", "t_resolve"):
        assert k in b
