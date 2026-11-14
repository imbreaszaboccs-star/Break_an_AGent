"""LLM agent over any OpenAI-compatible /chat/completions endpoint (Gemini, Nemotron, vLLM, ...).

An extra policy: the evaluation never depends on it. stdlib + oncall only.

    python -m oncall.agent --provider gemini --model <id> --suite judge-fast --runs 3 \
        --out results/agent-<model>.json --run-dir runs/
"""
import argparse
import asyncio
import functools
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from . import logsink
from .client import http_call, local_call
from .scenarios import Scenario, suite
from .sim import MAX_CALLS, Env

# base_url_env: env var that overrides base_url; key_env: env var holding the API key (None = no key).
PROVIDERS = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "key_env": "GEMINI_API_KEY"},
    # extra: merged into every request body (provider-specific knobs); --extra-body overrides it.
    "nemotron": {"base_url": "https://integrate.api.nvidia.com/v1", "key_env": "NVIDIA_API_KEY",
                 "extra": {"chat_template_kwargs": {"enable_thinking": True}, "max_tokens": 16384}},
    "vllm": {"base_url": "http://localhost:8000/v1", "base_url_env": "VLLM_BASE_URL", "key_env": None},
    # Verda serverless inference (e.g. kimi-k3-1-pro): VERDA_INFERENCE_BASE_URL is the host *without* /v1.
    "verda": {"base_url": None, "base_url_env": "VERDA_INFERENCE_BASE_URL", "base_url_suffix": "/v1",
              "key_env": "VERDA_INFERENCE_API_KEY"},
    "openai-compatible": {"base_url": None, "key_env": None},     # needs --base-url [--api-key-env]
}
KICKOFF = "The incident is in progress. Start investigating with the tools."
NUDGE = "You did not call a tool. Keep using the tools; call resolve_incident when you are done."
RETRY_CODES = {429, 500, 502, 503, 504}


class ApiError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


# ---- tool schemas (always derived from the MCP server so they cannot drift) -----------------------
def _inline(node, defs):
    """Resolve $ref/$defs and drop `title`: not every OpenAI-compatible backend (Gemini) accepts them."""
    if isinstance(node, list):
        return [_inline(x, defs) for x in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _inline(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
    return {k: _inline(v, defs) for k, v in node.items() if k not in ("$defs", "title")}


@lru_cache(maxsize=1)
def tool_schemas():
    """OpenAI `tools` array built from FastMCP's list_tools()."""
    from .server import build_server
    # ponytail: any scenario gives the same tool list; the cache assumes the schema is scenario independent.
    tools = asyncio.run(build_server(Scenario(1000, "medium")).list_tools())
    out = []
    for t in tools:
        schema = t.inputSchema
        params = _inline(schema, schema.get("$defs", {}))
        out.append({"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": params}})
    return out


# ---- chat completions over urllib -----------------------------------------------------------------
def chat(base_url, api_key, body, timeout=600, retries=10):
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = json.dumps(body).encode()
    for attempt in range(retries + 1):
        retry_after = None
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")      # server text only, never our headers
            if e.code not in RETRY_CODES:
                raise ApiError(f"HTTP {e.code}: {detail}", e.code)
            err = ApiError(f"HTTP {e.code}: {detail}", e.code)
            ra = e.headers.get("Retry-After", "")
            retry_after = float(ra) if ra.replace(".", "", 1).isdigit() else None
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            err = ApiError(f"{type(e).__name__}: {e}")
        if attempt == retries:
            raise err
        # ponytail: ~15 min of patience per request; free tiers 429 in bursts. Episode-level retry sits on top (run_suite).
        time.sleep(min(retry_after if retry_after is not None else 2 * 2 ** attempt, 120))


# ---- the loop ---------------------------------------------------------------------------------------
def _parse_args(raw):
    """-> (args dict, error or None). Malformed arguments become a tool error, never an exception."""
    if raw in (None, ""):
        return {}, None
    if isinstance(raw, dict):
        return raw, None
    try:
        args = json.loads(raw)
    except (TypeError, ValueError) as e:
        return None, f"malformed arguments (not valid JSON): {e}"
    if not isinstance(args, dict):
        return None, "malformed arguments: expected a JSON object"
    return args, None


def run_agent(scenario, *, base_url, model, api_key=None, temperature=0.0, max_turns=150, seed=None, url=None, extra=None):
    """Run one episode. Returns (env_or_none, breakdown_or_none, transcript).

    Local mode (url=None): env is the Env and breakdown comes from env.finalize().
    url mode: the tools run on the MCP server at `url`; env and breakdown are None (the caller finalizes).
    transcript = {"model", "messages", "stop", "turns", "usage"}.
    """
    from .cli import instruction
    env = None if url else Env(scenario)
    call = http_call(url) if url else local_call(env)
    messages = [{"role": "system", "content": instruction()}, {"role": "user", "content": KICKOFF}]
    tr = {"model": model, "messages": messages, "stop": "max_turns", "turns": 0, "usage": {"prompt": 0, "completion": 0}}
    n_tool_calls, nudged = 0, False
    for turn in range(max_turns):
        body = {"model": model, "messages": messages, "tools": tool_schemas(), "tool_choice": "auto", "temperature": temperature}
        if seed is not None:
            body["seed"] = seed
        body.update(extra or {})
        try:
            resp = chat(base_url, api_key, body)
            msg = resp["choices"][0]["message"]
        except (ApiError, KeyError, IndexError, TypeError) as e:
            tr["stop"] = f"api_error:{getattr(e, 'code', None) or type(e).__name__}:{e}"
            break
        tr["turns"] = turn + 1
        u = resp.get("usage") or {}
        tr["usage"]["prompt"] += u.get("prompt_tokens") or 0
        tr["usage"]["completion"] += u.get("completion_tokens") or 0
        calls = msg.get("tool_calls") or []
        a_msg = {"role": "assistant", "content": msg.get("content") or ""}
        reasoning = msg.get("reasoning_content") or msg.get("reasoning")
        if reasoning:
            # ponytail: kept in the transcript for analysis/SFT; sent back too, backends ignore unknown fields.
            a_msg["reasoning_content"] = reasoning
        if calls:
            # keep provider extras on each call (Gemini 3 `extra_content.google.thought_signature` must be echoed back)
            a_msg["tool_calls"] = [{**c, "id": c.get("id") or f"call_{turn}_{i}", "type": "function",
                                    "function": {**(c.get("function") or {}),
                                                 "name": (c.get("function") or {}).get("name", ""),
                                                 "arguments": (c.get("function") or {}).get("arguments") or "{}"}}
                                   for i, c in enumerate(calls)]
        messages.append(a_msg)
        if not calls:
            if nudged:
                tr["stop"] = "no_tool_call"
                break
            nudged = True
            messages.append({"role": "user", "content": NUDGE})
            continue
        nudged = False
        resolved = over = False
        for c in a_msg["tool_calls"]:
            name = c["function"]["name"]
            args, err = _parse_args(c["function"]["arguments"])
            if err:
                out = {"ok": False, "error": err}
            else:
                n_tool_calls += 1
                try:
                    out = call(name, **{k: v for k, v in args.items() if v is not None})
                except Exception as e:      # bad kwargs (e.g. an arg named `tool`), transport errors
                    out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                resolved |= name == "resolve_incident" and bool(out.get("ok"))
                over |= "episode over" in str(out.get("error", ""))
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(out, default=str)})
        if env is not None:
            over |= env.done
        if resolved or over or n_tool_calls >= MAX_CALLS:
            tr["stop"] = "resolved" if resolved else "episode_over"
            break
    return env, (env.finalize() if env else None), tr


# ---- providers / CLI ----------------------------------------------------------------------------
def resolve_provider(provider, base_url=None, api_key_env=None):
    """-> (base_url, api_key). Exits 2 with a clear message on missing config; never echoes the key."""
    if provider not in PROVIDERS:
        sys.exit(f"unknown provider {provider!r}; known: {', '.join(PROVIDERS)}")
    p = PROVIDERS[provider]
    env_base = os.environ.get(p.get("base_url_env", ""), "")
    if env_base:
        env_base = env_base.rstrip("/") + p.get("base_url_suffix", "")
    base = base_url or env_base or p["base_url"]
    if not base:
        print(f"error: provider {provider!r} needs --base-url", file=sys.stderr)
        sys.exit(2)
    key_env = api_key_env or p["key_env"]
    key = os.environ.get(key_env) if key_env else None
    if key_env and not key:
        print(f"error: environment variable {key_env} is not set (needed for provider {provider!r})", file=sys.stderr)
        sys.exit(2)
    return base, key


def slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


EPISODE_RETRIES, COOLDOWN = 2, 120


def _infra(stop):
    """API/transport failure (not the agent's doing). 400/401/403/404 are config errors and abort instead."""
    return stop.startswith("api_error") and not stop.startswith("api_error:40")


def _finished(run_dir, ep):
    """Breakdown of an episode that already finished without an infrastructure error, else None."""
    tr, log_f = Path(run_dir) / f"{ep}.messages.json", Path(run_dir) / f"{ep}.jsonl"
    if not (tr.exists() and log_f.exists()) or _infra(json.loads(tr.read_text(encoding="utf-8"))["stop"]):
        return None
    rows = [json.loads(x) for x in log_f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return next((x["breakdown"] for x in rows if x.get("type") == "final"), None)


def run_suite(provider, model, suite_name, runs, base_url, api_key, temperature, max_turns, seed, run_dir=None, log=functools.partial(print, flush=True), workers=1,
              extra=None, limit=None):
    """Same JSON shape as `oncall eval`: runs x scenarios breakdowns under policy `agent:<provider>:<model>`."""
    scs = suite(suite_name)[:limit]
    extra = PROVIDERS.get(provider, {}).get("extra") if extra is None else extra
    name = f"agent:{provider}:{model}"
    res = {"suite": suite_name, "scenarios": [s.id for s in scs], "policies": {name: []}}
    tool_schemas()      # build once before threads start

    abort = threading.Event()

    def one(job):
        r, sc = job
        ep = f"{slug(name)}-r{r + 1}-{sc.id}"
        if abort.is_set():
            return None, "skipped"
        done = _finished(run_dir, ep) if run_dir else None
        if done:                                          # --resume: keep episodes that already finished cleanly
            log(f"run {r + 1}/{runs} {sc.id}: score={done['score']:.3f} (kept from {run_dir})")
            return {**done, "run": r + 1}, "kept"
        for attempt in range(EPISODE_RETRIES + 1):
            env, bd, tr = run_agent(sc, base_url=base_url, model=model, api_key=api_key, temperature=temperature, extra=extra,
                                    max_turns=max_turns, seed=None if seed is None else seed + r)
            if not _infra(tr["stop"]) or attempt == EPISODE_RETRIES:
                break
            log(f"run {r + 1}/{runs} {sc.id}: infrastructure error ({tr['stop'][:50]}), restarting the episode "
                f"after {COOLDOWN * (attempt + 1)}s")
            time.sleep(COOLDOWN * (attempt + 1))
        if run_dir:
            logsink.write_episode(run_dir, ep, env, bd)
            # ponytail: LLM messages go in a sibling file (logsink rows are fixed); *.messages.json is not globbed as a rollout.
            (Path(run_dir) / f"{ep}.messages.json").write_text(json.dumps(tr, indent=1, default=str), encoding="utf-8")
        if tr["stop"].startswith("api_error:40"):         # 400/401/403/404: every later request would fail too
            abort.set()
        if _infra(tr["stop"]):                            # never score an API outage as an agent failure
            log(f"run {r + 1}/{runs} {sc.id}: EXCLUDED, infrastructure error: {tr['stop'][:60]}")
            return None, tr["stop"]
        log(f"run {r + 1}/{runs} {sc.id}: score={bd['score']:.3f} stop={tr['stop'][:60]} turns={tr['turns']}")
        return {**bd, "run": r + 1}, tr["stop"]

    jobs = [(r, sc) for r in range(runs) for sc in scs]
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for bd, stop in ex.map(one, jobs):
            if stop.startswith("api_error:40"):
                sys.exit(f"error: API rejected the request ({stop}); aborting")
            if bd:
                res["policies"][name].append(bd)
            elif stop != "skipped":
                res.setdefault("excluded", []).append(stop[:80])
    if res.get("excluded"):
        log(f"WARNING: {len(res['excluded'])} episodes excluded for infrastructure errors; rerun with --resume to fill them in")
    return res


def main(argv=None):
    from .cli import dump, stamp, table
    p = argparse.ArgumentParser(prog="oncall.agent", description="Run an OpenAI-compatible chat model as the on-call agent.")
    p.add_argument("--provider", required=True, choices=list(PROVIDERS))
    p.add_argument("--model", required=True, help="model id as the endpoint knows it (no default on purpose)")
    p.add_argument("--suite", default="judge-fast")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--out")
    p.add_argument("--run-dir")
    p.add_argument("--resume", help="existing run dir: keep its cleanly finished episodes, rerun the rest")
    p.add_argument("--base-url", help="override the provider's base URL (required for openai-compatible)")
    p.add_argument("--api-key-env", help="name of the env var holding the key (overrides the preset)")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-turns", type=int, default=150)
    p.add_argument("--seed", type=int, help="sent to the API as `seed` (+ run index)")
    p.add_argument("--workers", type=int, default=1, help="parallel episodes (keep 1 for rate-limited free tiers)")
    p.add_argument("--extra-body", type=json.loads, help="JSON merged into every request (default: the provider preset's)")
    p.add_argument("--limit", type=int, help="only the first N scenarios of the suite (smoke runs)")
    a = p.parse_args(argv)
    base, key = resolve_provider(a.provider, a.base_url, a.api_key_env)
    run_dir = Path(a.resume) if a.resume else Path(a.run_dir) / stamp() if a.run_dir else None
    res = run_suite(a.provider, a.model, a.suite, a.runs, base, key, a.temperature, a.max_turns, a.seed, run_dir, workers=a.workers,
                    extra=a.extra_body, limit=a.limit)
    print(table(res))
    if a.out:
        dump(a.out, res)


if __name__ == "__main__":
    main()
