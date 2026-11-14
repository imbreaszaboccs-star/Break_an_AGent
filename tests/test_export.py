"""The committed Harbor tasks ship a copy of src/oncall in solution/ (oracle runs); it must not go stale."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_harbor_solution_copy_matches_src():
    src = {p.name: p.read_bytes() for p in (ROOT / "src" / "oncall").glob("*.py")}
    tasks = sorted((ROOT / "harbor" / "tasks").glob("*/solution/oncall"))
    assert len(tasks) == 24
    for d in tasks:
        got = {p.name: p.read_bytes() for p in d.glob("*.py")}
        assert got == src, f"{d} is stale: run `make export`"
