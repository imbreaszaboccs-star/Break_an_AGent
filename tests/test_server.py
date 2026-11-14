import asyncio
import hashlib
import json
import socket
import threading
import time

import pytest
import uvicorn
from mcp.shared.memory import create_connected_server_and_client_session
from starlette.testclient import TestClient

from oncall import server
from oncall.client import http_call
from oncall.policies import POLICIES
from oncall.scenarios import Scenario
from oncall.sim import Env, TOOLS

TOKEN = "s3cret"
SHA = hashlib.sha256(TOKEN.encode()).hexdigest()
SC = Scenario(1003, "medium")
SEQ = [("get_status", {}), ("get_topology", {}), ("wait", {"minutes": 10}),
       ("resolve_incident", {"root_causes": [], "summary": "x"})]


def local_score():
    env = Env(SC)
    for tool, args in SEQ:
        env.call(tool, **args)
    return env.finalize()["score"]


async def run_seq(mcp):
    async with create_connected_server_and_client_session(mcp) as s:
        return [json.loads((await s.call_tool(t, a)).content[0].text) for t, a in SEQ]


def test_tool_list_is_exactly_the_agent_tools():
    mcp = server.build_server(SC, SHA)

    async def go():
        async with create_connected_server_and_client_session(mcp) as s:
            return {t.name for t in (await s.list_tools()).tools}
    assert asyncio.run(go()) == set(TOOLS)


def test_admin_finalize_auth_and_score():
    mcp = server.build_server(SC, SHA)
    res = asyncio.run(run_seq(mcp))
    assert all(r["ok"] for r in res)
    with TestClient(mcp.streamable_http_app()) as c:
        assert c.post("/admin/finalize").status_code == 401
        assert c.post("/admin/finalize", headers={"Authorization": "Bearer nope"}).status_code == 401
        assert c.post("/admin/finalize", headers={"Authorization": SHA}).status_code == 401
        r = c.post("/admin/finalize", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200
        assert r.json()["score"] == local_score()
        assert c.post("/admin/finalize", headers={"Authorization": f"Bearer {TOKEN}"}).json() == r.json()  # idempotent


def test_missing_token_hash_always_401():
    with TestClient(server.build_server(SC, None).streamable_http_app()) as c:
        assert c.post("/admin/finalize", headers={"Authorization": "Bearer "}).status_code == 401
        assert c.post("/admin/finalize", headers={"Authorization": "Bearer x"}).status_code == 401


def test_schema_validation_rejects_bad_enum():
    mcp = server.build_server(SC, SHA)

    async def go():
        async with create_connected_server_and_client_session(mcp) as s:
            r = await s.call_tool("get_logs", {"service": "x", "level": "LOUD"})
            r2 = await s.call_tool("set_circuit_breaker", {"service": "a", "dep": "b", "mode": "maybe"})
            return r, r2
    r, r2 = asyncio.run(go())
    assert r.isError and r2.isError
    assert mcp.env.n_calls == 0       # rejected before reaching the Env


def test_concurrent_calls_are_serialized():
    mcp = server.build_server(SC, SHA)

    async def go():
        async with create_connected_server_and_client_session(mcp) as s:
            return await asyncio.gather(*[s.call_tool("get_status", {}) for _ in range(12)])
    res = asyncio.run(go())
    assert all(not r.isError and json.loads(r.content[0].text)["ok"] for r in res)
    log = mcp.env.log
    assert [e["i"] for e in log] == list(range(1, 13))
    assert all(a["t_after"] == b["t_before"] for a, b in zip(log, log[1:]))


@pytest.fixture
def live_url():
    mcp = server.build_server(Scenario(1000, "medium"), SHA)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(), host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    while not srv.started:
        time.sleep(.05)
    yield f"http://127.0.0.1:{port}", mcp
    srv.should_exit = True
    th.join(5)


def test_http_client_reference_matches_local(live_url):
    base, mcp = live_url
    call = http_call(base + "/mcp")
    POLICIES["reference"](call)
    from oncall.cli import fetch_score
    over_http = fetch_score(base + "/admin/finalize", TOKEN)
    env = Env(Scenario(1000, "medium"))
    POLICIES["reference"](env.call)
    assert over_http["score"] == pytest.approx(env.finalize()["score"], abs=1e-9)
    assert not call("get_logs", service="x", level="LOUD")["ok"]
