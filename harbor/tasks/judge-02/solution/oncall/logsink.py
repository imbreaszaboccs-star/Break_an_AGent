"""Episode logs: JSONL file always, ClickHouse (JSONEachRow over HTTP) only if ONCALL_CLICKHOUSE_URL is set."""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def rows(episode_id, env, breakdown):
    """One row per tool call, then a final row with score, tags and the scenario truth."""
    sc = env.sc
    out = [{"type": "call", "episode": episode_id, "scenario": sc.id, **e} for e in env.log]
    out.append({"type": "final", "episode": episode_id, "scenario": sc.id, "score": breakdown["score"],
                "tags": breakdown["tags"], "breakdown": breakdown, "truth": {"faults": sc.faults, "herring": sc.herring}})
    return out


def write_episode(run_dir, episode_id, env, breakdown):
    rs = rows(episode_id, env, breakdown)
    body = "".join(json.dumps(r, default=str) + "\n" for r in rs)
    path = Path(run_dir) / f"{episode_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    url = os.environ.get("ONCALL_CLICKHOUSE_URL")
    if url:
        try:
            q = urllib.parse.quote("INSERT INTO oncall_rollouts FORMAT JSONEachRow")
            urllib.request.urlopen(urllib.request.Request(f"{url.rstrip('/')}/?query={q}", data=body.encode()), timeout=10).read()
        except Exception as e:      # never let a sink break an episode
            print(f"warning: clickhouse sink failed: {e}", file=sys.stderr)
    return path
