# Training Gemma on OnCall (Verda runbook)

Goal (DESIGN.md section 11): a small Gemma gets better at the incident-response tool-use task after SFT (and optionally GRPO)
on the `train` split, measured on `heldout` seeds and on held-out fault families. Everything here is an *extra*: the
environment, scoring and `make judge` never depend on it.

Files: `build_dataset.py` (rollouts -> chat JSONL), `sft.py` (LoRA SFT), `grpo.py` (online GRPO), `gemma_tools.jinja`
(chat template with tool calls, see below). Agent runner: `python -m oncall.agent`. Analysis SQL: `analysis/`.

## Why a custom chat template

Gemma 3 ships no tool-call format. `gemma_tools.jinja` is ours: tools are listed in the first user turn, the model answers
with a python list `[get_status(), get_logs(service="api", limit=20)]`, tool results come back as user turns wrapped in
`<tool_response>`. The same file is used for SFT rendering, GRPO and vLLM serving (`--chat-template`), so train and
inference prompts are identical. vLLM then parses the list with `--tool-call-parser pythonic`.
**UNVERIFIED**: vLLM's docs list no Gemma 3 parser/template pair (only `functiongemma` for the 270M FunctionGemma model);
`pythonic` + our template is the intended route but was not run. Check `vllm serve --help` / docs of your vLLM version
first. Unit tests only check that the rendered call round-trips through python's `ast` (what the pythonic parser does).

## 0. Dependencies

Add to `pyproject.toml` (not done automatically):

```toml
[dependency-groups]
train = ["torch>=2.4", "transformers>=4.50", "peft>=0.13", "accelerate>=1.0", "jinja2>=3.1", "huggingface_hub"]
```

vLLM pins its own torch: install it in a **separate venv** (below), not in the project env.
`export HF_TOKEN=...` and accept the Gemma license on Hugging Face first (gated repo).

## 1. Provision (Verda)

1. Create a project/instance with **1x 80 GB GPU** (A100 80GB or H100), Ubuntu + CUDA image, an SSH key, >= 200 GB disk.
   (4B fits; 12B needs more headroom and is untested here.) Console specifics: UNVERIFIED, use Verda's own docs.
2. `ssh` in, then:
   ```bash
   git clone <repo> && cd Break_the_agent
   curl -LsSf https://astral.sh/uv/install.sh | sh
   uv sync --group train
   uv venv .venv-vllm && uv pip install --python .venv-vllm vllm
   ```
3. Stop the instance when idle; keep adapters and `runs/` on a persistent volume or `rsync` them off.

## 2. Serve the base model

```bash
VLLM_ALLOW_RUNTIME_LORA_UPDATING=True .venv-vllm/bin/vllm serve google/gemma-3-4b-it \
  --enable-lora --max-lora-rank 16 --max-model-len 65536 \
  --chat-template train/gemma_tools.jinja --enable-auto-tool-choice --tool-call-parser pythonic \
  --gpu-memory-utilization 0.45
export VLLM_BASE_URL=http://localhost:8000/v1
```
Episodes are ~40k tokens (full tool outputs), hence `--max-model-len 65536`. `--gpu-memory-utilization 0.45` leaves room
for the trainer in the GRPO step; use 0.9 when only serving. For 12B use `google/gemma-3-12b-it` and a smaller utilization/context.

## 3. Rollouts on the train split

```bash
# reference runbook rollouts (no LLM, seconds): done inside build_dataset (step 4)
# optional: rejection-sampled Gemma base rollouts, 4 samples per train scenario
uv run python -m oncall.agent --provider vllm --model google/gemma-3-4b-it --suite train --runs 4 \
  --temperature 0.8 --seed 1 --workers 8 --run-dir runs/train-gemma --out results/train-gemma.json
# optional: frontier rollouts (e.g. Gemini) on the train split, same command with --provider gemini --model <id>
```
Rollout JSONL lands in `runs/<stamp>/`, `<episode>.messages.json` holds the raw LLM messages. If
`ONCALL_CLICKHOUSE_URL` is set the rows also go to ClickHouse (`analysis/`).

## 4. Build the SFT dataset

```bash
uv run python train/build_dataset.py runs/train-gemma --generate-reference --n 100 \
  --min-score 0.8 --exclude-families F12,F14 --out data/sft.jsonl
```
- keeps score >= 0.8, dedupes, **aborts** if any scenario seed is in dev/judge/judge-fast (or heldout when
  `ONCALL_HELDOUT_SALT` is set; salted scenarios are always refused);
- `oracle` is deliberately not usable as a data source (ground truth);
- `--exclude-families` matches `Scenario.family` if the class has it, else the `f<N>` part of the scenario id.
  The output prints the family labels seen: check that `F12`/`F14` really are the labels of those families;
- trajectories from run dirs are rebuilt from the call log (one call per assistant turn); free-text and parallel calls of the
  original LLM transcript are not kept, malformed calls never reach the dataset.

## 5. SFT

```bash
uv run python train/sft.py --data data/sft.jsonl --out adapters/gemma-sft --model google/gemma-3-4b-it --epochs 2
```
LoRA r=16/alpha=32 on the language-model projections, bf16, gradient checkpointing, batch 1 x grad-accum 16, lr 2e-4 cosine,
loss on assistant tokens only (logits computed only at those positions: Gemma's 262k vocab x 40k tokens does not fit
otherwise). Output: adapter + `oncall_train.json` (hyperparameters). Hours-scale for ~100-400 episodes on one 80 GB GPU
(estimate, UNVERIFIED).

## 6. Serve base and fine-tuned together

Restart vLLM from step 2 adding the adapter; requests then use `model=gemma-ft` for the adapter, the base id for base:
```bash
... vllm serve google/gemma-3-4b-it --enable-lora --lora-modules gemma-ft=adapters/gemma-sft  (flags as in step 2)
```

## 7. Evaluate gemma-base vs gemma-ft (heldout, 3 runs)

```bash
export ONCALL_HELDOUT_SALT=...        # same secret as the judge; never committed
uv run python -m oncall.agent --provider vllm --model google/gemma-3-4b-it --suite heldout --runs 3 --workers 8 \
  --run-dir runs/ --out results/agent-gemma-base.json
uv run python -m oncall.agent --provider vllm --model gemma-ft --suite heldout --runs 3 --workers 8 \
  --run-dir runs/ --out results/agent-gemma-ft.json
uv run oncall eval --policy reference,noop --suite heldout --out results/heldout-det.json
```
Merge the three files (`policies` dicts) and run `uv run oncall report --input <merged>.json`: the report gives mean +- std,
per-difficulty/per-family tables, failure tags and the bootstrap gap to `reference`. Expected tag drops after SFT:
`premature_resolve`, `masked_fix`, `herring_followed`, `symptom_fix`.
With ClickHouse: `python analysis/load.py runs/ --create`, then `analysis/gemma_base_vs_ft.sql`.

## 8. Held-out family eval

Train with `--exclude-families F12,F14` (step 4). The `heldout` suite contains those families, so the per-family table of
`gemma-ft` (and `analysis/score_by_model_difficulty_family.sql`) shows whether the gain also appears on families it never
saw. A gain on seen but not on held-out families means memorized scenarios, not a causal procedure: report that honestly.

## 9. GRPO (optional)

Serve with the SFT adapter registered as `gemma-grpo` and runtime LoRA updating on (step 2 + `--lora-modules gemma-grpo=adapters/gemma-sft`):
```bash
uv run python train/grpo.py --adapter adapters/gemma-sft --out adapters/gemma-grpo --steps 20 \
  --scenarios-per-step 4 --rollouts 8 --temperature 1.0 --kl-coef 0.02
```
Each step: sample 8 rollouts per scenario from vLLM, reward = env score, advantage = group-normalized, policy-gradient on
assistant tokens, save `stepNNNN/`, hot-load via `/v1/load_lora_adapter`. Rollouts are logged to
`adapters/gemma-grpo/rollouts/`, step stats to `log.jsonl`. Evaluate the `final/` adapter like in step 7 (`--model gemma-grpo`).
**Untested on GPU.** Ceiling: one GPU shared by vLLM and trainer, ~40k-token episodes, one on-policy gradient step per batch,
re-tokenized transcripts (not sampled ids), KL is against the base model with the adapter disabled. Treat it as a stretch.

## 10. Publish the adapter

```bash
huggingface-cli upload <org>/oncall-gemma-3-4b-lora adapters/gemma-sft .
```
Include in the model card: base model id, `oncall_train.json`, dataset command line, git commit, the template file and the vLLM
flags from step 2 (the adapter is useless without `gemma_tools.jinja`). Mention that the adapter was trained on the
`train` split only.

## 11. Verda Discord summary (template)

> **OnCall RL env: Gemma 3 4B on Verda** - 1x <GPU>, <N> rollouts on the train split (reference + <M> rejection-sampled), LoRA SFT
> <epochs> epochs (<hours> h) [+ GRPO <steps> steps]. Heldout (100 scenarios x 3 runs): base **<x.xx>** -> ft **<y.yy>**
> (reference 0.9x, noop 0.xx); held-out families F12/F14: <a> -> <b>. Fewer `premature_resolve` (<n> -> <m>).
> Adapter: <hf link>. Repo: <link>. vLLM + tool calling via our own Gemma template (details in train/README.md).

## 12. Fallback: Modal

Only if Verda is unavailable (not both): same commands in a Modal GPU function/container (A100/H100 80GB, vLLM and trainer in
separate processes). Nothing in this directory is Modal specific.

## UNVERIFIED (not run on a GPU or against the real services)

- vLLM `pythonic` parser with `gemma_tools.jinja` on Gemma 3 (see above); base-model quality of the pythonic format.
- `AutoModelForCausalLM` on multimodal Gemma 3 checkpoints, `logits_to_keep=<index tensor>` and `sdpa` with 40k tokens.
- Memory/time estimates; 12B.
- Gemini's OpenAI endpoint accepting the tool schemas as sent (refs/`title` are inlined/stripped; `anyOf` kept for `set_config.value`).
- Hot-loading with `load_inplace` is not used: the pusher unloads then loads under the same name.
