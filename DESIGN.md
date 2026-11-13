# OnCall — RL prostředí pro incident response

> Design dokument (v1). Cíl: produkční, reprodukovatelné RL prostředí, ve kterém agent
> jako on-call SRE diagnostikuje a opravuje incidenty v simulovaném produkčním systému.
> Splňuje zadání *Break the Agent* (AfterQuery), ale je navržené jako samostatný produkt:
> deterministický simulátor, MCP rozhraní, verifikovatelná odměna, sada exploit testů,
> held-out evaluace a pipeline pro trénink menšího modelu.

---

## 1. Proč tohle prostředí

**Úloha:** Produkční systém (~12 mikroslužeb, DB, cache, fronta, externí platební brána)
má incident. Agent má omezený čas (simulované minuty) a nástroje jako skutečný on-call
inženýr: metriky, logy, trace, historie deployů, konfigurace, runbooky — a zásahy:
rollback, restart, scale, config, feature flagy, circuit breaker, failover.

**Proč je to těžké pro frontier agenty (a proč férově):**

| Schopnost ze zadání | Jak se v prostředí projevuje |
|---|---|
| Plánování více kroků dopředu | Oprava má pořadí (nejdřív zastavit retry storm, pak škálovat DB; ne naopak). |
| Průzkum neznámého systému | Topologie a parametry se mezi scénáři mění; agent musí systém prozkoumat. |
| Používání nástrojů | ~20 nástrojů s různou cenou (čas) a informační hodnotou. |
| Omezené zdroje | Každé volání posouvá simulovaný čas → error budget hoří. Škálování stojí peníze. |
| Adaptace na nové info | Druhá porucha / zpráva od jiného týmu přichází uprostřed epizody. |

**Co se agent může naučit:** kauzální uvažování (symptom vs. root cause), hodnotu
informace vs. cenu čekání, ověřování, že oprava skutečně funguje (ne jen maskuje), a
minimalizaci kolaterálních škod. To jsou přenositelné dovednosti pro reálné agentní
nasazení v infrastruktuře.

**Proč ne LLM-judge:** veškerá odměna se počítá z ground-truth stavu simulátoru.
Žádný text agenta neovlivňuje skóre mimo jedno strukturované (enum) pole diagnózy.

---

## 2. Architektura

```
┌────────────────────┐   MCP (streamable HTTP)   ┌──────────────────────────────┐
│ Harbor + OpenCode  │ ────────────────────────▶ │ oncall-sim (sidecar kontejner)│
│ (agent kontejner)  │                           │  ├─ MCP server (agent tools)  │
│  - nevidí scénář   │                           │  ├─ Simulator (deterministický)│
│  - nevidí seed     │                           │  └─ Admin API (token, jen pro │
└────────────────────┘                           │      verifier: finalize/score)│
          │ po skončení agenta                   └──────────────────────────────┘
          ▼                                                   ▲
   tests/test.sh (verifier) ── admin token ──────────────────┘
          └─▶ /logs/verifier/reward.txt  (+ reward_breakdown.json)
```

- **Sidecar izolace:** scénář, seed a ground truth existují jen v sim kontejneru.
  Agent komunikuje výhradně přes MCP. Admin token je v `tests/` (do agent kontejneru
  se kopíruje až po skončení agenta) → agent nemůže volat `finalize`/`score`.
- **Determinismus:** výstup = f(seed, sekvence akcí). Oddělené RNG streamy
  (`traffic`, `faults`, `noise`) → *common random numbers*: provoz a poruchy jsou
  pro všechny politiky stejné, liší se jen důsledky akcí. Férové srovnání agent vs.
  reference vs. no-op na stejném seedu.
- **Stack:** Python 3.12, `uv`, oficiální `mcp` SDK (FastMCP, streamable HTTP),
  stdlib `random.Random` (žádný numpy), `pytest`. Docker + docker-compose.

### Struktura repa

```
oncall-env/
  pyproject.toml              # pinned deps, uv.lock
  Makefile                    # make judge | make test | make dev
  docker/
    sim.Dockerfile
  src/oncall/
    sim.py                    # engine: tick loop, služby, propagace chyb, latence
    faults.py                 # knihovna poruch (viz §4)
    scenarios.py              # generátor scénářů ze seedu + splity
    server.py                 # MCP tools + admin API
    scoring.py                # reward (viz §5)
    policies.py               # noop, stop_early, reference, oracle, exploity
    cli.py                    # oncall eval / oncall report / oncall export-harbor
  harbor/
    tasks/<scenario_id>/      # generováno: task.toml, instruction.md,
                              # environment/, solution/solve.sh, tests/test.sh
  tests/
    test_determinism.py
    test_exploits.py          # každý exploit < práh
    test_solvability.py       # reference policy řeší každý scénář
  results/                    # commitnuté reporty s hashi verzí
  README.md
```

---

## 3. Simulátor

**Čas:** 1 tick = 1 simulovaná minuta. Horizont `T = 180` ticků + epilog `E = 60`.

**Model služby** (per služba): `replicas`, `capacity_per_replica`, `version`,
`config{}`, `memory_used/limit`, `conn_pool_size`, `disk_used`, `cert_expiry_tick`,
`health`. Za tick:

- **Zátěž:** request rate z denní křivky + šum; propaguje se po call grafu
  (fan-out koeficienty). Retry politika násobí zátěž na downstream při chybách
  (→ realistické retry stormy).
- **Latence:** `base / max(0.05, 1 − utilization)` + příspěvky downstream (p50/p99).
- **Chybovost:** vlastní (bug v deployi, OOM, plný disk, expirovaný cert) +
  propagovaná z downstream (s fallbackem/circuit breakerem tlumená).
- **DB:** max connections; každá replika držení `pool_size` spojení →
  škálování klientů nad limit **zhoršuje** situaci (záměrně, odpovídá realitě).
- **Restart:** instance cold-start 2–4 ticky, vyprázdněná cache → cache stampede.

**SLI (ground truth):** `ok_t = obsloužené uživatelské requesty bez chyby a pod
latency SLO / nabídnuté`. Shedované requesty (maintenance mode, rate limit) = neúspěch.

**Topologie:** 3 šablony (e-shop, SaaS API, media pipeline), náhodné přejmenování
služeb a parametry ze seedu → agent nemůže spoléhat na zapamatování.

---

## 4. Scénáře a poruchy

| Rodina | Signály (vždy ≥ 2 nezávislé) | Správný zásah | Typická past |
|---|---|---|---|
| F1 Bad deploy | skok chybovosti v čase deploye, stacktrace v logu | rollback služby | souběžný nevinný deploy jiné služby (red herring) |
| F2 Memory leak | rostoucí RSS, OOM kills (pila), latence | rollback/flag vypnutí leaku | restart „pomůže" na 20 min → epilog odhalí |
| F3 Retry storm → DB pool | DB conn saturace, retry metriky na upstreamu | snížit retry/backoff na upstreamu, pak DB | škálování klientů / restart DB |
| F4 Config/flag drift | latence po změně flagu, audit log | vypnout flag | rollback deploye, který nic nezměnil |
| F5 Externí dependency | timeouty na PSP, status zpráva | circuit breaker + fallback | rollback vlastní služby |
| F6 Odložená expirace certu | cert metadata, warning v logu | rotace certu před `t_exp` | nekontrolovat proaktivně → výpadek v t≈90 |
| F7 Plný disk (logy) | disk %, write errors | vyčistit + snížit log level | restart bez uvolnění místa |
| F8 Druhá porucha mid-episode | nový alert/zpráva od týmu v t≈60 | adaptovat, znovu triage | prohlásit incident za vyřešený po první opravě |

**Obtížnost:** `easy` (1 porucha, bez pastí — sanity check), `medium` (1 porucha +
red herring), `hard` (2 poruchy, odložená událost, red herringy).

**Splity:** `dev` (veřejné seedy, 30 scénářů), `judge` (pevný seznam 12 seedů,
publikovaný kvůli reprodukovatelnosti), `heldout` (seedy z tajného salt, 100 scénářů,
nepoužívá se při ladění, jen pro finální reporty a trénink malého modelu).

**Fairness invariant (testováno):** každá porucha emituje ≥ 2 pozorovatelné signály
dostupné přes nástroje; non-privileged reference policy každý scénář řeší
se skóre ≥ 0.8. Scénář, který tím neprojde, se nesmí dostat do suite.

---

## 5. MCP rozhraní

Každé volání stojí simulovaný čas (svět mezitím běží). Výstupy jsou realistické:
šum, stránkování, truncace na N řádků.

**Pozorování (1 min, není-li uvedeno jinak)**

| Tool | Popis |
|---|---|
| `get_status()` | čas, zbývající horizont, aktivní alerty, infra spend |
| `get_events(since)` | nové alerty, zprávy od jiných týmů, deploye ostatních |
| `get_topology()` | služby a call graf |
| `get_metrics(service, metric, window)` | rps, error_rate, p50/p99, cpu, mem, conns, disk, retries |
| `get_logs(service, level, grep, limit)` | 95 % šum, relevantní řádky jen u příčiny |
| `get_traces(endpoint, n)` (2 min) | vzorky trace se span latencemi/chybami |
| `get_deploys(service?)` | historie verzí, kdo a kdy |
| `get_config(service)` / `get_flags()` | aktuální konfigurace a feature flagy, audit log |
| `get_runbook(topic)` | obecné SRE runbooky (nezávislé na scénáři) |

**Akce**

| Tool | Čas | Pozn. |
|---|---|---|
| `rollback(service, version)` | 5 min | rollback nevinné služby = kolaterál |
| `restart(service)` | 3 min | cold start, vyprázdní cache |
| `scale(service, replicas)` | 4 min | ovlivní spend a DB spojení |
| `set_config(service, key, value)` | 2 min | validace rozsahu, nevalidní → chyba (stojí čas) |
| `set_flag(flag, on)` | 1 min | |
| `set_circuit_breaker(service, dep, mode)` | 2 min | `closed/open/fallback` |
| `failover_db()` | 6 min | bez repliky v sync → ztráta dat (tvrdá penalizace) |
| `rotate_cert(service)` / `cleanup_disk(service)` | 3 min | |
| `wait(minutes)` | n | explicitní pozorování vývoje |
| `resolve_incident(root_causes[], summary)` | — | **ukončí** interakci; `root_causes` = seznam `{service, fault_class}` z enumu |

Po `resolve_incident` (nebo vyčerpání horizontu / max 150 volání) simulátor
**dojede zbytek horizontu bez akcí a pak epilog** (60 min, provoz 1.5×).
Ukončit dřív tedy nic nezastaví — svět běží dál, jako v produkci.

---

## 6. Reward

Vše z ground truth simulátoru, deterministicky.

```
U(π)      = průměr ok_t přes t ∈ [0, T+E)               # dostupnost pro uživatele
R_avail   = clip((U(agent) − U(noop)) / (U(oracle) − U(noop)), 0, 1)
R_fixed   = podíl root-cause poruch skutečně odstraněných na konci epilogu
            (maskovaná porucha, např. restartovaný leak, = 0)
R_diag    = 1 pokud množina root_causes == ground truth, jinak 0 (jediný pokus)

score_raw = 0.60·R_avail + 0.30·R_fixed + 0.10·R_diag
score     = clip(score_raw · M_dataloss − P_collateral − P_cost, 0, 1)

M_dataloss   = 0.25 při jakékoli ztrátě dat (failover bez sync, rollback migrace)
P_collateral = 0.05 za každý zbytečný destruktivní zásah (rollback/restart zdravé služby)
P_cost       = 0.10 pokud spend na konci > 1.3× baseline
```

- `U(noop)` a `U(oracle)` se počítají přehráním stejného seedu (deterministické,
  cacheované). `oracle` = privilegovaná skriptovaná politika znalá ground truth
  (horní mez pro normalizaci, **ne** reference run).
- `reward_breakdown.json` vedle `reward.txt` obsahuje všechny složky + tagy chyb
  (§8) → judges vidí *proč* skóre vyšlo.

### Exploit matice (automatické testy v `tests/test_exploits.py`)

| Strategie | Proč neprojde | Očekávané skóre |
|---|---|---|
| Nic nedělat | R_avail = 0 z definice, R_fixed = 0 | ≈ 0 |
| Okamžitý `resolve_incident` | svět dojede bez zásahu; max R_diag z hádání (1/|enum|) | < 0.05 |
| Restart všeho dokola | cold starty + stampede; leak se vrátí v epilogu; kolaterál | < 0.2 |
| Scale všeho na max | spend penalizace; F3 se zhorší (DB spojení); nefixuje bugy | < 0.2 |
| Rollback všeho | kolaterál, nekompatibilní migrace → ztráta dat | < 0.1 |
| Maintenance mode / shed traffic | shedované requesty = neúspěch | ≈ 0 |
| Vypnout health checky / alerty | skóre jde z ground truth, ne z pozorovaných metrik | beze změny |
| Hádat všechny root causes | `==` množin, jeden pokus | 0 za diag |
| Injekce do `summary` | `summary` se neboduje, žádný LLM judge | 0 |
| Čtení scénáře / seedu | jen v sidecaru; MCP neexpozuje; admin API za tokenem | — |
| Nevalidní argumenty / fuzz | schema validace, chyba stojí čas | ≤ noop |

Invariant v CI: `max(exploit scores) < 0.25 < mean(reference) − 0.5`, na všech
`dev` seedech. Nový exploit nalezený kýmkoli → nový test, pak fix.

---

## 7. Politiky a baseliny

| Politika | Informace | Účel |
|---|---|---|
| `noop` | — | baseline „do nothing" (judging) |
| `stop_early` | — | `resolve_incident` po 1. volání `get_status` (judging) |
| `reference` | **stejné MCP nástroje jako agent** | reference run; dokazuje, že úloha je řešitelná z dostupných informací |
| `oracle` | ground truth | normalizace R_avail, horní mez |
| `exploit_*` | — | exploit matice |
| `frontier` | MCP přes Harbor/OpenCode | měřený agent |

**Reference policy (expertní runbook, deterministická):**
1. Triage: od uživatelských SLI po call grafu dolů → nejhlubší anomální služba
   (anomálie = odchylka od baseline okna).
2. Korelace s časovou osou: deploye/flag/config změny v ±5 min od začátku anomálie.
3. Klasifikace podle signatury signálů (tabulka v §4) → zásah.
4. Ověření: `wait` + kontrola, že metriky se vrátily *a drží* (detekce maskování).
5. Proaktivní kontroly (certy, disk) a sledování `get_events` → re-triage při nové události.
6. `resolve_incident` až po stabilizaci.

Reference je záměrně jednoduchá a čitelná — její síla vychází ze správného postupu,
ne z privilegovaných dat. Spouští se přes **stejný MCP server** (in-process klient),
takže se do Harbor exportuje jako `solution/solve.sh` (oracle agent v Harboru).

---

## 8. Analýza chyb (Meaningful difficulty)

Automatické tagy z trajektorie porovnané s ground truth:

| Tag | Detekce | Rozhodnutí, které agent udělal špatně |
|---|---|---|
| `symptom_fix` | první zásah na službě, která není root cause | zaměnil symptom za příčinu |
| `masked_fix` | restart bez odstranění příčiny, regrese v epilogu | neověřil trvalost opravy |
| `herring_followed` | zásah na red-herring deploy | korelace ≠ kauzalita |
| `over_investigation` | čas do 1. správného zásahu > 2× reference | špatná cena informace vs. čekání |
| `premature_resolve` | resolve s aktivní poruchou | nepočkal na ověření |
| `missed_event` | nečetl `get_events` po t≈60, F8 nevyřešena | neadaptoval se na novou info |
| `collateral` | zbytečný destruktivní zásah | chybí risk management |
| `wrong_order` | např. scale DB před zastavením retry stormu | plánování |

Report ukazuje distribuci tagů per model + 2–3 anotované trajektorie (s výňatkem, kde
informace pro správné rozhodnutí *byla* dostupná — odkaz na konkrétní tool output).

---

## 9. Evaluace a reprodukovatelnost

**Jeden příkaz:**

```bash
make judge        # = uv run oncall judge --suite judge --agent-runs 3
```

Spustí: build kontejnerů → `noop`, `stop_early`, `reference`, 3× frontier agent přes
`harbor run` na 12 judge scénářích → `results/<timestamp>/report.md` + `report.json`.

**Bez LLM (rychlé, CI):** `uv run oncall eval --policy reference --suite dev`

**Report obsahuje:**
- mean ± std per politika, per obtížnost, per rodina poruchy
- gap `reference − agent` s 95% bootstrap CI přes scénáře; per-run konzistence
  (gap musí být kladný v každém ze 3 runů)
- exploit matice, distribuce chybových tagů
- hashe: git commit, `uv.lock`, image digest, seed list, model ID + parametry

**Determinismus:** `test_determinism.py` — stejný seed + akce ⇒ identický hash
trajektorie a skóre (napříč běhy i platformami). Variance tedy pochází jen z agenta.

**Kalibrační cíle (hypotézy k ověření, ne naměřené výsledky):**
reference ≥ 0.85, frontier ≤ 0.55, všechny baseliny/exploity ≤ 0.2.
Smyčka: pokud frontier > cíl → přidat red herringy/odložené události (ne zatajovat info);
pokud reference < 0.8 na scénáři → scénář je nefér, opravit nebo vyřadit.

---

## 10. Harbor integrace

`oncall export-harbor --suite judge` vygeneruje pro každý scénář:

```
harbor/tasks/<id>/
  task.toml               # timeouty, MCP server endpoint sidecaru
  instruction.md          # role on-call SRE, cíl, popis nástrojů a pravidel času/odměny
  environment/
    Dockerfile            # agent kontejner (bez scénáře)
    docker-compose.yaml   # sidecar oncall-sim, SCENARIO_SEED jen v sidecar env
  solution/solve.sh       # spustí reference policy přes MCP
  tests/test.sh           # admin token → finalize → reward.txt + breakdown
```

`instruction.md` popisuje **pravidla** úplně a pravdivě (čas běží, epilog existuje,
jak se počítá skóre). Žádné triky ve formulaci — obtížnost je v rozhodování.

> Otevřené: přesné schéma MCP konfigurace v `task.toml` a podpora docker-compose
> sidecaru ověřit proti starter kitu Harboru. Fallback: sim běží ve stejném kontejneru
> jako jiný uživatel s právy 0700 na scénářová data, MCP přes localhost.

---

## 11. Trénink menšího modelu (stretch)

1. **Data:** trajektorie `reference` na `dev`+train seedech renderované jako
   tool-call konverzace (SFT) + frontier trajektorie se skóre ≥ 0.8
   (rejection sampling).
2. **Model:** open-weights ~7–8B instruct s tool-calling (LoRA SFT).
3. **RL (volitelně):** GRPO/PPO přímo s rewardem prostředí — simulátor je rychlý
   (tisíce epizod/h bez LLM), skóre je dense díky R_avail.
4. **Evaluace:** base vs. SFT vs. SFT+RL na `heldout` seedech **a** na held-out
   rodině poruch (kontrola, že model se neučí nazpaměť scénáře, ale postup).
   Metriky: skóre, distribuce chybových tagů (očekávaný pokles `masked_fix`,
   `premature_resolve`).

---

## 12. Testy a kvalita

| Test | Co hlídá |
|---|---|
| `test_determinism.py` | reprodukovatelnost |
| `test_exploits.py` | každá exploit politika < práh na všech dev seedech |
| `test_solvability.py` | reference ≥ 0.8 a každá porucha má ≥ 2 signály |
| `test_scoring.py` | noop = 0, oracle = 1, monotonie (oprava dřív ⇒ skóre ≥) |
| `test_server.py` | schema validace, auth admin API, agent nevidí ground truth |

CI (GitHub Actions): `uv sync --frozen`, `pytest`, `oncall eval --policy reference
--suite dev`, build images. Release = tag + commitnutý report v `results/`.

---

## 13. Milníky

1. **Sim jádro** — engine, F1–F3, scoring, noop/oracle, determinismus test.
2. **MCP server** — všechny tooly, admin API, lokální klient pro politiky.
3. **Reference policy + exploit suite** — solvability a exploit testy zelené.
4. **Harbor export + `make judge`** — end-to-end s jedním frontier runem.
5. **F4–F8, obtížnosti, kalibrace** — iterace podle chybových tagů.
6. **Report + demo** — 3× frontier, CI gap, anotované trajektorie.
7. **Stretch** — SFT malého modelu, eval na heldout.

## 14. Demo (10 min)

1. (1 min) Problém a proč on-call (reálný, cenný, kauzální).
2. (3 min) Živě: frontier agent na `hard` scénáři → restartuje leakující službu,
   prohlásí vyřešeno, epilog odhalí regresi. Vedle reference: správný rollback.
3. (2 min) Reward + exploit matice (živě spustit `exploit_restart_all`, `stop_early`).
4. (2 min) Výsledky: gap s CI, chybové tagy, odkaz na místo v trajektorii, kde
   informace byla dostupná.
5. (2 min) Reprodukce jedním příkazem + (stretch) malý model před/po.

---

## Otevřené otázky

- Který frontier model a limity harnessu (max turns, timeout) — ovlivní `T` a cenu volání.
- MCP schéma v Harbor `task.toml` a sidecar podpora (viz §10).
- Počet judge scénářů vs. čas běhu (12 × 6 runů) — změřit po milníku 4.
