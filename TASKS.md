# Tasks & progress

Cíl: přepsat repo podle [DESIGN.md](DESIGN.md), milníky 1–8 (§13). Kód M1–M8 hotový; zbývají jen běhy, které potřebují klíče / GPU / Harbor.
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
- [x] End-to-end `harbor run` (Harbor 0.26, `judge-00`): `-a oracle` → 0.97317 (= lokální reference na bit), `-a nop` → 0.0
- [ ] `harbor run -a opencode` s Gemini — **vyžaduje API klíč**

## M5 — F6–F14, obtížnosti, kalibrace
- [x] F6 cert expiry, F7 plný disk, F8 zpráva u druhé poruchy, F9 cache stampede, F10 poison message (fronta + worker), F11 tichý canary, F12 thread starvation, F13 zavádějící zpráva, F14 odmaskovaná kaskáda (+ `under_provisioned`)
- [x] mix obtížností dle §4 (easy F1/F3/F5/F7 · medium past · hard F9/F10/F14 + F6/F8)
- [x] tagy `authority_bias`, `canary_missed`, `unmasked_cascade_missed`, `missed_event` (WARN)
- [x] reference + oracle (vícekrokový), exploity < 0.25, nový baseline + Harbor export

## M6 — Report + analýza
- [x] LLM agent runner (`oncall.agent`, OpenAI-compatible: Gemini / Nemotron / vLLM)
- [x] `analysis/*.sql` + schéma ClickHouse, loader
- [x] report: chybové tagy per model, gap per run (kladný v každém běhu?), anotované trajektorie (první volání, kde byl signál vidět, vs. první zásah)
- [x] `oncall judge --runner direct|harbor` + `make judge MODEL=…` (bez modelu výrazné upozornění, ne tiché přeskočení)
- [~] Gemini API (billing tier 3): `gemini-3.1-pro-preview`, `gemini-3.8-flash`, `gemma-4-31b-it`, `gemini-4-argon`, `gemini-4-carbon` — judge × 3, paralelně

## M7 — Gemma na Verdě
- [x] `train/build_dataset.py`, `train/sft.py` (LoRA), `train/grpo.py`, `train/README.md` (runbook Verda + vLLM)
- [ ] skutečné rollouty + trénink + eval base vs ft na heldout — **vyžaduje Verda GPU**

## M8 — Nemotron
- [x] preset `nemotron` v agent runneru
- [x] běh `nvidia/nemotron-3.5-super-vl-120b-a12b` na judge-fast × 3 (thinking on, T=1.0, top_p 0.95) → [results/nemotron-judge-fast/report.md](results/nemotron-judge-fast/report.md)
- [x] plný judge × 3 (24 scénářů) → [results/nemotron-judge/report.md](results/nemotron-judge/report.md)

## Log
- 2026-11-13: audit — kód (`triage_env`, 4 typy poruch, stdio MCP, replay trace) neodpovídá DESIGN.md; zvolen rozsah M1–M4.
- 2026-11-13: ověřen Harbor formát (compose sidecar vedle služby `main`, `transport = "streamable-http"`, verifier ve `shared` módu vidí sidecar) → otevřená otázka z §10 vyřešena. Rozpracováno: M1 + M3 (sim jádro, poruchy, scoring, politiky, testy).
- 2026-11-14: **M1 + M3 hotovo** — `uv run pytest` 362 passed (~19 s). Dev suite (30): reference 0.980 (min 0.962; easy 0.981 / medium 0.985 / hard 0.976), oracle 1.000, noop / stop_early 0, všechny exploity ≤ 0.035. Judge: reference 0.978 (min 0.929). Review: reference čte jen přes nástroje, výstupy nástrojů neprozrazují ground truth. Rozpracováno: M2 + M4.
  - Známé slabiny: reference je hodně silná (obtížnost pro LLM zatím neověřená); F3 storm má úzký kalibrační okraj; `sin`/`gauss` se mohou mezi platformami lišit v posledním ulp (baseline porovnává s tolerancí).
- 2026-11-14: **M2 + M4 hotovo** (kromě reálného `harbor run`). `uv run pytest` 368 passed. Docker smoke test: sim image postaven, `oncall solve` přes HTTP MCP + `oncall finalize` = 0.97844, stejně jako lokální reference; finalize bez tokenu → 401. `oncall report --compare results/baseline.json` → exit 0. Review fix: názvy Harbor úloh prozrazovaly rodinu poruchy (`eas-f1-2000`) → přejmenováno na `judge-00..23`.
  - Neověřeno (chybí Harbor): merge compose se službou `main`, healthcheck, flagy `harbor run` a layout výstupu jobů, který čte `oncall judge`.
  - Další krok: nainstalovat Harbor, `harbor run -a oracle -p harbor/tasks/judge-00`, pak 1× Gemini (`make judge-fast`) → M5.
- 2026-11-14: start M5–M8. Na stroji nejsou API klíče, GPU ani Harbor → M6–M8 = kód + offline testy, reálné běhy zůstávají na uživateli.
- 2026-11-14: **M5 hotovo** — F6–F14 (+ fronta/worker ve všech šablonách), mix obtížností §4, nové tagy, vícekrokový oracle. `uv run pytest` 400 passed. Judge: reference 0.979 (min 0.948), každá rodina F1–F14 ≥ 0.95; sweep 300 scénářů: reference ≥ 0.8 všude; všech 10 exploitů = 0.000.
- 2026-11-14: **review fixy (externí code review)**: (1) díra v odměně — slepý „neškodný" sweep (vypnout flagy, `dlq_enabled`, `rotate_cert`, `max_retries=1`…) nebyl penalizován → `necessary()` + 0.05 za zbytečný nedestruktivní zásah, nový `exploit_blind_sweep` (= 0.000), DESIGN §6 upraven; (2) falešný tag `symptom_fix` u canary flagu / F9 rate-limitu; (3) p99 se nepropagovalo do volajících; (4) SFT dataset zahazoval uvažování modelu → bere `<episode>.messages.json`; (5) `make judge` bez modelu tiše přeskočil agenta. Neopraveno záměrně: metriky hned po akci ukazují jen dokončené minuty (jako reálný monitoring) — doplněno do instrukce.
- 2026-11-14: **M6–M8 kód hotov** — `oncall.agent` (Gemini / Nemotron / vLLM), `train/` (dataset, LoRA SFT, GRPO, Gemma chat template, runbook Verda), `analysis/` (ClickHouse schéma + 5 dotazů + loader), report s anotovanými selháními. Offline testy proti fake OpenAI serveru.
- 2026-11-14: **Harbor ověřen end-to-end** (0.26, Docker Desktop/Windows): oracle 0.97317 = lokální baseline, nop 0.0; layout výstupu `<job>/<task>__<id>/verifier/reward_breakdown.json` sedí s `oncall judge`. `build_timeout_sec` 600 → 1800 (build agent image trval 7,5 min). Přidán test, že `harbor/tasks/*/solution/oncall` není zastaralý vůči `src/`.
- 2026-11-14: M8 start — NVIDIA klíč od uživatele (jen v env proměnné, nikde v repu; doporučeno ho po testech zrotovat). Agent runner: preset `extra` (Nemotron `enable_thinking`), `--extra-body`, `--limit`, ukládání `reasoning_content` do transkriptu, timeout 600 s. Smoke test (eas-f1-2000, 4 tahy): paralelní tool cally fungují, správný rollback bad deploye, ~5 s/tah.
- 2026-11-14: **Nemotron judge-fast × 3 hotovo** — 0.789 ± 0.215 (easy 0.934 / medium 0.857 / hard 0.695) vs reference 0.977. **Gap 0.188, 95% CI [0.115, 0.267], kladný v každém běhu (0.181 / 0.222 / 0.162).** Nejslabší F10 (0.63), F9 (0.64), F12 (0.74), F14 (0.74); tagy: over_investigation 11, collateral 9, symptom_fix 5, missed_event 3. Replay 36 zaznamenaných sekvencí akcí → shodné skóre na bit. Oprava anotací: signál se počítá až od `visible_at` poruchy; „porucha přišla až po resolve" se vypisuje explicitně; v anotacích max 1 epizoda na scénář.
- 2026-11-14: plný judge × 3 s 3 workery → 61/72 epizod skončilo na HTTP 429 (rate limit NVIDIA) a **runner je bodoval jako selhání agenta** (průměr 0.204 = artefakt). Opraveno: delší backoff na 429 (Retry-After, ~15 min / request), restart epizody po infra chybě (2×, cooldown), epizody s infra chybou se **vyřazují, nikdy neboduje**, `--resume <run dir>` doplní jen chybějící; per-run gap podle explicitního `run` indexu. Test `test_rate_limit_outage_is_excluded_not_scored_and_resume_fills_it`. Resume běží se 2 workery.
- 2026-11-14: **Nemotron judge × 3 hotovo (hlavní číslo)** — 72/72 epizod, 0 vyřazených, 1 restart po 429. Nemotron 0.840 ± 0.183 (easy 0.891 / medium 0.904 / hard 0.781) vs reference 0.979. **Gap 0.138, 95% CI [0.088, 0.200], kladný v každém běhu (0.104 / 0.152 / 0.159).** Nejslabší F9 (0.59), F14 (0.79), F10 (0.83). Replay 72 sekvencí → shodné skóre na bit. Log runneru se teď flushuje (dřív prázdný při zápisu do souboru).
- 2026-11-14: **Kimi K3.1 Pro (Verda inference)** — nový preset `verda` (`VERDA_INFERENCE_BASE_URL` = `https://inference.verda.com` dle docs.verda.com, `/v1` se doplní; `VERDA_INFERENCE_API_KEY`). Smoke test OK (6 paralelních tool callů, reasoning, správný rollback). Spuštěn judge × 3, 2 workery, T=1.0 → `results/agent-kimi-judge.json`. Klíč jen v env proměnné.
- 2026-11-14: **Kimi K3.1 Pro judge × 3 hotovo** — 72/72, 0 vyřazených, 0 restartů (~1 min/epizoda). Kimi 0.874 ± 0.182 (easy 0.922 / medium 0.957 / hard 0.802). **Gap 0.105, 95% CI [0.060, 0.158], kladný v každém běhu (0.130 / 0.069 / 0.116).** Nejslabší F8 (0.55), F9 (0.73), F7 (0.78), F14 (0.82). Sdílené selhání s Nemotronem: resolve před druhou poruchou v t≈40–50 (`missed_event`). Replay 72 → shodné na bit. Reporty: `results/kimi-judge/`, srovnání obou `results/judge-agents/`.
- 2026-11-14: **DeepSeek 4.1 Flash (`deepseek-4-1-flash-1017`, Verda inference)** — smoke test OK (správný rollback, ~1 s/tah, bez reasoning_content). Spuštěn judge × 3, 2 workery, T=1.0 → `results/agent-deepseek-judge.json`.
- 2026-11-14: **DeepSeek 4.1 Flash judge × 3 hotovo** — 72/72, 0 vyřazených. 0.851 ± 0.195 (easy 0.922 / medium 0.947 / hard 0.764). **Gap 0.127, 95% CI [0.072, 0.195], kladný v každém běhu (0.120 / 0.132 / 0.130).** Nejslabší F9 (0.63), F8 (0.70), F10 (0.72). Replay 72 → shodné na bit. Srovnání 3 modelů: `results/judge-agents/report.md` — gap 0.105–0.138, kladný v každém z 9 běhů.
- 2026-11-14: **Gemini API klíč (tier 3)** — vypsáno ~50 modelů; vybrány 3 rodiny: Gemini Pro (`gemini-3.1-pro-preview`, přesná verze místo aliasu `-latest`), Gemini Flash (`gemini-3.8-flash`), Gemma open (`gemma-4-31b-it` = zároveň `gemma-base` z §7/§11). Kódová jména `gemini-4-*` bez popisu vynechána. **Fix runneru:** Gemini 3 vrací u tool callů `extra_content.google.thought_signature`, které se musí poslat zpět (jinak HTTP 400) → extra pole tool callu se teď zachovávají. Smoke test všech 3 OK; spuštěny paralelně judge × 3, každý 2 workery, run dirs `runs/gemini-3.1-pro`, `runs/gemini-3.8-flash`, `runs/gemma-4-31b`.
- 2026-11-14: na přání uživatele přidány `gemini-4-argon` a `gemini-4-carbon` (API je vypisuje jako „Gemini 4 Argon/Carbon“, v 3.0, bez dalšího popisu). Smoke test OK (správný rollback), ale pomalé (~38 s / ~20 s na tah) → judge × 3 se 4 workery, run dirs `runs/gemini-4-argon`, `runs/gemini-4-carbon`.

## v2 — těžší a realističtější simulace (zadání uživatele 2026-11-14)
- [x] research: 15 ověřených postmortemů s primárními zdroji (Twilio 2013, GitHub 2018, Honeycomb 2023, Pulumi 2023, Clerk 2025, Netlify 2021, Postmark 2022/2024, Facebook 2010, GitLab #482, CircleCI 2025, GoCardless 2017, Healthchecks.io 2025, …) + SRE benchmarky (ITBench-AA: Gemini 3.1 Pro 30 %, OpenRCA 2.0 20.7 %)
- [x] návrh: 14 mechanismů R1–R14, každý podle konkrétního postmortemu; úrovně medium / hard / expert (bez easy); tichá škoda uživatelům v SLI; per-instance pohled, business metriky
- [x] implementace A: infra + realistická telemetrie + R1–R7
- [x] implementace B: R8–R14, nové úrovně a suity, reference, exploity, baseline, export
- [x] změřit obtížnost po návrhu (carbon ≈ 0.6 a ostatní pod ním je jen **hypotéza, ne cíl ani ground truth**; neladit simulaci proti jednomu modelu, upravovat jen nerealistické/nefér mechaniky)
- [x] nový baseline, Harbor export, přeměření modelů (7 modelů × judge × 3)

- 2026-11-14: start v2. Gemma-4-31b běh na v1 zastaven (5/72 hotovo, ~15 h zbývalo; lze `--resume`). argon / carbon / 3.1 Pro / 3.8 Flash na v1 doběhnou jako výchozí bod kalibrace (carbon v1 ≈ 0.96).
- 2026-11-14: všechny testovací běhy na v1 zastaveny (na pokyn uživatele). v1 výsledky: Nemotron 0.840, DeepSeek 0.851, Kimi 0.874, gemini-4-argon 0.960 (72/72); carbon / 3.1 Pro / 3.8 Flash / Gemma nedoběhly. Spuštěna implementace v2 část A.
- 2026-11-14: **v2 část A hotovo** — per-instance model, business metriky, tichá škoda v SLI, `get_instances` / `drain_instance` / `get_business_metrics`, 6 nových údržbových akcí, 8 config klíčů, R1–R7. 435 testů OK (1 = zastaralý Harbor export). Reference na dev 0.973 (min 0.929), na 890 generovaných scénářích min ≥ 0.915 pro R1–R7; max exploit 0.010. Kontrola úniku pravdy: 0 z 7 nových mechanismů. Spuštěna část B.
- 2026-11-14: **v2 část B hotovo** — R8–R14, úrovně medium/hard/expert (easy pryč), judge 24 = 6/10/8. 473 testů OK; reference judge 0.963–0.977 dle úrovně, oracle 1.0, noop/stop_early 0, max exploit 0.028; únik pravdy 0/24. DESIGN.md: nová sekce v2. **Spuštěno měření v2** (judge × 3, paralelně): gemini-4-carbon, gemini-4-argon, gemini-3.1-pro, gemini-3.8-flash, Kimi, DeepSeek, Nemotron → `results/v2/`, `runs/v2/`.
- 2026-11-15: **v2 přeměřeno, 7 modelů × 72 epizod, 0 vyřazených** → `results/v2/judge-agents/report.md`. carbon 0.871, argon 0.850, Kimi 0.759, 3.8 Flash 0.748, DeepSeek 0.724, Nemotron 0.636, 3.1 Pro 0.582 (reference 0.969). Gap kladný ve všech 21 bězích. Proti v1 každý model −0.09 až −0.20. Nejtěžší: R9 (FB 2010) 0.05–0.47, R8 (Postmark 2022), R1 (Twilio), R13 (GoCardless). Replay 504 epizod → shodné na bit. Hypotéza carbon ≈ 0.6 nesplněna (0.871) — simulace se proti ní záměrně neladila; navržené další realistické páky (pomalý tooling během incidentu, mezery v telemetrii, oznamující eventy v šumu, víc expert scénářů) čekají na rozhodnutí uživatele.
