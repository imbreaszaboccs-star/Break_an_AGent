.PHONY: dev test eval baseline export images judge judge-fast agent dataset sft grpo clickhouse

dev:
	uv sync

test:
	uv run pytest -q

eval:
	uv run oncall eval --policy 'reference,noop,stop_early,exploit_*' --suite dev

baseline:
	uv run oncall eval --policy 'noop,stop_early,reference,exploit_*' --suite judge --out results/baseline.json

export:
	uv run oncall export-harbor --suite judge --out harbor/tasks

images:
	docker build -t oncall-sim:local -f docker/sim.Dockerfile .

judge:
	uv run oncall judge --suite judge $(if $(MODEL),--model $(MODEL) --provider $(PROVIDER)) $(ARGS)

judge-fast:
	uv run oncall judge --suite judge-fast $(if $(MODEL),--model $(MODEL) --provider $(PROVIDER)) $(ARGS)

# LLM agent over an OpenAI-compatible API (M6/M8). Model id is always explicit:
#   make agent PROVIDER=gemini MODEL=<gemini model id>      (needs GEMINI_API_KEY)
#   make agent PROVIDER=nemotron MODEL=<nemotron model id>  (needs NVIDIA_API_KEY)
#   make agent PROVIDER=vllm MODEL=<served name> SUITE=heldout   (Gemma on Verda, VLLM_BASE_URL)
PROVIDER ?= gemini
SUITE ?= judge
RUNS ?= 3
agent:
	@test -n "$(MODEL)" || (echo "set MODEL=<model id>"; exit 2)
	uv run python -m oncall.agent --provider $(PROVIDER) --model $(MODEL) --suite $(SUITE) --runs $(RUNS) 	  --out results/agent-$(PROVIDER)-$(notdir $(MODEL)).json --run-dir runs/

# Gemma training (M7, GPU box): see train/README.md
dataset:
	uv run python train/build_dataset.py runs/ --generate-reference --n 500 --out data/sft.jsonl

sft:
	uv run --group train python train/sft.py $(ARGS)

grpo:
	uv run --group train python train/grpo.py $(ARGS)

clickhouse:
	uv run python analysis/load.py runs/ --create
