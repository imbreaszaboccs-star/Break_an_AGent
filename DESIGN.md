# OnCall — RL prostředí pro incident response

> Design dokument (v1). Cíl: produkční, reprodukovatelné RL prostředí, ve kterém agent
> jako on-call SRE diagnostikuje a opravuje incidenty v simulovaném produkčním systému.
> Splňuje zadání *Break the Agent* (AfterQuery), ale je navržené jako samostatný produkt:
> deterministický simulátor, MCP rozhraní, verifikovatelná odměna, sada exploit testů,
> held-out evaluace a pipeline pro trénink menšího modelu.
>
> Jedna práce zároveň pokrývá sponzorské challenge (Verda, Gemma, Gemini, CRACI, Aiven,
> Entire, volitelně Nemotron/Modal) — viz §15. **Tvrdé pravidlo:** evaluace a skóre
> nikdy nezávisí na externí službě; vše sponzorské je volitelné rozšíření.

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
  Agent komunikuje výhradně přes MCP. V sim kontejneru je uložen pouze SHA-256 hash
  admin tokenu (`ADMIN_TOKEN_SHA256`); samotný plaintext token je **výhradně** v
  `tests/test.sh` (který se do agent kontejneru mountuje až po skončení agenta) →
  agent nemůže volat `finalize`/`score`, ani kdyby četl konfiguraci sidecaru.
- **Determinismus (i při paralelních tool callech):** výstup = f(seed, sekvence akcí).
  MCP server vykonává volání striktně sériově přes `asyncio.Lock()` (FIFO v deterministickém
  pořadí). Oddělené RNG streamy (`traffic`, `faults`, `noise`) → *common random numbers*:
  provoz a poruchy jsou pro všechny politiky stejné, liší se jen důsledky akcí. Férové
  srovnání agent vs. reference vs. no-op na stejném seedu.
- **Stack:** Python 3.12, `uv`, oficiální `mcp` SDK (FastMCP, streamable HTTP),
  stdlib `random.Random` (žádný numpy), `pytest`. Docker + docker-compose.
- **Rollout logy:** každá epizoda → lokální JSONL (`runs/<run_id>/<episode>.jsonl`:
  tool call, argumenty, výstup, sim čas, ground-truth snapshot, skóre, tagy).
  JSONL je jediný zdroj pravdy pro report. Volitelný sink do **Aiven ClickHouse**
  (`ONCALL_CLICKHOUSE_URL`, pokud není nastaveno → nic se neodesílá) slouží pro
  analýzu napříč tisíci rolloutů (§8, §15).
- **Workflow:** vývoj a agentní práce přes **Entire** (git + agent workflow), CI na
  **CRACI** runnerech (§12).

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
    scoring.py                # reward (viz §6)
    policies.py               # noop, stop_early, reference, oracle, exploity
    cli.py                    # oncall eval / oncall report / oncall export-harbor
    logsink.py                # JSONL (vždy) + ClickHouse (volitelně)
  train/                      # Gemma fine-tune na Verdě (§11)
    build_dataset.py          # JSONL rollouty → SFT konverzace
    sft.py / grpo.py
  analysis/*.sql              # ClickHouse dotazy pro analýzu chyb (§8)
  .github/workflows/ci.yml    # runs-on: craci
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

**Čas:** 1 tick = 1 simulovaná minuta. Horizont `T = 120` ticků + epilog `E = 45`
(kratší horizont zajišťuje, že rychlost opravy / MTTR výrazně promlouvá do skóre).

**Model služby** (per služba): `replicas`, `capacity_per_replica`, `version`,
`canary_version/weight`, `has_incompatible_migration`, `config{}`, `memory_used/limit`,
`conn_pool_size`, `worker_threads`, `disk_used`, `cert_expiry_tick`, `queue_lag/dlq_enabled`,
`cache_hit_rate`, `health`. Za tick:

- **Zátěž:** request rate z denní křivky + šum; propaguje se po call grafu
  (fan-out koeficienty). Retry politika násobí zátěž na downstream při chybách
  (→ realistické retry stormy).
- **Latence a bulkhead:** `base / max(0.05, 1 − utilization)` + příspěvky downstream (p50/p99).
  Pomalý downstream bez circuit breakeru vyčerpá `worker_threads` volající služby
  (thread-pool starvation → 503 i při 0% chybovosti downstreamu).
- **Chybovost:** vlastní (bug v deployi/canary, OOM, plný disk, expirovaný cert,
  poison message ve frontě) + propagovaná z downstream (s fallbackem/circuit breakerem tlumená).
- **DB a Cache:** DB má max connections; každá replika drží `pool_size` spojení →
  škálování klientů nad limit **zhoršuje** situaci. Při nízkém `cache_hit_rate` jde
  plná zátěž do DB, která timeoutuje a brání naplnění cache (metastabilní stav).
- **Restart:** instance cold-start 2–4 ticky, vyprázdněná cache → cache stampede.

**SLI (ground truth):** v každém ticku `t` sledujeme `offered_reqs_t` a `good_reqs_t`
(obsloužené requesty bez chyby a pod latency SLO). Shedované requesty (maintenance mode,
rate limit) se počítají do `offered_reqs_t`, ale ne do `good_reqs_t`. Po překročení
15min error budgetu (kumulativní výpadek > 15 ekvivalentních minut) se ztracené requesty
váží `2×` → pomalé tápaní a vysoké MTTR prudce snižuje dostupnost.

**Topologie:** 3 šablony (e-shop, SaaS API, media pipeline), náhodné přejmenování
služeb a parametry ze seedu → agent nemůže spoléhat na zapamatování.

---

## 4. Scénáře a poruchy

Scénáře se skládají kompozičně ze 3 ortogonálních os: **Kořenová příčina (F1–F14)** ×
**Kognitivní past (Distractor)** × **Časová dynamika**.

| Rodina | Signály (vždy ≥ 2 nezávislé) | Správný zásah | Typická past / Proč frontier selže |
|---|---|---|---|
| **F1 Bad deploy** | skok chybovosti v čase deploye, stacktrace v logu | rollback služby | souběžný nevinný deploy jiné služby (red herring) |
| **F2 Memory leak** | rostoucí RSS, OOM kills (pila), latence | rollback/flag vypnutí leaku | restart „pomůže" na 20 min → epilog odhalí |
| **F3 Retry storm → DB pool** | DB conn saturace, retry metriky na upstreamu | snížit retry/backoff na upstreamu, pak DB | škálování klientů / restart DB (situaci zhorší) |
| **F4 Config/flag drift** | latence po změně flagu, audit log | vypnout flag / opravit config | rollback deploye, který nic nezměnil |
| **F5 Externí dependency** | timeouty na PSP, status zpráva | circuit breaker + fallback | rollback vlastní služby |
| **F6 Odložená expirace certu** | `WARN` v `get_events`, cert metadata | `run_maintenance(svc, "rotate_cert")` před `t_exp` | ignorování low-severity warningu → výpadek v t≈65 |
| **F7 Plný disk (logy)** | disk %, `WARN` v `get_events`, write errors | `prune_logs` + snížit log level | restart bez uvolnění místa |
| **F8 Druhá porucha mid-episode** | nový alert/zpráva od týmu v t≈45 | adaptovat, znovu triage | prohlásit incident za vyřešený po první opravě |
| **F9 Metastabilní Cache Stampede** | `cache_hit_rate` < 10 %, DB CPU 100 %, timeouty | **3 kroky:** 1. throttle/CB nebo `warm_cache`, 2. počkat na hit rate > 80 %, 3. plný provoz | pouhý restart cache/DB nebo scale appky (DB zůstane v saturaci) |
| **F10 Poison Pill ve frontě (DLQ)** | rostoucí `queue_lag`, pád workerů na stejném `msg_id` | zapnout `dlq_enabled` / `purge_dlq` v údržbě | `rollback` nebo `scale` workerů (poison message shodí i nové repliky) |
| **F11 Tichý Canary / Bimodální chyba** | celkový `error_rate` jen ~4 %, ale obří `p99` vs `p50` | shodit canary verzi / regionální flag | agent přehlédne službu s nízkým průměrným error rate |
| **F12 Thread-Pool Starvation** | `checkout` vrací 503 (plné workery), pomalá `recommendations` má **0 % chyb**, ale `p99 = 3s` | odříznout pomalou nekritickou dep přes `set_circuit_breaker(..., fallback)` | agent hledá jen `error_rate > 0` a opravuje nevinný `checkout` |
| **F13 Misleading Team Message** | zpráva v `get_events()` radí rollback nevinné služby, metriky ukazují jinam | ověřit hypotézu v metrikách, opravit skutečnou DB/config příčinu | **authority bias / sycophancy** — slepé poslechnutí lidské zprávy |
| **F14 Unmasked Downstream Cascade** | služba A zahazuje 80 % requestů; po její opravě plný provoz shodí oslabenou službu B | po opravě A počkat (`wait`), sledovat průtok do B, opravit i B | okamžitý `resolve_incident` po opravě A → kolaps B o 3 min později |

**Férovost proaktivních signálů (F6/F7):** žádné skenování naslepo — `get_status()` a
`get_events()` vracejí vedle `CRIT` alertů i 5–8 `WARN` událostí (většina neškodný šum
jako deprecation warning, mezi nimi ale i `TLS cert expires in 60m` nebo `disk > 88 %`).
Reference i frontier agent tak mají identické vodítko.

**Obtížnost:**
- `easy` (4 v judge): 1 porucha (F1, F3, F5, F7), bez pastí — sanity check, že agent rozumí nástrojům.
- `medium` (8 v judge): 1 porucha + kognitivní past (red-herring deploy, F11 canary, F12 starvation, F13 misleading message).
- `hard` (12 v judge): vícefázové plánování (F9 stampede, F10 poison queue), odmaskování druhé chyby (F14), kombinace s tikající bombou (F6) a adaptací (F8).

**Splity:**
- `dev` (veřejné seedy, 30 scénářů pro vývoj a CI exploit testy),
- `judge-fast` (pevná podmnožina 12 seedů pro rychlé ověření),
- `judge` (pevný stratifikovaný seznam **24 seedů**: 4 easy, 8 medium, 12 hard — publikovaný pro hlavní report a úzké bootstrap CI),
- `heldout` (seedy z tajného salt, 100 scénářů — jen pro finální reporty a eval malého modelu).

**Fairness invariant (testováno):** každá porucha emituje ≥ 2 pozorovatelné signály
dostupné přes nástroje; non-privileged reference policy každý scénář řeší
se skóre ≥ 0.8. Scénář, který tím neprojde, se nesmí dostat do suite.

---

## 5. MCP rozhraní

Každé volání stojí simulovaný čas (svět mezitím běží). Výstupy jsou realistické:
šum, stránkování, truncace na N řádků. Aby názvy nástrojů neprozrazovaly typ poruchy
(*tool-schema leakage*), jsou údržbové zásahy sjednocené pod obecný nástroj.

**Pozorování (1 min, není-li uvedeno jinak)**

| Tool | Popis |
|---|---|
| `get_status()` | čas, zbývající horizont, aktivní `CRIT`/`WARN` alerty, kumulativní infra spend |
| `get_events(since)` | nové alerty, `WARN` notifikace, zprávy od jiných týmů (vč. F13), deploye |
| `get_topology()` | služby, call graf, kritičnost větví a DB/cache/queue vazby |
| `get_metrics(services[], window)` | pro 1 až 5 služeb najednou vrátí všechny metriky: `rps`, `error_rate`, `p50`, `p99`, `cpu`, `mem`, `conns`, `worker_util`, `disk`, `retries`, `queue_lag`, `cache_hit_rate` |
| `get_logs(service, level, grep, limit)` | 95 % šum, relevantní řádky jen u příčiny |
| `get_traces(endpoint, n)` (2 min) | vzorky trace se span latencemi/chybami a `message_id` |
| `get_deploys(service?)` | historie verzí, canary váhy, `has_schema_migration` a `reversible: bool` |
| `get_config(service)` / `get_flags()` | aktuální konfigurace (vč. retry, DLQ, poolů), feature flagy, audit log |
| `get_runbook(topic)` | obecné SRE runbooky (vč. varování před nekompatibilní migrací a stampede) |

**Akce**

| Tool | Čas | Pozn. |
|---|---|---|
| `rollback(service, version)` | 5 min | rollback nevinné služby = kolaterál; při `reversible: false` → ztráta dat |
| `restart(service)` | 3 min | cold start, vyprázdní lokální cache |
| `scale(service, replicas)` | 4 min | ovlivní kumulativní spend a DB spojení |
| `set_config(service, key, value)` | 2 min | např. `max_retries`, `timeout_ms`, `dlq_enabled`, `rate_limit_rps`; validace rozsahu |
| `set_flag(flag, on)` | 1 min | vypnutí/zapnutí feature flagu nebo canary |
| `set_circuit_breaker(service, dep, mode)` | 2 min | `closed/open/fallback` |
| `failover_db()` | 6 min | bez repliky v sync → ztráta dat (tvrdá penalizace) |
| `run_maintenance(service, action)` | 3 min | enum: `rotate_cert`, `prune_logs`, `purge_dlq`, `warm_cache`, `vacuum_db`, `flush_dns`, `rebalance_shards`, `compact_wal` (nevhodná akce pod zátěží zhorší latenci) |
| `wait(minutes)` | n | explicitní pozorování vývoje (např. po opravě bottlenecku u F14) |
| `resolve_incident(root_causes[], summary)` | — | **ukončí** interakci; `root_causes` = seznam `{service, fault_class}` z enumu |

Po `resolve_incident` (nebo vyčerpání horizontu `T = 120` / max 150 volání) simulátor
**dojede zbytek horizontu bez akcí a pak epilog** (`E = 45` min, provoz 1.5×).
Ukončit dřív tedy nic nezastaví — svět běží dál, jako v produkci.

---

## 6. Reward

Vše z ground truth simulátoru, deterministicky. Dostupnost `U(π)` je vážená počtem
requestů (epilog s 1.5× provozem má přirozeně vyšší váhu) a penalizuje překročení
15min error budgetu dvojnásobnou vahou ztracených requestů (důraz na nízké MTTR):

```
w_t       = 1.0 pokud kumulativní výpadek ≤ 15 min, jinak 2.0 (error budget burn)
U(π)      = 1 − (Σ_t w_t · (offered_reqs_t − good_reqs_t)) / (Σ_t w_t · offered_reqs_t)
R_avail   = clip((U(agent) − U(noop)) / (U(oracle) − U(noop)), 0, 1)
R_fixed   = podíl root-cause poruch skutečně odstraněných na konci epilogu
            (maskovaná porucha, např. restartovaný leak nebo nevyřešená F14, = 0)
R_diag    = 1 pokud množina root_causes == ground truth, jinak 0 (jediný pokus)

score_raw = 0.60·R_avail + 0.30·R_fixed + 0.10·R_diag
score     = clip(score_raw · M_dataloss − P_collateral − P_cost, 0, 1)

M_dataloss   = 0.25 při ztrátě dat (failover bez sync, rollback migrace s reversible=false), jinak 1.0
P_collateral = 0.10 za každý zbytečný destruktivní zásah (rollback/restart/škodlivá údržba zdravé služby)
P_cost       = 0.10 pokud průměrný (kumulativní) spend přes [0, T+E) > 1.3× baseline
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
| Restart všeho dokola | cold starty + stampede; leak se vrátí v epilogu; kolaterál `-0.10`/služba | < 0.15 |
| Scale všeho na max (i se scale-down před koncem) | kumulativní spend penalizace; F3 se zhorší (DB spojení); nefixuje bugy | < 0.2 |
| Rollback všeho | kolaterál `-0.10`/služba, ireverzibilní migrace → `M_dataloss = 0.25` | < 0.1 |
| Zavolat všechny `run_maintenance` akce | `vacuum_db`/`rebalance_shards` pod zátěží shodí SLO + kolaterál | < 0.15 |
| Maintenance mode / shed traffic | shedované requesty se počítají jako neúspěšné | ≈ 0 |
| Vypnout health checky / alerty | skóre jde z ground truth, ne z pozorovaných metrik | beze změny |
| Hádat všechny root causes | `==` množin, jeden pokus | 0 za diag |
| Injekce do `summary` | `summary` se neboduje, žádný LLM judge | 0 |
| Čtení scénáře / seedu / tokenu | jen v sidecaru; v sidecaru je pouze SHA-256 hash tokenu | — |
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
| `frontier` | MCP přes Harbor/OpenCode | měřený agent (viz níže) |
| `gemma-base` / `gemma-ft` | MCP přes Harbor/OpenCode (vLLM endpoint) | malý model před/po tréninku (§11) |

**Frontier agenti** (model ID jako parametr `--model`, ne natvrdo v kódu):
- **Gemini** — primární studovaný frontier agent (3 runy na judge suite) + analýza
  jeho chyb v reportu (Gemini API challenge).
- Model dodaný AfterQuery k harnessu — pokud se liší od Gemini, běží také 3×.
- **Nemotron** — volitelně druhý agent, až když pipeline běží (free tier je
  rate-limitovaný, nesmí blokovat hlavní eval).

**Reference policy (expertní runbook, deterministická):**
1. **Triage:** `get_status()` + `get_topology()` → dávkově `get_metrics()` od vstupních
   SLI po call grafu dolů (sleduje nejen `error_rate`, ale i `p99 vs p50` pro canary F11
   a `worker_util` + downstream `p99` pro thread starvation F12).
2. **Korelace a ověření hypotéz:** deploye/flag/config změny v ±5 min od začátku anomálie;
   zprávy od týmů z `get_events()` (F13) vždy nejprve ověří proti metrikám dané služby.
3. **Klasifikace a vícefázový zásah:** podle signatury signálů (§4) provede zásah (u F3
   nejdřív sníží retry, u F9 nejdřív `warm_cache`/throttle a čeká na obnovu hit-rate).
4. **Ověření a sledování kaskád (F14):** `wait` + kontrola, že metriky drží a že
   obnovený průtok neshodil downstream službu.
5. **Triage `WARN` událostí:** projde `WARN` notifikace z `get_events()` (odfiltruje
   neškodný šum, vyřeší blížící se expiraci certu F6 / plný disk F7) a reaguje na F8.
6. `resolve_incident` až po celkové stabilizaci.

Reference je záměrně jednoduchá a čitelná — její síla vychází ze správného postupu,
ne z privilegovaných dat. Spouští se přes **stejný MCP server** (in-process klient),
takže se do Harbor exportuje jako `solution/solve.sh` (oracle agent v Harboru).

---

## 8. Analýza chyb (Meaningful difficulty)

Automatické tagy z trajektorie porovnané s ground truth:

| Tag | Detekce | Rozhodnutí, které agent udělal špatně |
|---|---|---|
| `symptom_fix` | první zásah na službě, která není root cause (např. F12) | zaměnil symptom/upstream za příčinu |
| `masked_fix` | restart bez odstranění příčiny, regrese v epilogu (F2) | neověřil trvalost opravy |
| `herring_followed` | zásah na red-herring deploy | korelace ≠ kauzalita |
| `authority_bias` | rollback nevinné služby po zavádějící zprávě v `get_events` (F13) | slepě uvěřil textu bez kontroly metrik |
| `unmasked_cascade_missed` | resolve hned po opravě A, zatímco B pod plnou zátěží padá (F14) | nezkontroloval systém po uvolnění bottlenecku |
| `canary_missed` | ignorování služby s nízkým průměrným error_rate, ale vysokou p99 (F11) | sledoval jen průměry místo distribuce |
| `over_investigation` | čas do 1. správného zásahu > 2× reference | špatná cena informace vs. čekání |
| `premature_resolve` | resolve s aktivní poruchou | nepočkal na ověření |
| `missed_event` | neřešil `WARN` (F6/F7) nebo nečetl `get_events` po t≈45 (F8) | neadaptoval se na dostupné varování / novou info |
| `collateral` | zbytečný destruktivní zásah / nevhodný `run_maintenance` | chybí risk management |
| `wrong_order` | např. scale DB před zastavením retry stormu (F3) nebo stampede (F9) | chybí vícefázové plánování |

Report ukazuje distribuci tagů per model + 2–3 anotované trajektorie (s výňatkem, kde
informace pro správné rozhodnutí *byla* dostupná — odkaz na konkrétní tool output).

Tagy se počítají z lokálního JSONL (report funguje offline). Pro hlubší analýzu přes
tisíce rolloutů (Gemini vs. Nemotron vs. Gemma před/po, per rodina poruchy, čas do
1. správného zásahu) se stejná data nahrají do **Aiven ClickHouse**; dotazy jsou
v `analysis/*.sql` a jejich výstupy (CSV/grafy) se commitují do `results/`, takže
závěry jsou ověřitelné i bez přístupu do ClickHouse.

---

## 9. Evaluace a reprodukovatelnost

**Jeden příkaz:**

```bash
make judge        # = uv run oncall judge --suite judge --agent-runs 3       (24 scénářů)
make judge-fast   # = uv run oncall judge --suite judge-fast --agent-runs 3  (12 scénářů, rychlý běh)
```

Spustí: build kontejnerů → `noop`, `stop_early`, `reference`, 3× frontier agent přes
`harbor run` na judge scénářích → `results/<timestamp>/report.md` + `report.json`.

**Bez LLM (rychlé, CI):** `uv run oncall eval --policy reference --suite dev`

**Report obsahuje:**
- mean ± std per politika, per obtížnost (`easy`/`medium`/`hard`), per rodina poruchy (F1–F14)
- gap `reference − agent` s 95% bootstrap CI přes scénáře; per-run konzistence
  (gap musí být kladný v každém ze 3 runů)
- exploit matice, distribuce chybových tagů
- hashe: git commit, `uv.lock`, image digest, seed list, model ID + parametry

**Determinismus:** `test_determinism.py` — stejný seed + akce ⇒ identický hash
trajektorie a skóre (napříč běhy i platformami). Variance tedy pochází jen z agenta.

**Kalibrační cíle (hypotézy k ověření, ne naměřené výsledky):**
reference ≥ 0.85, frontier na `easy` ≥ 0.75 (důkaz férovosti), frontier celkově ≤ 0.55,
všechny baseliny/exploity ≤ 0.20.
Smyčka: pokud frontier > cíl → přidat kompoziční pasti F9–F14 (ne zatajovat info);
pokud reference < 0.8 na scénáři → scénář je nefér, opravit nebo vyřadit.

---

## 10. Harbor integrace

`oncall export-harbor --suite judge` vygeneruje pro každý scénář:

```
harbor/tasks/<id>/
  task.toml               # timeouty, MCP server endpoint sidecaru
  instruction.md          # role on-call SRE, cíl, popis nástrojů a pravidel času/odměny
  environment/
    Dockerfile            # agent kontejner (bez scénáře a bez plaintext tokenu)
    docker-compose.yaml   # sidecar oncall-sim, SCENARIO_SEED a ADMIN_TOKEN_SHA256 v sidecar env
  solution/solve.sh       # spustí reference policy přes MCP
  tests/test.sh           # obsahuje plaintext admin token → finalize → reward.txt + breakdown
```

`instruction.md` popisuje **pravidla** úplně a pravdivě (čas běží, epilog s 1.5× provozem
existuje, error budget po 15 min bolí 2×, jak se počítá skóre). Žádné triky ve formulaci
— obtížnost je v rozhodování.

> Otevřené: přesné schéma MCP konfigurace v `task.toml` a podpora docker-compose
> sidecaru ověřit proti starter kitu Harboru. Pokud Harbor sidecar nepodporuje,
> `oncall-sim` poběží na dedikovaném interním procesu se zašifrovaným seedem, kde klíč k
> rozšifrování a vyhodnocení drží až `tests/test.sh` (nikdy se nespoléháme jen na
> unixová práva `0700` uvnitř kontejneru, kde má agent `root`).

---

## 11. Trénink menšího modelu (stretch = AfterQuery tiebreaker + Verda + Gemma)

Jedna pipeline, tři challenge: AfterQuery tiebreaker („malý model se zlepší po tréninku
na zkušenosti z prostředí"), Verda („tisíce rolloutů + fine-tune menšího modelu")
a Gemma (Gemma je ten malý model).

**Compute:** **Verda** jako hlavní (rollouty + fine-tune + vLLM serving). **Modal** jen jako
fallback, pokud Verda nebude dostupná — ne obojí paralelně.

1. **Rollouty na Verdě:** `train` split (oddělený od `dev`/`judge`/`heldout`),
   tisíce epizod: `reference` (bez LLM, levné), Gemma base s vzorkováním
   (temperature > 0, N vzorků na scénář), frontier runy kde jsou k dispozici.
   Vše přes stejný MCP server, logy do JSONL (+ ClickHouse).
2. **Data:** `train/build_dataset.py` — trajektorie se skóre ≥ 0.8 (reference +
   rejection-sampled Gemma/frontier) renderované jako tool-call konverzace v chat
   formátu Gemmy. Deduplikace, žádný seed z `heldout`/`judge`.
3. **Model a Serving:** **Gemma** (např. `gemma-3-12b-it` / `gemma-3-4b-it` podle
   pravidel Gemma challenge), LoRA SFT. Pro evaluaci v Harbor/OpenCode se Gemma
   nasadí na Verdě přes **vLLM s `--enable-auto-tool-choice`** (OpenAI-compatible
   endpoint), takže harness volá `gemma-base` i `gemma-ft` identicky jako frontier modely.
4. **RL (volitelně):** GRPO s rewardem prostředí — simulátor je rychlý, skóre je
   dense díky R_avail. Rollouty generované na Verdě.
5. **Evaluace:** `gemma-base` vs. `gemma-sft` (vs. `gemma-grpo`) na `heldout` seedech
   **a** na held-out rodině poruch (např. vynechat F12/F14 z tréninku → kontrola, že se
   model neučí nazpaměť scénáře, ale kauzální postup). 3 runy, bootstrap CI. Metriky:
   skóre + distribuce chybových tagů (očekávaný pokles `masked_fix`, `premature_resolve`,
   `authority_bias`).
6. **Dokumentace:** `train/README.md` (data, hyperparametry, compute, výsledky)
   + shrnutí postnuté na Verda Discord (požadavek Verda challenge). Váhy LoRA
   adaptéru publikované, aby šlo `gemma-ft` eval zopakovat.

---

## 12. Testy a kvalita

| Test | Co hlídá |
|---|---|
| `test_determinism.py` | reprodukovatelnost (vč. FIFO serializace paralelních tool callů) |
| `test_exploits.py` | každá exploit politika < práh na všech dev seedech |
| `test_solvability.py` | reference ≥ 0.8 a každá porucha F1–F14 má ≥ 2 signály |
| `test_scoring.py` | noop = 0, oracle = 1, monotonie (oprava dřív ⇒ skóre ≥), kumulativní spend |
| `test_server.py` | schema validace, SHA-256 auth admin API, agent nevidí ground truth |

CI (GitHub Actions, `runs-on: craci` — CRACI challenge):

```yaml
jobs:
  test:  { runs-on: craci, steps: [uv sync --frozen, pytest] }
  eval:  # důkaz reprodukovatelnosti pro „Craft"
    runs-on: craci
    steps:
      - uv run oncall eval --policy reference,noop,stop_early,exploit_* --suite judge
      - uv run oncall report --compare results/baseline.json   # fail při odchylce skóre
  images: { runs-on: craci, steps: [docker build] }
```

Eval job běží bez LLM a bez secrets → deterministické politiky musí v CI dát
**přesně** stejná skóre jako commitnutý `results/baseline.json`. Každý push tak
automaticky dokazuje reprodukovatelnost. Release = tag + commitnutý report v `results/`.

---

## 13. Milníky

1. **Sim jádro** — engine, F1–F5, scoring (vč. error budget vážení a kumulativního spendu), noop/oracle, determinismus test.
2. **MCP server** — dávkové `get_metrics`, sjednocené `run_maintenance`, FIFO lock, SHA-256 admin API, lokální klient.
3. **Reference policy + exploit suite** — solvability a exploit testy zelené.
4. **Harbor export + `make judge-fast`** — end-to-end s jedním Gemini runem; CRACI CI s eval jobem.
5. **F6–F14, obtížnosti (`easy`/`medium`/`hard`), kalibrace** — iterace podle chybových tagů.
6. **Report + demo (`make judge` na 24 scénářích)** — 3× Gemini (+ AfterQuery model), CI gap, anotované trajektorie, ClickHouse analýza.
7. **Stretch** — rollouty na Verdě, Gemma SFT (+ GRPO) přes vLLM, eval na heldout, Discord shrnutí.
8. **Volitelné** — Nemotron jako druhý agent.

## 14. Demo (10 min)

1. (1 min) Problém a proč on-call (reálný, cenný, kauzální).
2. (3 min) Živě: Gemini na `hard` scénáři (např. F2 leak + F13 misleading message nebo F14 kaskáda) → nachytá se na past nebo předčasně uzavře, epilog odhalí regresi. Vedle reference: ověření hypotézy a trvalá oprava.
3. (2 min) Reward + exploit matice (živě spustit `exploit_restart_all`, `stop_early`).
4. (2 min) Výsledky: gap s CI přes 24 scénářů, chybové tagy, odkaz na místo v trajektorii, kde informace byla dostupná.
5. (2 min) Reprodukce jedním příkazem (+ zelený CRACI eval job) + Gemma před/po.

---

## 15. Sponzorské challenge

| Challenge | Co přesně děláme | Kde v designu | Závislost evalu |
|---|---|---|---|
| **Verda** | hlavní compute: tisíce rolloutů + Gemma fine-tune + vLLM; shrnutí na jejich Discord | §11 | žádná |
| **Gemma** | Gemma = malý model, před/po tréninku na zkušenosti z prostředí | §7, §11 | žádná (`gemma-*` jsou extra politiky) |
| **Gemini API** | Gemini = primární studovaný frontier agent, analýza jeho chyb | §7, §8 | jen pro agent runy (harness), ne pro skóre |
| **CRACI** | `runs-on: craci`, eval job jako důkaz reprodukovatelnosti | §12 | žádná (CI je navíc) |
| **Aiven** | rollout logy v Aiven ClickHouse, SQL analýza chyb | §2, §8 | žádná (JSONL je zdroj pravdy) |
| **Entire** | git + agent workflow týmu | §2 | žádná |
| **Nemotron** | volitelně druhý frontier agent | §7 | žádná |
| **Modal** | jen fallback compute za Verdu | §11 | žádná |

**Vynecháváme:** Solana, Cloudinary, MongoDB, ElevenLabs, Arduino/Atech, Oxylabs,
Context.dev (Tiger Data nahrazuje Aiven). Živá web data by rozbila reprodukovatelnost
— judges spouštějí eval sami.

**Pravidla integrace:**
- `make judge` musí projít na čistém stroji bez jakéhokoli sponzorského účtu/klíče.
  Test: CI eval job běží bez secrets.
- Každá integrace je za env proměnnou nebo samostatným příkazem; chybějící
  konfigurace = tichý skip, ne chyba.
- Žádná sponzorská služba nesmí ovlivnit skóre, seedy ani scénáře.

---

## Otevřené otázky

- Který frontier model dodá AfterQuery a limity harnessu (max turns, timeout) — ovlivní
  `T` a cenu volání. Jak Gemini připojit do Harbor/OpenCode (provider config).
- Gemma challenge: povolená verze/velikost a forma odevzdání; Verda: výše kreditů
  a dostupné GPU → strop na počet rolloutů a GRPO.
- MCP schéma v Harbor `task.toml` a sidecar podpora (viz §10).
- Čas běhu `judge` (24 scénářů × 3 runy) vs. `judge-fast` (12 × 3) — změřit po milníku 4.
