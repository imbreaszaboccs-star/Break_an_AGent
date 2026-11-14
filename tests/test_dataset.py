import ast
import json
import sys
from pathlib import Path

import pytest

from oncall import logsink
from oncall.policies import run_env
from oncall.scenarios import Scenario, suite

TRAIN = Path(__file__).resolve().parents[1] / "train"
sys.path.insert(0, str(TRAIN))
import build_dataset as bd  # noqa: E402

N = 3


def test_reference_dataset_format_and_filter(tmp_path):
    out = tmp_path / "sft.jsonl"
    bd.main(["--generate-reference", "--n", str(N), "--out", str(out)])
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == N
    for r in rows:
        m = r["messages"]
        assert [x["role"] for x in m[:2]] == ["system", "user"] and r["tools"]
        assert r["meta"]["score"] >= 0.8 and r["meta"]["seed"] >= 10000
        calls = [x for x in m if x["role"] == "assistant"]
        tools = [x for x in m if x["role"] == "tool"]
        assert len(calls) == len(tools) == r["meta"]["n_calls"] > 5
        for c, t in zip(calls, tools):
            tc = c["tool_calls"][0]
            assert tc["function"]["name"] in {x["function"]["name"] for x in r["tools"]}
            assert isinstance(tc["function"]["arguments"], dict) and tc["id"] == t["tool_call_id"]
            assert json.loads(t["content"])["t"] >= 0
        assert m[-2]["tool_calls"][0]["function"]["name"] == "resolve_incident"
    # a min-score above anything reachable drops everything
    out2 = tmp_path / "none.jsonl"
    bd.main(["--generate-reference", "--n", "2", "--min-score", "1.01", "--out", str(out2)])
    assert out2.read_text() == ""


def test_from_run_dir_dedupe_and_family_exclusion(tmp_path):
    sc = suite("train")[0]
    env = run_env("reference", sc)
    b = env.finalize()
    logsink.write_episode(tmp_path, "a", env, b)
    logsink.write_episode(tmp_path, "b", env, b)       # identical trajectory -> duplicate
    eps = list(bd.episodes_from_runs([tmp_path]))
    assert len(eps) == 2
    rows, drop = bd.build(eps)
    assert len(rows) == 1 and drop["duplicate"] == 1
    fam = bd.family(sc)
    assert fam != "?"
    rows, drop = bd.build(bd.episodes_from_runs([tmp_path]), exclude={fam})
    assert rows == [] and drop["excluded_family"] == 2


def test_llm_transcript_keeps_reasoning(tmp_path):
    """A sibling <episode>.messages.json (oncall.agent) wins over the rebuilt tool log, so model text survives."""
    sc = suite("train")[1]
    env = run_env("reference", sc)
    logsink.write_episode(tmp_path, "llm", env, env.finalize())
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "go"},
            {"role": "assistant", "content": "DB conns are saturated, check retries first.",
             "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "get_status", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c0", "content": "{}"}]
    (tmp_path / "llm.messages.json").write_text(json.dumps({"messages": msgs}), encoding="utf-8")
    rows, _ = bd.build(bd.episodes_from_runs([tmp_path]))
    m = rows[0]["messages"]
    assert m[2]["content"].startswith("DB conns") and m[2]["tool_calls"][0]["function"]["arguments"] == {}
    msgs[2]["tool_calls"][0]["function"]["arguments"] = "{broken"
    (tmp_path / "llm.messages.json").write_text(json.dumps({"messages": msgs}), encoding="utf-8")
    rows, _ = bd.build(bd.episodes_from_runs([tmp_path]))
    assert rows[0]["messages"][2]["content"] == ""      # unparsable transcript -> fall back to the tool log


def test_family_fallbacks():
    class S:
        id = "eas-f12-1"
    assert bd.family(S()) == "F12"
    S.family = "f14"
    assert bd.family(S()) == "F14"
    assert bd.family(object()) == "?"


def test_split_leakage_guard(tmp_path):
    bad = bd.forbidden_seeds()
    assert {1000, 2000} <= bad and not bad & {x.seed for x in suite("train")}
    sc = Scenario(2000, "easy")      # a judge-fast seed
    env = run_env("reference", sc)
    logsink.write_episode(tmp_path, "leak", env, env.finalize())
    with pytest.raises(SystemExit, match="evaluation suite"):
        bd.main([str(tmp_path), "--out", str(tmp_path / "x.jsonl")])
    with pytest.raises(SystemExit):        # salted scenario (heldout style) is refused as well
        bd.check_leak(Scenario(10050, "easy", "somesalt"), bad)


def test_chat_template_roundtrip():
    jinja2 = pytest.importorskip("jinja2")
    tpl = jinja2.Environment().from_string((TRAIN / "gemma_tools.jinja").read_text(encoding="utf-8"))
    args = {"root_causes": [{"service": "a", "fault_class": "bad_deploy"}], "summary": "it's \"x\"", "f": True, "n": None, "x": 1.5}
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "1", "type": "function", "function": {"name": "get_status", "arguments": {}}},
                {"id": "2", "type": "function", "function": {"name": "resolve_incident", "arguments": args}}]},
            {"role": "tool", "tool_call_id": "1", "content": "{}"}, {"role": "tool", "tool_call_id": "2", "content": "{}"}]
    text = tpl.render(messages=msgs, tools=[{"type": "function", "function": {"name": "get_status"}}],
                      bos_token="<bos>", add_generation_prompt=True)
    assert text.startswith("<bos><start_of_turn>user\nS") and text.endswith("<start_of_turn>model\n")
    assert text.count("<start_of_turn>user") == 2          # parallel tool results share one user turn
    call = text.split("<start_of_turn>model\n")[1].split("<end_of_turn>")[0]
    parsed = ast.parse(call, mode="eval").body             # what vLLM's pythonic parser does
    assert [c.func.id for c in parsed.elts] == ["get_status", "resolve_incident"]
    got = {k.arg: ast.literal_eval(k.value) for k in parsed.elts[1].keywords}
    assert got == args


def test_assistant_mask_covers_only_model_turns():
    jinja2 = pytest.importorskip("jinja2")
    import re
    import sft

    class FakeTok:      # whitespace "tokenizer" with offsets, enough to exercise encode()
        def apply_chat_template(self, messages, tools, tokenize, chat_template):
            return jinja2.Environment().from_string(chat_template).render(messages=messages, tools=tools, bos_token="<bos>")

        def __call__(self, text, add_special_tokens, return_offsets_mapping):
            ms = list(re.finditer(r"\S+\s*", text))
            return {"input_ids": list(range(len(ms))), "offset_mapping": [m.span() for m in ms]}

    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "get_status", "arguments": {}}}]},
            {"role": "tool", "tool_call_id": "1", "content": "RESULT"}]
    ids, mask = sft.encode(FakeTok(), msgs, None, 10 ** 6)
    text = FakeTok().apply_chat_template(msgs, None, False, (TRAIN / "gemma_tools.jinja").read_text(encoding="utf-8"))
    pieces = [text[m.start():m.end()] for m in re.finditer(r"\S+\s*", text)]
    trained = "".join(p for p, m in zip(pieces, mask) if m)
    assert trained == "[get_status()]<end_of_turn>\n"
    assert sft.encode(FakeTok(), msgs, None, 5)[0] == list(range(5))      # truncation keeps the prefix


def test_grpo_helpers_without_torch():
    import grpo
    adv = grpo.advantages([1.0, 0.0, 0.5, 0.5])
    assert abs(sum(adv)) < 1e-9 and adv[0] > 0 > adv[1]
    assert all(abs(x) < 1e-6 for x in grpo.advantages([0.3, 0.3, 0.3]))        # no signal -> zero advantage
    ok = [{"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "wait", "arguments": '{"minutes": 5}'}}]}]
    assert grpo.to_train_messages(ok)[0]["tool_calls"][0]["function"]["arguments"] == {"minutes": 5}
    bad = [{"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": "wait", "arguments": "{oops"}}]}]
    assert grpo.to_train_messages(bad) is None
