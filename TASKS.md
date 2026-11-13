# Tasks & progress

Cíl: přepsat repo podle [DESIGN.md](DESIGN.md), rozsah **milníky 1–4** (§13).
Starý prototyp `triage_env/` + `tasks/` + `scripts/` se nahrazuje balíkem `src/oncall/`.

Legenda: `[ ]` todo · `[~]` rozpracováno · `[x]` hotovo (ověřeno testem/příkazem)

## M1 — Sim jádro
- [x] `src/oncall/scenarios.py` — 3 šablony topologie (e-shop, SaaS API, media), přejmenování ze seedu, obtížnosti, splity `dev` / `judge-fast` / `judge` / `heldout`
- [x] `src/oncall/sim.py` — tick loop (T=120, E=45 @1.5×), zátěž + retry, latence/bulkhead, DB conn pool, cache, cold start, spend, SLI `offered/good`
- [x] `src/oncall/faults.py` — F1 bad deploy, F2 memory leak, F3 retry storm, F4 config/flag drift, F5 externí dependency; red-herring deploy; druhá porucha v t≈45
- [x] `src/oncall/scoring.py` — §6 reward (U, error budget 2×, R_avail/R_fixed/R_diag, M_dataloss, P_collateral, P_cost) + chybové tagy §8
- [x] `noop` / `oracle` politiky, cache U(noop)/U(oracle)
- [x] `tests/test_determinism.py`, `tests/test_scoring.py`

## M2 — MCP server
- [x] `src/oncall/server.py` — FastMCP streamable HTTP, všech 9 pozorovacích + 11 akčních toolů (§5), schema validace, FIFO `asyncio.Lock`
- [x] Admin API `finalize` se SHA-256 tokenem (`ADMIN_TOKEN_SHA256`)
- [x] MCP klient (in-process + HTTP) pro politiky
- [x] `src/oncall/logsink.py` — JSONL `runs/<run_id>/<episode>.jsonl`, volitelně ClickHouse (`ONCALL_CLICKHOUSE_URL`)
- [x] `tests/test_server.py`

## M3 — Reference policy + exploit suite
- [x] `reference` (jen MCP nástroje), `stop_early`, `exploit_*` (§6 matice)
- [x] `tests/test_solvability.py` — reference ≥ 0.8 na každém dev scénáři, ≥ 2 signály na poruchu
- [x] `tests/test_exploits.py` — `max(exploit) < 0.25 < mean(reference) − 0.5`

## M4 — Harbor export, judge, CI
- [x] `src/oncall/cli.py` — `eval`, `report`, `export-harbor`, `serve`, `solve`, `finalize`, `judge`
- [x] `harbor/tasks/judge-NN/` (24 úloh, neutrální názvy) — task.toml, instruction.md, environment/{Dockerfile, docker-compose.yaml}, solution/solve.sh, tests/test.sh
- [x] `docker/sim.Dockerfile`, `Makefile` (`test`, `dev`, `judge`, `judge-fast`, `images`)
- [x] `.github/workflows/ci.yml` (`runs-on: craci`), `results/baseline.json`
- [x] smazat starý `triage_env/`, `tasks/`, `scripts/`, `tests/test_world.py`
- [x] README přepsat
- [ ] End-to-end `harbor run` s Gemini — **vyžaduje Harbor + API klíč, mimo tento stroj**

## Mimo rozsah (pozdější milníky)
- M5: F6–F14, kompoziční pasti, kalibrace
- M6: report s 3× Gemini, anotované trajektorie, ClickHouse SQL (`analysis/`)
- M7: Verda rollouty, Gemma SFT/GRPO (`train/`)
- M8: Nemotron

## Log
- 2026-11-13: audit — kód (`triage_env`, 4 typy poruch, stdio MCP, replay trace) neodpovídá DESIGN.md; zvolen rozsah M1–M4.
- 2026-11-13: ověřen Harbor formát (compose sidecar vedle služby `main`, `transport = "streamable-http"`, verifier ve `shared` módu vidí sidecar) → otevřená otázka z §10 vyřešena. Rozpracováno: M1 + M3 (sim jádro, poruchy, scoring, politiky, testy).
- 2026-11-14: **M1 + M3 hotovo** — `uv run pytest` 362 passed (~19 s). Dev suite (30): reference 0.980 (min 0.962; easy 0.981 / medium 0.985 / hard 0.976), oracle 1.000, noop / stop_early 0, všechny exploity ≤ 0.035. Judge: reference 0.978 (min 0.929). Review: reference čte jen přes nástroje, výstupy nástrojů neprozrazují ground truth. Rozpracováno: M2 + M4.
  - Známé slabiny: reference je hodně silná (obtížnost pro LLM zatím neověřená); F3 storm má úzký kalibrační okraj; `sin`/`gauss` se mohou mezi platformami lišit v posledním ulp (baseline porovnává s tolerancí).
- 2026-11-14: **M2 + M4 hotovo** (kromě reálného `harbor run`). `uv run pytest` 368 passed. Docker smoke test: sim image postaven, `oncall solve` přes HTTP MCP + `oncall finalize` = 0.97844, stejně jako lokální reference; finalize bez tokenu → 401. `oncall report --compare results/baseline.json` → exit 0. Review fix: názvy Harbor úloh prozrazovaly rodinu poruchy (`eas-f1-2000`) → přejmenováno na `judge-00..23`.
  - Neověřeno (chybí Harbor): merge compose se službou `main`, healthcheck, flagy `harbor run` a layout výstupu jobů, který čte `oncall judge`.
  - Další krok: nainstalovat Harbor, `harbor run -a oracle -p harbor/tasks/judge-00`, pak 1× Gemini (`make judge-fast`) → M5.
