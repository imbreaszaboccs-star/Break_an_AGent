"""LoRA SFT of Gemma on OnCall tool-call trajectories (loss on assistant tokens only).

    python train/sft.py --data sft.jsonl --out adapters/gemma-sft [--model google/gemma-3-4b-it]

Plain transformers + peft + a 30-line loop (no trl: its tool-call/assistant-mask handling varies by version).
torch/transformers/peft are imported lazily so `--help` works without them.
"""
import argparse
import json
import math
import random
import re
from pathlib import Path

TEMPLATE = Path(__file__).with_name("gemma_tools.jinja")
LORA_TARGETS = r"^(?!.*vision).*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)$"   # language model only
ASSISTANT = re.compile(r"<start_of_turn>model\n(.*?<end_of_turn>)", re.S)


def encode(tok, messages, tools, max_len):
    """-> (input_ids, assistant_mask) as python lists. Assistant tokens = text after `<start_of_turn>model\n`
    up to and including `<end_of_turn>`; offsets from the fast tokenizer find them, so no per-turn re-rendering.
    Over-long episodes are truncated at the end (a prefix of an episode is still a valid episode)."""
    text = tok.apply_chat_template(messages, tools=tools, tokenize=False, chat_template=TEMPLATE.read_text(encoding="utf-8"))
    spans = [m.span(1) for m in ASSISTANT.finditer(text)]
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)    # template already starts with <bos>
    ids, mask, k = enc["input_ids"], [], 0
    for s, e in enc["offset_mapping"]:
        while k < len(spans) and spans[k][1] <= s:
            k += 1
        mask.append(int(k < len(spans) and spans[k][0] <= s < spans[k][1]))
    return ids[:max_len], mask[:max_len]


def assistant_logprobs(model, ids, mask, torch):
    """Per-token log-probs of the assistant tokens, shape [n_assistant_tokens] (with grad if the model is in train mode).
    Logits are computed only at the positions that predict an assistant token: Gemma's 262k vocab x 40k tokens
    would not fit otherwise. # ponytail: relies on `logits_to_keep=<index tensor>` support (transformers >= 4.50), UNVERIFIED on GPU.
    """
    dev = next(model.parameters()).device
    x = torch.tensor([ids], device=dev)
    pos = torch.tensor([i for i in range(1, len(ids)) if mask[i]], device=dev)       # token i is predicted at i-1
    if len(pos) == 0:
        return None
    logits = model(input_ids=x, logits_to_keep=pos - 1).logits[0].float()
    return torch.log_softmax(logits, -1).gather(-1, x[0, pos][:, None])[:, 0]


def load_model(model_id, adapter=None, trainable=True, attn="sdpa"):
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    # ponytail: AutoModelForCausalLM on multimodal Gemma 3 checkpoints (4b/12b) maps to the conditional-generation class; UNVERIFIED.
    model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.bfloat16, attn_implementation=attn, device_map={"": 0})
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    if adapter:
        model = PeftModel.from_pretrained(model, adapter, is_trainable=trainable)
    else:
        model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, target_modules=LORA_TARGETS, task_type="CAUSAL_LM"))
    model.config.use_cache = False
    return tok, model


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data", required=True, help="JSONL from build_dataset.py")
    p.add_argument("--out", required=True, help="adapter output dir")
    p.add_argument("--model", default="google/gemma-3-4b-it", help="e.g. google/gemma-3-12b-it (needs >= 80 GB, UNVERIFIED)")
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--grad-accum", type=int, default=16)
    p.add_argument("--max-len", type=int, default=49152, help="reference trajectories are ~40k tokens")
    p.add_argument("--attn", default="sdpa", help="sdpa | flash_attention_2 | eager (eager is O(n^2) memory: do not)")
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args(argv)

    import torch
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    tok, model = load_model(a.model, attn=a.attn)
    rows = [json.loads(l) for l in Path(a.data).read_text(encoding="utf-8").splitlines() if l.strip()]
    data = [encode(tok, r["messages"], r["tools"], a.max_len) for r in rows]
    print(f"{len(data)} examples, tokens/example ~{sum(len(d[0]) for d in data) // max(len(data), 1)}, "
          f"trained tokens/example ~{sum(sum(d[1]) for d in data) // max(len(data), 1)}", flush=True)
    params = [q for q in model.parameters() if q.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    total = a.epochs * len(data) // a.grad_accum or 1
    warm = max(1, total // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * 0.5 * (1 + math.cos(math.pi * min(s, total) / total)))
    model.train()
    step = 0
    for ep in range(a.epochs):
        random.shuffle(data)
        run = 0.0
        for i, (ids, mask) in enumerate(data, 1):
            lp = assistant_logprobs(model, ids, mask, torch)
            if lp is None:
                continue
            loss = -lp.mean()                       # per-example token mean; examples weighted equally
            (loss / a.grad_accum).backward()
            run += loss.item()
            if i % a.grad_accum == 0 or i == len(data):
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
                step += 1
                print(f"epoch {ep + 1} step {step}/{total} loss {run / a.grad_accum:.4f} lr {sched.get_last_lr()[0]:.2e}", flush=True)
                run = 0.0
    model.save_pretrained(a.out)
    (Path(a.out) / "oncall_train.json").write_text(json.dumps({"base_model": a.model, "data": a.data, "epochs": a.epochs, "lr": a.lr,
                                                                "examples": len(data), "template": TEMPLATE.name}), encoding="utf-8")
    print(f"adapter saved to {a.out}")


if __name__ == "__main__":
    main()
