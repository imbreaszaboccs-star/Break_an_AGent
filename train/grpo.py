"""Online GRPO against the OnCall environment (LoRA, group-relative advantages, vLLM sampling).

Per step: pick K train scenarios -> sample N rollouts each from the policy served by vLLM (oncall.agent.run_agent,
temperature > 0) -> reward = env score -> advantage = (r - mean) / (std + eps) within the scenario group ->
policy-gradient loss on assistant tokens -> save adapter -> hot-load it into vLLM.

    VLLM_ALLOW_RUNTIME_LORA_UPDATING=True vllm serve google/gemma-3-4b-it --enable-lora \
        --lora-modules gemma-grpo=adapters/gemma-sft --chat-template train/gemma_tools.jinja \
        --enable-auto-tool-choice --tool-call-parser pythonic --max-model-len 65536 --gpu-memory-utilization 0.45
    python train/grpo.py --adapter adapters/gemma-sft --out adapters/gemma-grpo --steps 20

# ponytail: UNTESTED ON GPU end to end (advantages and message conversion are unit-testable plain python).
# Ceiling: vLLM and the trainer share ONE GPU, ~40k-token episodes, one gradient step per batch (strictly on-policy,
# so no ratio/clipping), 4B realistic, 12B not. Tokens are re-tokenized from the transcript, not the sampled ids.
"""
import argparse
import json
import random
import statistics
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from oncall import logsink
from oncall.agent import resolve_provider, run_agent, tool_schemas
from oncall.scenarios import suite


def advantages(rewards, eps=1e-4):
    m, s = statistics.mean(rewards), statistics.pstdev(rewards)
    return [(r - m) / (s + eps) for r in rewards]


def to_train_messages(messages):
    """Transcript (OpenAI JSON-string arguments) -> dict arguments for the chat template; None if any call is malformed."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                try:
                    args = json.loads(c["function"]["arguments"])
                except ValueError:
                    return None
                if not isinstance(args, dict):
                    return None
                calls.append({**c, "function": {"name": c["function"]["name"], "arguments": args}})
            m["tool_calls"] = calls
        out.append(m)
    return out


def push_adapter(vllm_url, name, path, key=None):
    """Hot-load `path` as LoRA `name` (server needs VLLM_ALLOW_RUNTIME_LORA_UPDATING=True and must see `path`)."""
    root = vllm_url.rstrip("/").removesuffix("/v1")
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
    for ep, body in (("unload_lora_adapter", {"lora_name": name}),
                     ("load_lora_adapter", {"lora_name": name, "lora_path": str(Path(path).resolve())})):
        try:
            urllib.request.urlopen(urllib.request.Request(f"{root}/v1/{ep}", json.dumps(body).encode(), headers), timeout=120).read()
        except Exception as e:
            if ep == "load_lora_adapter":       # unloading before the first load may fail, that is fine
                raise RuntimeError(f"vLLM refused {ep}: {e}") from e


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", default="google/gemma-3-4b-it")
    p.add_argument("--adapter", help="start from this LoRA (e.g. the SFT adapter); vLLM must serve the same one as --lora-name")
    p.add_argument("--out", required=True)
    p.add_argument("--vllm-url", help="default: $VLLM_BASE_URL or http://localhost:8000/v1")
    p.add_argument("--lora-name", default="gemma-grpo", help="name the adapter has in vLLM (sent as `model`)")
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--scenarios-per-step", type=int, default=4)
    p.add_argument("--rollouts", type=int, default=8, help="N samples per scenario (group size)")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--max-turns", type=int, default=150)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--lr", type=float, default=1e-5)
    p.add_argument("--kl-coef", type=float, default=0.0, help=">0: k3 KL to the base model (adapter disabled)")
    p.add_argument("--max-len", type=int, default=49152)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)

    import torch
    from sft import assistant_logprobs, encode, load_model      # train/ is sys.path[0] when run as a script
    base_url, key = resolve_provider("vllm", a.vllm_url)
    rng = random.Random(a.seed)
    tok, model = load_model(a.model, a.adapter)
    params = [q for q in model.parameters() if q.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    pool, out, tools = suite("train"), Path(a.out), tool_schemas()       # only the train split, never eval suites
    out.mkdir(parents=True, exist_ok=True)

    for step in range(1, a.steps + 1):
        scs = rng.sample(pool, a.scenarios_per_step)
        jobs = [(sc, i, rng.randrange(2 ** 31)) for sc in scs for i in range(a.rollouts)]
        with ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(lambda j: run_agent(j[0], base_url=base_url, model=a.lora_name, api_key=key,
                                                  temperature=a.temperature, max_turns=a.max_turns, seed=j[2]), jobs))
        for (sc, i, _), (env, bd, tr) in zip(jobs, res):
            logsink.write_episode(out / "rollouts", f"step{step:04d}-{sc.id}-{i}", env, bd)
        rewards = [bd["score"] for _, bd, _ in res]
        batch = []      # (messages, advantage)
        for k in range(len(scs)):
            grp = range(k * a.rollouts, (k + 1) * a.rollouts)
            adv = advantages([rewards[j] for j in grp])
            if max(abs(x) for x in adv) < 1e-3:
                continue                      # all rollouts scored the same: no learning signal
            for j, x in zip(grp, adv):
                msgs = to_train_messages(res[j][2]["messages"])
                if msgs and not res[j][2]["stop"].startswith("api_error"):
                    batch.append((msgs, x))
        loss_sum = 0.0
        model.train()
        for msgs, adv in batch:
            ids, mask = encode(tok, msgs, tools, a.max_len)
            lp = assistant_logprobs(model, ids, mask, torch)
            if lp is None:
                continue
            loss = -adv * lp.mean()
            if a.kl_coef > 0:
                with torch.no_grad(), model.disable_adapter():
                    ref = assistant_logprobs(model, ids, mask, torch)
                d = ref - lp
                loss = loss + a.kl_coef * (torch.exp(d) - d - 1).mean()
            (loss / len(batch)).backward()
            loss_sum += loss.item()
        if batch:
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            model.save_pretrained(out / f"step{step:04d}")
            push_adapter(base_url, a.lora_name, out / f"step{step:04d}", key)
        rec = {"step": step, "reward_mean": statistics.mean(rewards), "reward_max": max(rewards), "trained_on": len(batch),
               "loss": loss_sum / max(len(batch), 1), "stops": sorted({tr["stop"].split(":")[0] for _, _, tr in res})}
        print(json.dumps(rec), flush=True)
        with (out / "log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    model.save_pretrained(out / "final")
    print(f"final adapter: {out / 'final'}")


if __name__ == "__main__":
    main()
