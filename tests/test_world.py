import unittest

from triage_env.baselines import POLICIES, reference
from triage_env.world import BUDGET, KINDS, World, replay

SEEDS = range(12)


def run(policy, seed):
    w = World(seed)
    POLICIES[policy](w)
    return w.finish()


class Integrity(unittest.TestCase):
    def test_do_nothing_and_stop_early_earn_nothing(self):
        for s in SEEDS:
            self.assertEqual(run("do_nothing", s)["reward"], 0)
            self.assertEqual(run("stop_early", s)["reward"], 0)

    def test_reference_beats_every_shortcut_with_margin(self):
        ref = [run("reference", s)["reward"] for s in SEEDS]
        self.assertGreater(min(ref), 0.85)
        for name in ("loudest_fix", "shotgun", "do_nothing", "stop_early"):
            other = [run(name, s)["reward"] for s in SEEDS]
            self.assertLess(max(other), min(ref) - 0.3, name)

    def test_deterministic_and_replayable(self):
        w = World(3)
        reference(w)
        self.assertEqual(w.finish(), replay(3, w.trace))
        w2 = World(3)
        reference(w2)
        self.assertEqual(w.trace, w2.trace)

    def test_preemptive_fixes_do_not_count(self):
        """Firing remedies before a fault has begun must not pre-empt it."""
        for s in SEEDS:
            w = World(s)
            late = [f for f in w.faults if f.onset > 0][0]
            for tool in ("restart", "rollback", "scale"):
                w.call(tool, service=late.service)
            self.assertIsNone(late.fixed_at)

    def test_temporary_relief_is_not_a_fix(self):
        """A restart of a resource-exhausted service masks symptoms, then they return."""
        hits = 0
        for s in range(60):
            w = World(s)
            f = w.faults[0]
            if f.kind != "resource_exhaustion":
                continue
            hits += 1
            w.call("restart", service=f.service)
            w.call("wait", ticks=3)
            self.assertLess(w.errors(w.tick)[f.service], 0.05)
            w.call("wait", ticks=6)
            self.assertGreater(w.errors(w.tick)[f.service], 0.3)
            self.assertEqual(w.finish()["recovery"], 0)
        self.assertGreater(hits, 3)

    def test_stopping_before_the_second_incident_is_penalised(self):
        """Fix incident one, submit at once: incident two (later onset) is unhandled."""
        for s in SEEDS:
            w = World(s)
            f = w.faults[0]
            fix = {"stuck_process": ("restart", {}), "resource_exhaustion": ("scale", {}),
                   "bad_deploy": ("rollback", {}), "bad_config": ("set_config", {"key": f.key, "value": f.good})}
            tool, extra = fix[f.kind]
            w.call(tool, service=f.service, **extra)
            w.call("submit", findings=[{"service": f.service, "kind": f.kind}])
            self.assertLess(w.finish()["recovery"], 0.95)

    def test_findings_without_fix_earn_no_diagnosis_credit(self):
        w = World(1)
        w.call("submit", findings=[{"service": f.service, "kind": f.kind} for f in w.faults])
        self.assertEqual(w.finish()["diagnosis"], 0)

    def test_budget_is_enforced(self):
        w = World(0)
        for _ in range(BUDGET):
            w.call("restart", service=next(iter(w.deps)))
        self.assertTrue(w.done)
        self.assertFalse(w.call("get_alerts")["ok"])

    def test_every_service_has_a_user_facing_dependant(self):
        for s in range(30):
            w = World(s)
            for svc in w.order:
                if w.tier[svc] > 0:
                    self.assertTrue(w.dependents[svc], (s, svc))

    def test_observations_are_complete_enough_to_solve(self):
        """Fairness: the fault signature is visible in logs for every kind that occurs."""
        seen = set()
        for s in range(40):
            w = World(s)
            for f in w.faults:
                if f.onset > 0:
                    continue
                text = "\n".join(w.call("get_logs", service=f.service, n=10)["result"])
                seen.add(f.kind)
                sig = {"bad_deploy": "NullPointer", "bad_config": "invalid value",
                       "resource_exhaustion": ("exhausted", "OutOfMemory"), "stuck_process": "unresponsive"}[f.kind]
                sig = (sig,) if isinstance(sig, str) else sig
                self.assertTrue(any(x in text for x in sig), (s, f.kind))
        self.assertEqual(seen, set(KINDS))


if __name__ == "__main__":
    unittest.main()
