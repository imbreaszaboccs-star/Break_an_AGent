"""Load runs/**/*.jsonl into ClickHouse (table oncall_rollouts) over HTTP. Only when ONCALL_CLICKHOUSE_URL is set.

    ONCALL_CLICKHOUSE_URL=https://user:pass@host:8443 python analysis/load.py runs/ [--create]

--create applies analysis/schema.sql first. Append-only: loading the same dir twice duplicates rows.
"""
import argparse
import base64
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SETTINGS = {"input_format_skip_unknown_fields": 1, "input_format_json_read_objects_as_strings": 1}


def post(url, query, data=b""):
    p = urllib.parse.urlsplit(url)
    host = p.hostname + (f":{p.port}" if p.port else "")
    req = urllib.request.Request(f"{p.scheme}://{host}{p.path.rstrip('/')}/?{urllib.parse.urlencode({'query': query, **SETTINGS})}", data=data)
    if p.username:      # urllib ignores user:pass@ in URLs, send it as Basic auth
        cred = f"{urllib.parse.unquote(p.username)}:{urllib.parse.unquote(p.password or '')}"
        req.add_header("Authorization", "Basic " + base64.b64encode(cred.encode()).decode())
    return urllib.request.urlopen(req, timeout=60).read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="run dirs or JSONL files")
    ap.add_argument("--create", action="store_true", help="run schema.sql first")
    a = ap.parse_args(argv)
    url = os.environ.get("ONCALL_CLICKHOUSE_URL")
    if not url:
        print("ONCALL_CLICKHOUSE_URL is not set: nothing to do (JSONL stays the source of truth).")
        return 0
    if a.create:
        for stmt in Path(__file__).with_name("schema.sql").read_text(encoding="utf-8").split(";"):
            stmt = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
            if stmt:
                post(url, stmt)
    files = []
    for p in map(Path, a.paths):
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    n = 0
    for f in files:
        body = f.read_bytes()
        if body.strip():
            post(url, "INSERT INTO oncall_rollouts FORMAT JSONEachRow", body)
            n += 1
    print(f"loaded {n} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
