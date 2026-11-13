"""MCP server for one episode: one @mcp.tool per agent tool + POST /admin/finalize (token protected).

No tool exposes truth or score. Every handler takes the same FIFO lock, then calls Env.call.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
from typing import Literal, TypedDict

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from . import logsink
from .scenarios import FAMILIES, Scenario
from .sim import MAINT, RUNBOOKS, Env

Level = Literal["ALL", "ERROR", "WARN", "INFO"]
Mode = Literal["closed", "open", "fallback"]
Action = Literal[tuple(MAINT)]
Topic = Literal[tuple(RUNBOOKS)]


class RootCause(TypedDict):
    service: str
    fault_class: Literal[tuple(FAMILIES)]


def build_server(scenario, admin_token_sha256=None, run_dir=None):
    """Returns a FastMCP bound to a fresh Env; `mcp.env` is exposed for tests."""
    env = Env(scenario)
    lock = asyncio.Lock()          # asyncio.Lock wakes waiters in FIFO order
    # ponytail: stateless + JSON responses: no session bookkeeping, the Env is the only state.
    mcp = FastMCP("oncall-sim", host="0.0.0.0", port=8000, stateless_http=True, json_response=True)
    mcp.env = env

    async def run(tool, **args):
        async with lock:
            return json.dumps(env.call(tool, **{k: v for k, v in args.items() if v is not None}))

    # ---- observations ----
    @mcp.tool()
    async def get_status() -> str:
        """Current time, remaining minutes, active alerts and cumulative spend. Costs 1 minute."""
        return await run("get_status")

    @mcp.tool()
    async def get_events(since: int = 0) -> str:
        """Alerts, deploys and team messages (last 100), optionally only those at t >= since. Costs 1 minute."""
        return await run("get_events", since=since)

    @mcp.tool()
    async def get_topology() -> str:
        """Services, kinds, replicas and the dependency edges with their circuit-breaker state. Costs 1 minute."""
        return await run("get_topology")

    @mcp.tool()
    async def get_metrics(services: list[str], window: int = 5) -> str:
        """Per-service metric series for 1-5 services over the last `window` (1-30) minutes. Costs 1 minute."""
        return await run("get_metrics", services=services, window=window)

    @mcp.tool()
    async def get_logs(service: str, level: Level = "ALL", grep: str = "", limit: int = 50) -> str:
        """Recent log lines of a service (last 60 min), filtered by level and substring; limit 1-200. Costs 1 minute."""
        return await run("get_logs", service=service, level=level, grep=grep, limit=limit)

    @mcp.tool()
    async def get_traces(endpoint: str, n: int = 5) -> str:
        """Sample n (1-10) request traces for an endpoint ("/" + a direct dependency of the entry service). Costs 2 minutes."""
        return await run("get_traces", endpoint=endpoint, n=n)

    @mcp.tool()
    async def get_deploys(service: str | None = None) -> str:
        """Deploy history (version, time, author, has_schema_migration, reversible) of one or all services. Costs 1 minute."""
        return await run("get_deploys", service=service)

    @mcp.tool()
    async def get_config(service: str) -> str:
        """Current configuration of a service and its change audit log. Costs 1 minute."""
        return await run("get_config", service=service)

    @mcp.tool()
    async def get_flags() -> str:
        """Feature flags and their change audit log. Costs 1 minute."""
        return await run("get_flags")

    @mcp.tool()
    async def get_runbook(topic: Topic) -> str:
        """Generic SRE runbook text for a topic. Costs 1 minute."""
        return await run("get_runbook", topic=topic)

    # ---- actions (effect lands when the action's duration has elapsed) ----
    @mcp.tool()
    async def rollback(service: str, version: str) -> str:
        """Roll a service back to an older version. Costs 5 minutes. Rolling back past an irreversible schema migration loses data."""
        return await run("rollback", service=service, version=version)

    @mcp.tool()
    async def restart(service: str) -> str:
        """Restart a service (cold start, resets memory). Costs 3 minutes."""
        return await run("restart", service=service)

    @mcp.tool()
    async def scale(service: str, replicas: int) -> str:
        """Set the replica count of a service (1-20). Costs 4 minutes and adds spend."""
        return await run("scale", service=service, replicas=replicas)

    @mcp.tool()
    async def set_config(service: str, key: str, value: int | float | bool | str) -> str:
        """Set a config key: max_retries 0-10, timeout_ms 10-30000, pool_size 1-100, rate_limit_rps 0-100000 (0 = off),
        log_level DEBUG|INFO|WARN|ERROR, dlq_enabled true|false. Costs 2 minutes."""
        return await run("set_config", service=service, key=key, value=value)

    @mcp.tool()
    async def set_flag(flag: str, on: bool) -> str:
        """Turn a feature flag on or off. Costs 1 minute."""
        return await run("set_flag", flag=flag, on=on)

    @mcp.tool()
    async def set_circuit_breaker(service: str, dep: str, mode: Mode) -> str:
        """Set the circuit breaker of the edge service -> dep: closed (normal), open (fail fast), fallback (degraded answer). Costs 2 minutes."""
        return await run("set_circuit_breaker", service=service, dep=dep, mode=mode)

    @mcp.tool()
    async def failover_db() -> str:
        """Fail over the database to its replica. Costs 6 minutes; data is lost if the replica is not in sync."""
        return await run("failover_db")

    @mcp.tool()
    async def run_maintenance(service: str, action: Action) -> str:
        """Run a maintenance action on a service (validity depends on the service kind). Costs 3 minutes. Some actions are harmful on a busy database."""
        return await run("run_maintenance", service=service, action=action)

    @mcp.tool()
    async def wait(minutes: int) -> str:
        """Let time pass (1-30 minutes). Costs `minutes` minutes."""
        return await run("wait", minutes=minutes)

    @mcp.tool()
    async def resolve_incident(root_causes: list[RootCause], summary: str = "") -> str:
        """Close the incident: list the root causes as {service, fault_class} (fault_class is one of
        bad_deploy, memory_leak, retry_storm, config_drift, external_dependency) and a short summary. Free; ends your interaction."""
        return await run("resolve_incident", root_causes=root_causes, summary=summary)

    # ---- admin: the only way to read the score; token protected, idempotent ----
    @mcp.custom_route("/admin/finalize", methods=["POST"])
    async def finalize(request):
        got = request.headers.get("authorization", "")
        token = got[7:] if got.lower().startswith("bearer ") else ""
        ok = bool(admin_token_sha256) and hmac.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(), admin_token_sha256.lower())
        if not ok:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        async with lock:
            out = env.finalize()
            if run_dir:
                logsink.write_episode(run_dir, scenario.id, env, out)
        return JSONResponse(out)

    return mcp


def main():
    try:
        sc = Scenario(int(os.environ["SCENARIO_SEED"]), os.environ["SCENARIO_DIFFICULTY"], os.environ.get("ONCALL_SALT", ""))
    except KeyError as e:
        sys.exit(f"missing environment variable {e}")
    token = os.environ.get("ADMIN_TOKEN_SHA256")
    if not token:
        print("warning: ADMIN_TOKEN_SHA256 not set, /admin/finalize will always return 401", file=sys.stderr)
    build_server(sc, token, os.environ.get("ONCALL_RUN_DIR")).run(transport="streamable-http")
