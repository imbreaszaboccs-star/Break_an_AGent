"""Build a chat-format SFT dataset (JSONL) from OnCall rollouts.

Sources: (a) run dirs / *.jsonl written by logsink, (b) --generate-reference: reference rollouts on the `train` split.
Keeps score >= --min-score, refuses any scenario that belongs to dev/judge/judge-fast/heldout, dedupes.
Row: {"messages": [system, user, assistant(tool_calls)/tool ...], "tools": [...], "meta": {...}}.
Tool-call `arguments` are dicts (what chat templates expect), tool message content is json.dumps(result)
exactly like oncall.agent produces it, so train and inference prompts match.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from oncall.agent import KICKOFF, tool_schemas
from oncall.cli import instruction
from oncall.policies import run_env
from oncall.scenarios import Scenario, suite

EVAL_SUITES = ("dev", "judge", "judge-fast")


def family(sc):
    """Family label such as 'F12'. Uses Scenario.family if present, else the f<N> part of the scenario id."""
    f = getattr(sc, "family", None)
    if f:
        return str(f).upper()
    m = re.search(r"-f(\d+)-", getattr(sc, "id", ""))
    return f"F{m.group(1)}" if m else "?"


def forbidden_seeds():
    """Seeds of every evaluation suite. heldout needs ONCALL_HELDOUT_SALT; without it we rely on its non-empty salt."""
    seeds = {sc.seed for name in EVAL_SUITES for sc in suite(name)}
    if os.environ.get("ONCALL_HELDOUT_SALT"):
        seeds |= {sc.seed for sc in suite("heldout")}
    else:
        print("warning: ONCALL_HELDOUT_SALT not set, heldout seeds checked only via salt != ''", file=sys.stderr)
    return seeds


def check_leak(sc, bad_seeds):
    if sc.seed in bad_seeds or sc.salt:
        sys.exit(f"refusing scenario {sc.id} (seed={sc.seed}, salt={sc.salt!r}): belongs to an evaluation suite")


def to_messages(log):
    """env.log / call rows -> OpenAI-style messages (one tool call per assistant turn)."""
    msgs = [{"role": "system", "content": instruction()}, {"role": "user", "content": KICKOFF}]
    for i, e in enumerate(log):
        args = {k: v for k, v in e["args"].items() if v is not None}
        msgs.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"call_{i}", "type": "function", "function": {"name": e["tool"], "arguments": args}}]})
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "content": json.dumps(e["result"], default=str)})
    return msgs


def from_transcript(path):
    """Real LLM transcript (oncall.agent's <episode>.messages.json) -> messages with the model's own text kept.
    Tool-call arguments become dicts; an episode with unparsable arguments is skipped (returns None)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    msgs = data["messages"] if isinstance(data, dict) else data
    out = []
    for m in msgs:
        m = dict(m)
        if m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = dict(tc["function"])
                if isinstance(fn.get("arguments"), str):
                    try:
                        fn["arguments"] = json.loads(fn["arguments"] or "{}")
                    except ValueError:
                        return None
                calls.append({**tc, "function": fn})
            m["tool_calls"] = calls
        out.append(m)
    return out


def episodes_from_runs(paths):
    """Yield (scenario, score, log, source, messages|None) from logsink JSONL files.
    messages is the sibling <episode>.messages.json transcript when present (keeps the model's reasoning)."""
    files = []
    for p in map(Path, paths):
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    for f in files:
        rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        fin = next((r for r in rows if r.get("type") == "final"), None)
        if fin is None:
            continue
        bd = fin["breakdown"]
        sc = Scenario(bd["seed"], bd["difficulty"], bd.get("salt", ""))
        tr = f.with_name(f.stem + ".messages.json")
        yield sc, fin["score"], [r for r in rows if r.get("type") == "call"], str(f), from_transcript(tr) if tr.exists() else None


def episodes_from_reference(n, policy):
    # ponytail: `train` has 100 scenarios; --n beyond that wraps nothing, it just stops at 100.
    for sc in suite("train")[:n]:
        env = run_env(policy, sc)
        yield sc, env.finalize()["score"], env.log, f"generate:{policy}", None


def build(episodes, min_score=0.8, exclude=(), bad_seeds=frozenset()):
    tools, seen, rows, drop = tool_schemas(), set(), [], {"low_score": 0, "excluded_family": 0, "duplicate": 0, "empty": 0}
    for sc, score, log, src, transcript in episodes:
        check_leak(sc, bad_seeds)
        if score < min_score:
            drop["low_score"] += 1
        elif family(sc) in exclude:
            drop["excluded_family"] += 1
        elif not log:
            drop["empty"] += 1
        else:
            msgs = transcript or to_messages(log)   # ponytail: scripted policies have no reasoning text
            key = hashlib.sha256(json.dumps(msgs[2:], sort_keys=True).encode()).hexdigest()
            if key in seen:
                drop["duplicate"] += 1
                continue
            seen.add(key)
            rows.append({"messages": msgs, "tools": tools, "meta": {
                "scenario": sc.id, "seed": sc.seed, "difficulty": sc.difficulty, "family": family(sc),
                "score": score, "n_calls": len(log), "source": src}})
    return rows, drop


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("runs", nargs="*", help="run dirs or JSONL files written by logsink")
    p.add_argument("--generate-reference", action="store_true", help="also roll out a policy on the train split")
    p.add_argument("--policy", default="reference", choices=["reference"], help="oracle is excluded on purpose: it uses ground truth")
    p.add_argument("--n", type=int, default=100, help="train scenarios for --generate-reference")
    p.add_argument("--min-score", type=float, default=0.8)
    p.add_argument("--exclude-families", default="", help="comma list of family labels, e.g. F12,F14")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    if not a.runs and not a.generate_reference:
        p.error("give run dirs and/or --generate-reference")
    exclude = {x.strip().upper() for x in a.exclude_families.split(",") if x.strip()}

    def episodes():
        yield from episodes_from_runs(a.runs)
        if a.generate_reference:
            yield from episodes_from_reference(a.n, a.policy)
    rows, drop = build(episodes(), a.min_score, exclude, forbidden_seeds())
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {len(rows)} examples to {out}; dropped {drop}")
    if exclude:
        print(f"excluded families: {sorted(exclude)} (labels seen: {sorted({r['meta']['family'] for r in rows})})")


if __name__ == "__main__":
    main()
