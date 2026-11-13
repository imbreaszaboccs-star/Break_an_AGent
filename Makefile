.PHONY: dev test eval baseline export images judge judge-fast

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
	uv run oncall judge --suite judge $(ARGS)

judge-fast:
	uv run oncall judge --suite judge-fast $(ARGS)
