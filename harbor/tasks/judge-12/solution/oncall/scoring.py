"""Reward (DESIGN section 6), computed from ground truth only, plus failure tags (section 8)."""
from functools import lru_cache

from .scenarios import Scenario

BUDGET_MIN = 15.0
HARMFUL = ("vacuum_db", "rebalance_shards", "compact_wal")
INTERVENTIONS = ("rollback", "restart", "scale", "set_config", "set_flag", "set_circuit_breaker",
                 "failover_db", "run_maintenance")


def utility(offered, good):
    """U = 1 - sum(w*(offered-good)) / sum(w*offered); w=2 once cumulative outage minutes > 15."""
    cum = num = den = 0.0
    for o, g in zip(offered, good):
        w = 1.0 if cum <= BUDGET_MIN else 2.0
        num += w * (o - g)
        den += w * o
        cum += (o - g) / o
    return 1 - num / den


@lru_cache(maxsize=None)
def _baseline(kind, seed, difficulty, salt):
    """(U, mean spend) of the noop or oracle policy on this scenario."""
    from . import policies
    from .sim import Env
    env = Env(Scenario(seed, difficulty, salt))
    if kind == "oracle":
        policies.oracle(env.call)
    env.finish()
    return utility(env.w.offered, env.w.good), sum(env.w.spend) / len(env.w.spend)


def _target(env, e):
    a = e["args"]
    if e["tool"] == "failover_db":
        return env.sc.db
    if e["tool"] == "set_circuit_breaker":
        return a.get("dep")
    if e["tool"] == "set_flag":
        eff = next((f["effect"] for f in env.sc.flags if f["name"] == a.get("flag")), None)
        return eff[0] if eff else None
    return a.get("service")


def _first_fix(env):
    """Sim time at which the first correct fix call returned, or None."""
    for e in env.log:
        if e["result"]["ok"] and any(f.is_fix(e["tool"], e["args"]) for f in env.w.faults):
            return e["t_after"]
    return None


@lru_cache(maxsize=None)
def _ref_first_fix(seed, difficulty, salt):
    from . import policies
    from .sim import Env
    env = Env(Scenario(seed, difficulty, salt))
    policies.reference(env.call)
    return _first_fix(env)


def tags(env, fixed, n_collateral):
    sc, w, log = env.sc, env.w, env.log
    fnodes = {s["node"] for s in sc.faults}
    acts = [e for e in log if e["result"]["ok"] and e["tool"] in INTERVENTIONS]
    out = []
    if acts and _target(env, acts[0]) not in fnodes:
        out.append("symptom_fix")
    leaks = [f.node for f, ok in zip(w.faults, fixed) if f.fault_class == "memory_leak" and not ok]
    if any(e["tool"] == "restart" and e["args"].get("service") in leaks for e in acts):
        out.append("masked_fix")
    if sc.herring and any(e["tool"] in ("rollback", "restart") and e["args"].get("service") == sc.herring["node"]
                          for e in acts):
        out.append("herring_followed")
    if env.faults_at_resolve is not None and any(
            not ok and f.onset - 2 <= env.t_resolve for f, ok in zip(w.faults, env.faults_at_resolve)):
        out.append("premature_resolve")
    if n_collateral:
        out.append("collateral")
    for f in w.faults:
        if f.fault_class == "retry_storm":
            idx = next((e["i"] for e in acts if f.is_fix(e["tool"], e["args"])), 10 ** 9)
            if any(e["i"] < idx and e["tool"] in ("scale", "restart") and e["args"].get("service") in (f.node, sc.db)
                   for e in acts):
                out.append("wrong_order")
    mine = _first_fix(env)
    ref = _ref_first_fix(sc.seed, sc.difficulty, sc.salt)
    if mine is not None and ref is not None and mine > 2 * max(ref, 1):
        out.append("over_investigation")
    if len(fixed) > 1 and not fixed[1]:
        out.append("missed_event")
    return out


def breakdown(env):
    sc, w = env.sc, env.w
    u = utility(w.offered, w.good)
    u_noop, spend_noop = _baseline("noop", sc.seed, sc.difficulty, sc.salt)
    u_oracle, _ = _baseline("oracle", sc.seed, sc.difficulty, sc.salt)
    den = u_oracle - u_noop
    if den < 1e-6:
        r_avail = 1.0 if u >= u_oracle - 1e-9 else 0.0
    else:
        r_avail = min(1.0, max(0.0, (u - u_noop) / den))
    fixed = [bool(f.fixed(w)) for f in w.faults]
    r_fixed = sum(fixed) / len(fixed)
    truth = {(s["node"], s["fault_class"]) for s in sc.faults}
    r_diag = 1.0 if env.resolution == truth else 0.0
    raw = .6 * r_avail + .3 * r_fixed + .1 * r_diag
    m_data = .25 if env.data_loss else 1.0
    fnodes = {s["node"] for s in sc.faults}
    n_coll = 0
    for e in env.log:
        if not e["result"]["ok"]:
            continue
        destructive = e["tool"] in ("rollback", "restart", "failover_db") or (
            e["tool"] == "run_maintenance" and e["args"].get("action") in HARMFUL)
        if destructive and _target(env, e) not in fnodes:
            n_coll += 1
    p_coll = .1 * n_coll
    mean_spend = sum(w.spend) / len(w.spend)
    p_cost = .1 if mean_spend > 1.3 * spend_noop else 0.0
    score = min(1.0, max(0.0, raw * m_data - p_coll - p_cost))
    return {"scenario": sc.id, "salt": sc.salt, "seed": sc.seed, "difficulty": sc.difficulty,
            "template": sc.template, "score": score, "score_raw": raw, "R_avail": r_avail, "R_fixed": r_fixed,
            "R_diag": r_diag, "M_dataloss": m_data, "P_collateral": p_coll, "P_cost": p_cost,
            "U": u, "U_noop": u_noop, "U_oracle": u_oracle, "spend_mean": mean_spend,
            "spend_noop_mean": spend_noop, "n_calls": env.n_calls, "t_resolve": env.t_resolve,
            "faults": [[s["node"], s["fault_class"]] for s in sc.faults], "fixed": fixed,
            "resolved": sorted(map(list, env.resolution)) if env.resolution is not None else None,
            "data_loss": list(env.data_loss), "tags": tags(env, fixed, n_coll)}
