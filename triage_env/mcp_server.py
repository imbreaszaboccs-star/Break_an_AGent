"""MCP server (stdio) exposing the triage world as tools.

Env: TRIAGE_SEED (default 0), TRIAGE_TRACE (default /logs/agent/triage_trace.json).
The trace (seed + every call) is rewritten after each call; the verifier replays it with
`triage_env.score`, so the reward comes from re-simulating, never from the server's say-so.
"""
import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .world import BUDGET, World

SEED = int(os.environ.get("TRIAGE_SEED", "0"))
TRACE = Path(os.environ.get("TRIAGE_TRACE", "/logs/agent/triage_trace.json"))
world = World(SEED)
mcp = FastMCP("incident-triage")


def _call(tool, **args):
    out = world.call(tool, **args)
    try:
        TRACE.parent.mkdir(parents=True, exist_ok=True)
        TRACE.write_text(json.dumps({"seed": SEED, "trace": world.trace}))
    except OSError:
        pass
    return json.dumps(out)


@mcp.tool()
def list_services() -> str:
    """List every service and its tier. Cost 1 tick."""
    return _call("list_services")


@mcp.tool()
def get_alerts() -> str:
    """Current alerts (user-facing SLO breaches, saturation, informational). Cost 1 tick."""
    return _call("get_alerts")


@mcp.tool()
def describe_service(service: str) -> str:
    """Dependencies, dependents, owner and current version of a service. Cost 1 tick."""
    return _call("describe_service", service=service)


@mcp.tool()
def get_metrics(service: str) -> str:
    """Error rate, latency, cpu, memory, connection pool, throughput. Cost 1 tick."""
    return _call("get_metrics", service=service)


@mcp.tool()
def get_logs(service: str, n: int = 10) -> str:
    """Last n log lines of a service. Cost 1 tick."""
    return _call("get_logs", service=service, n=n)


@mcp.tool()
def get_deploys(service: str) -> str:
    """Recent deploys of a service. Cost 1 tick."""
    return _call("get_deploys", service=service)


@mcp.tool()
def get_config(service: str) -> str:
    """Current config and recent config changes of a service. Cost 1 tick."""
    return _call("get_config", service=service)


@mcp.tool()
def restart(service: str) -> str:
    """Restart a service. Cost 3 ticks. Effects are not reported; verify with metrics/alerts."""
    return _call("restart", service=service)


@mcp.tool()
def rollback(service: str) -> str:
    """Roll a service back to its previous version. Cost 3 ticks."""
    return _call("rollback", service=service)


@mcp.tool()
def set_config(service: str, key: str, value: str) -> str:
    """Set a config key on a service. Cost 3 ticks."""
    return _call("set_config", service=service, key=key, value=value)


@mcp.tool()
def scale(service: str) -> str:
    """Add capacity (memory / connections) to a service. Cost 3 ticks."""
    return _call("scale", service=service)


@mcp.tool()
def wait(ticks: int = 1) -> str:
    """Let time pass (1-10 ticks) so you can observe the effect of changes."""
    return _call("wait", ticks=ticks)


@mcp.tool()
def submit(findings: list[dict]) -> str:
    """End the shift. findings = up to 3 {"service": ..., "kind": ...} root causes you found and fixed.
    kind is one of bad_deploy, bad_config, resource_exhaustion, stuck_process."""
    return _call("submit", findings=findings)


@mcp.tool()
def status() -> str:
    """Free: current tick and remaining budget."""
    return json.dumps({"tick": world.tick, "budget_left": BUDGET - world.tick, "episode_over": world.done})


if __name__ == "__main__":
    mcp.run()
