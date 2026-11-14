"""Shared scenario finders for the test files."""
from functools import lru_cache

from oncall.scenarios import Scenario, suite


@lru_cache(maxsize=None)
def pool():
    return tuple(suite("dev") + suite("judge"))


def with_class(cls, pred=lambda s, f: True, roles=None, diff=None):
    """(scenario, index of the fault) of the first dev / judge scenario (else a scan over generated seeds) holding `cls`."""
    def scan(scs):
        for sc in scs:
            for i, f in enumerate(sc.faults):
                if f["fault_class"] == cls and (roles is None or f["role"] in roles) and pred(sc, f):
                    return sc, i
    hit = scan(s for s in pool() if diff in (None, s.difficulty))
    for d, base in (("hard", 5000), ("expert", 6000), ("medium", 4000)):
        if diff not in (None, d):
            continue
        if hit:
            break
        hit = scan(Scenario(s, d) for s in range(base, base + 80))
    assert hit, cls
    return hit
