import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from oncall import agent
from oncall.scenarios import Scenario
from oncall.server import build_server
from oncall.sim import Env

SC = Scenario(1003, "medium")
SEQ = [("get_status", {}), ("get_topology", {}), ("resolve_incident", {"root_causes": [], "summary": "x"})]


def tc(name, args, i=0):
    a = args if isinstance(args, str) else json.dumps(args)
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": a}}


def msg(*calls, content=None):
    return {"role": "assistant", "content": content, "tool_calls": list(calls)} if calls else {"role": "assistant", "content": content or "hmm"}


class Fake:
    """OpenAI-compatible fake: `script(n_request, body) -> assistant message` (or an int = HTTP error code)."""

    def __init__(self, script):
        self.script, self.requests, self.auth = script, [], []
        fake = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                fake.auth.append(self.headers.get("Authorization"))
                out = fake.script(len(fake.requests) - 1, body)
                if isinstance(out, int):
                    self.send_response(out)
                    self.send_header("Retry-After", "0")
                    self.end_headers()
                    return
                data = json.dumps({"choices": [{"message": out}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def fake():
    made = []

    def make(script):
        made.append(Fake(script))
        return made[-1]
    yield make
    for f in made:
        f.close()


def scripted(seq):
    return lambda n, body: msg(tc(*seq[n], i=n)) if n < len(seq) else msg(content="done")


def local_score(seq):
    env = Env(SC)
    for tool, args in seq:
        env.call(tool, **args)
    return env.finalize()["score"]


def test_tool_schemas_match_mcp_tools():
    names = [t.name for t in asyncio.run(build_server(SC).list_tools())]
    tools = agent.tool_schemas()
    assert [t["function"]["name"] for t in tools] == names
    jsonschema = pytest.importorskip("jsonschema")
    for t in tools:
        assert t["type"] == "function" and t["function"]["description"]
        params = t["function"]["parameters"]
        assert params["type"] == "object" and isinstance(params["properties"], dict)
        jsonschema.Draft202012Validator.check_schema(params)
        assert "$ref" not in json.dumps(params) and "$defs" not in json.dumps(params)
    assert json.dumps(tools)        # serialisable


def test_scripted_episode_scores_like_local(fake):
    f = fake(scripted(SEQ))
    env, bd, tr = agent.run_agent(SC, base_url=f.url, model="m", api_key="sekret")
    assert tr["stop"] == "resolved" and tr["turns"] == 3 and env.done
    assert [e["tool"] for e in env.log] == [t for t, _ in SEQ]
    assert bd["score"] == pytest.approx(local_score(SEQ))
    roles = [m["role"] for m in tr["messages"]]
    assert roles[:2] == ["system", "user"] and roles.count("tool") == 3
    assert f.requests[0]["tools"] == agent.tool_schemas() and f.requests[0]["model"] == "m"
    assert set(f.auth) == {"Bearer sekret"}
    assert tr["usage"] == {"prompt": 30, "completion": 6}
    assert "sekret" not in json.dumps(tr)


def test_malformed_arguments_do_not_crash(fake):
    script = [msg(tc("get_status", "{not json", 0), tc("get_events", "[1, 2]", 1), tc("no_such_tool", {}, 2),
                  tc("get_logs", {"service": 5}, 3)),
              msg(tc("resolve_incident", {"root_causes": []}, 4))]
    f = fake(lambda n, body: script[n] if n < len(script) else msg(content="x"))
    env, bd, tr = agent.run_agent(SC, base_url=f.url, model="m")
    tool_msgs = [json.loads(m["content"]) for m in tr["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 5 and not any(m["ok"] for m in tool_msgs[:4])
    assert "malformed" in tool_msgs[0]["error"] and "malformed" in tool_msgs[1]["error"]
    # the two JSON-level failures never reached the env; unknown tool and bad types did (and cost a minute each)
    assert [e["tool"] for e in env.log] == ["no_such_tool", "get_logs", "resolve_incident"]
    assert tr["stop"] == "resolved" and 0 <= bd["score"] <= 1


def test_no_tool_call_nudges_once_then_stops(fake):
    f = fake(lambda n, body: msg(content="I think it is fine"))
    env, bd, tr = agent.run_agent(SC, base_url=f.url, model="m")
    assert tr["stop"] == "no_tool_call" and len(f.requests) == 2 and env.n_calls == 0
    assert tr["messages"][-2]["role"] == "user" and "did not call a tool" in tr["messages"][-2]["content"]
    assert bd["score"] < 0.5        # nothing done


def test_retries_on_429_and_reports_api_errors(fake):
    f = fake(lambda n, body: 429 if n == 0 else msg(tc("resolve_incident", {"root_causes": []})))
    _, _, tr = agent.run_agent(SC, base_url=f.url, model="m")
    assert tr["stop"] == "resolved" and len(f.requests) == 2
    f = fake(lambda n, body: 401)
    _, bd, tr = agent.run_agent(SC, base_url=f.url, model="m")
    assert tr["stop"].startswith("api_error:401") and bd is not None and len(f.requests) == 1


def test_max_turns(fake):
    f = fake(lambda n, body: msg(tc("get_status", {}, n)))
    env, _, tr = agent.run_agent(SC, base_url=f.url, model="m", max_turns=3)
    assert tr["stop"] == "max_turns" and env.n_calls == 3


def test_missing_key_exits_2(monkeypatch, capsys):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        agent.resolve_provider("gemini")
    assert e.value.code == 2 and "GEMINI_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert agent.resolve_provider("gemini")[1] == "k"
    monkeypatch.setenv("VLLM_BASE_URL", "http://h:1/v1")
    assert agent.resolve_provider("vllm") == ("http://h:1/v1", None)
    with pytest.raises(SystemExit) as e:
        agent.resolve_provider("openai-compatible")
    assert e.value.code == 2


def test_cli_output_shape_and_logs(fake, tmp_path, monkeypatch):
    f = fake(lambda n, body: msg(tc("resolve_incident", {"root_causes": []}, n)))
    monkeypatch.setattr(agent, "suite", lambda name: [SC, Scenario(1004, "medium")])
    out = tmp_path / "res.json"
    agent.main(["--provider", "openai-compatible", "--base-url", f.url, "--model", "m/x", "--suite", "dev",
                "--runs", "2", "--out", str(out), "--run-dir", str(tmp_path / "runs")])
    res = json.loads(out.read_text())
    name = "agent:openai-compatible:m/x"
    assert set(res) == {"suite", "scenarios", "policies"} and list(res["policies"]) == [name]
    assert len(res["policies"][name]) == 4 and all("score" in b and "tags" in b for b in res["policies"][name])
    files = list((tmp_path / "runs").glob("*/*"))
    assert len([p for p in files if p.suffix == ".jsonl"]) == 4
    msgs = json.loads(next(p for p in files if p.name.endswith(".messages.json")).read_text())
    assert msgs["messages"][0]["role"] == "system"


def test_auth_error_aborts_suite_early(fake, monkeypatch):
    f = fake(lambda n, body: 401)
    monkeypatch.setattr(agent, "suite", lambda name: [SC, Scenario(1004, "medium"), Scenario(1005, "medium")])
    with pytest.raises(SystemExit, match="401"):
        agent.run_suite("openai-compatible", "m", "dev", 1, f.url, None, 0.0, 10, None)
    assert len(f.requests) == 1


def test_rate_limit_outage_is_excluded_not_scored_and_resume_fills_it(monkeypatch, tmp_path):
    """An API outage must never be scored as an agent failure; --resume reruns only what is missing."""
    monkeypatch.setattr(agent.time, "sleep", lambda s: None)
    monkeypatch.setattr(agent, "suite", lambda name: [SC, Scenario(1004, "medium")])
    down, fakes_seen = {"on": True}, []
    calls = {"n": 0}

    def run_agent_spy(sc, **kw):
        fakes_seen.append(sc.seed)
        if down["on"] and sc.seed == 1004:
            return None, None, {"stop": "api_error:429:HTTP 429: Too Many Requests", "turns": 0, "messages": []}
        calls["n"] += 1
        env = Env(sc)
        env.call("resolve_incident", root_causes=[], summary="")
        return env, env.finalize(), {"stop": "resolved", "turns": 1, "messages": [{"role": "system", "content": ""}]}
    monkeypatch.setattr(agent, "run_agent", run_agent_spy)
    monkeypatch.setattr(agent.logsink, "write_episode", lambda d, ep, env, bd: (
        __import__("pathlib").Path(d).mkdir(parents=True, exist_ok=True),
        (__import__("pathlib").Path(d) / f"{ep}.jsonl").write_text(json.dumps({"type": "final", "breakdown": bd}) + "\n")) if bd else None)
    run_dir = tmp_path / "r"
    res = agent.run_suite("openai-compatible", "m", "dev", 1, "http://unused", None, 0.0, 10, None, run_dir=run_dir, log=lambda *_: None)
    name = "agent:openai-compatible:m"
    assert [b["scenario"] for b in res["policies"][name]] == [SC.id]       # outage excluded, not scored 0
    assert len(res["excluded"]) == 1 and res["excluded"][0].startswith("api_error:429")
    assert fakes_seen.count(1004) == agent.EPISODE_RETRIES + 1              # episode restarted before giving up
    down["on"], calls["n"] = False, 0
    res = agent.run_suite("openai-compatible", "m", "dev", 1, "http://unused", None, 0.0, 10, None, run_dir=run_dir, log=lambda *_: None)
    assert sorted(b["scenario"] for b in res["policies"][name]) == sorted([SC.id, Scenario(1004, "medium").id])
    assert calls["n"] == 1 and "excluded" not in res                        # only the missing episode was rerun
    assert all(b["run"] == 1 for b in res["policies"][name])
