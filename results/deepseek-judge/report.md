# OnCall report: suite `judge`

## Score per policy (mean ± std)

| policy | n | all | easy | medium | hard |
|---|---|---|---|---|---|
| reference | 24 | 0.979 ± 0.011 | 0.978 ± 0.004 | 0.980 ± 0.010 | 0.978 ± 0.014 |
| noop | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:verda:deepseek-4-1-flash-1017 | 72 | 0.851 ± 0.195 | 0.922 ± 0.062 | 0.947 ± 0.053 | 0.764 ± 0.241 |

## Score per fault family (mean ± std)

| policy | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 0.974 ± 0.001 | 1.000 ± 0.000 | 0.978 ± 0.000 | 0.977 ± 0.000 | 0.981 ± 0.000 | 0.991 ± 0.008 | 0.981 ± 0.000 | 0.976 ± 0.000 | 0.983 ± 0.006 | 0.974 ± 0.022 | 0.970 ± 0.004 | 0.985 ± 0.000 | 0.982 ± 0.003 | 0.967 ± 0.011 |
| noop | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:verda:deepseek-4-1-flash-1017 | 0.978 ± 0.003 | 0.959 ± 0.053 | 0.863 ± 0.009 | 0.884 ± 0.074 | 0.911 ± 0.087 | 0.972 ± 0.043 | 0.940 ± 0.060 | 0.701 ± 0.325 | 0.633 ± 0.242 | 0.722 ± 0.293 | 0.966 ± 0.009 | 0.906 ± 0.083 | 0.957 ± 0.048 | 0.820 ± 0.151 |

## Gap reference - agent (95% bootstrap CI over scenarios)

- agent:verda:deepseek-4-1-flash-1017: 0.127 [0.072, 0.195] over 24 scenarios; per run: 0.120, 0.132, 0.130 (positive in every run)

## Annotated failures: agent:verda:deepseek-4-1-flash-1017

### har-f9-2020: score 0.214, tags: premature_resolve, collateral, missed_event
- truth: [['redis-media', 'cache_stampede'], ['ingest-api', 'memory_leak']] · fixed: [True, False] · resolved as: [['metadata', 'retry_storm'], ['redis-media', 'cache_stampede']]
- first intervention: `run_maintenance(service='redis-media', action='warm_cache')` (call #14, t=13) — necessary
- `cache_stampede` on `redis-media`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='redis-media', action='warm_cache')` (call #14, t=13)
- `memory_leak` on `ingest-api`: signal first visible in `get_metrics(services=['frontline', 'playlist', 'transcode-svc', 'ingest-api'], window=5)` (call #35, t=77); correct fix: never

### har-f10-2017: score 0.256, tags: missed_event
- truth: [['order-worker', 'poison_message'], ['purchase-api', 'config_drift']] · fixed: [True, False] · resolved as: [['order-worker', 'poison_message']]
- first intervention: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #11, t=10) — necessary
- `poison_message` on `order-worker`: signal first visible in `get_metrics(services=['order-worker', 'orders-queue', 'order-svc', 'purchase-api', 'gateway'], window=15)` (call #5, t=4); correct fix: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #11, t=10)
- `config_drift` on `purchase-api`: appeared at t=44, after the agent had already resolved at t=26 (the instruction says faults can arrive mid-shift)

### har-f9-2012: score 0.287, tags: collateral, over_investigation
- truth: [['redis-main', 'cache_stampede'], ['report-svc', 'config_drift']] · fixed: [True, True] · resolved as: [['redis-main', 'cache_stampede'], ['report-svc', 'bad_deploy']]
- first intervention: `run_maintenance(service='redis-main', action='warm_cache')` (call #19, t=19) — necessary
- `cache_stampede` on `redis-main`: signal first visible in `get_events(since=0)` (call #3, t=2); correct fix: `run_maintenance(service='redis-main', action='warm_cache')` (call #19, t=19)
- `config_drift` on `report-svc`: signal first visible in `get_metrics(services=['report-svc', 'usage-meter'], window=8)` (call #43, t=72); correct fix: `set_flag(flag='fast-ranker', on=False)` (call #48, t=77)


## Failure tags

- reference: none
- noop: canary_missed=2, missed_event=13
- stop_early: canary_missed=2, missed_event=13, premature_resolve=24
- agent:verda:deepseek-4-1-flash-1017: collateral=14, missed_event=8, over_investigation=8, premature_resolve=3, symptom_fix=6

## Hashes

- git commit: bbab5dce1824d4a9fa143d6a3a7a9beba2d29e51
- uv.lock sha256: f81f22d9da9bbd58e877f95c5633af61a238b825a62fa9ef3562731db8e62d7d
- scenarios (24): eas-f1-2000, eas-f3-2001, eas-f5-2002, eas-f7-2003, med-f12-2004, med-f13-2005, med-f13-2006, med-f11-2007, med-f1-2008, med-f2-2009, med-f4-2010, med-f11-2011, har-f9-2012, har-f10-2013, har-f14-2014, har-f6-2015, har-f9-2016, har-f10-2017, har-f14-2018, har-f8-2019, har-f9-2020, har-f10-2021, har-f14-2022, har-f6-2023
