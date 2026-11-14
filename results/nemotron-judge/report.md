# OnCall report: suite `judge`

## Score per policy (mean ± std)

| policy | n | all | easy | medium | hard |
|---|---|---|---|---|---|
| reference | 24 | 0.979 ± 0.011 | 0.978 ± 0.004 | 0.980 ± 0.010 | 0.978 ± 0.014 |
| noop | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b | 72 | 0.840 ± 0.183 | 0.891 ± 0.060 | 0.904 ± 0.062 | 0.781 ± 0.239 |

## Score per fault family (mean ± std)

| policy | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 0.974 ± 0.001 | 1.000 ± 0.000 | 0.978 ± 0.000 | 0.977 ± 0.000 | 0.981 ± 0.000 | 0.991 ± 0.008 | 0.981 ± 0.000 | 0.976 ± 0.000 | 0.983 ± 0.006 | 0.974 ± 0.022 | 0.970 ± 0.004 | 0.985 ± 0.000 | 0.982 ± 0.003 | 0.967 ± 0.011 |
| noop | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b | 0.961 ± 0.041 | 0.868 ± 0.097 | 0.855 ± 0.009 | 0.874 ± 0.060 | 0.871 ± 0.060 | 0.938 ± 0.056 | 0.857 ± 0.013 | 0.890 ± 0.088 | 0.586 ± 0.251 | 0.826 ± 0.225 | 0.920 ± 0.050 | 0.878 ± 0.060 | 0.913 ± 0.064 | 0.791 ± 0.255 |

## Gap reference - agent (95% bootstrap CI over scenarios)

- agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b: 0.138 [0.088, 0.200] over 24 scenarios; per run: 0.104, 0.152, 0.159 (positive in every run)

## Annotated failures: agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b

### har-f9-2020: score 0.000, tags: premature_resolve, collateral, missed_event
- truth: [['redis-media', 'cache_stampede'], ['ingest-api', 'memory_leak']] · fixed: [True, False] · resolved as: [['redis-media', 'cache_stampede']]
- first intervention: `run_maintenance(service='redis-media', action='warm_cache')` (call #14, t=13) — necessary
- `cache_stampede` on `redis-media`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='redis-media', action='warm_cache')` (call #14, t=13)
- `memory_leak` on `ingest-api`: signal first visible in `get_metrics(services=['accounts', 'ingest-api'], window=10)` (call #27, t=46); correct fix: never

### har-f10-2017: score 0.258, tags: missed_event
- truth: [['order-worker', 'poison_message'], ['purchase-api', 'config_drift']] · fixed: [True, False] · resolved as: [['order-worker', 'poison_message']]
- first intervention: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #10, t=9) — necessary
- `poison_message` on `order-worker`: signal first visible in `get_metrics(services=['gateway', 'purchase-api', 'order-svc', 'orders-queue', 'order-worker'], window=10)` (call #4, t=3); correct fix: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #10, t=9)
- `config_drift` on `purchase-api`: appeared at t=44, after the agent had already resolved at t=27 (the instruction says faults can arrive mid-shift)

### har-f14-2014: score 0.346, tags: premature_resolve, missed_event
- truth: [['upload', 'bad_deploy'], ['encoder-coord', 'under_provisioned'], ['thumbnails', 'config_drift']] · fixed: [True, True, False] · resolved as: [['encoder-coord', 'under_provisioned'], ['upload', 'bad_deploy']]
- first intervention: `rollback(service='upload', version='v2.7.0')` (call #7, t=6) — necessary
- `bad_deploy` on `upload`: signal first visible in `get_metrics(services=['upload', 'media-edge', 'encoder-coord'], window=10)` (call #4, t=3); correct fix: `rollback(service='upload', version='v2.7.0')` (call #7, t=6)
- `under_provisioned` on `encoder-coord`: signal first visible in `get_events()` (call #2, t=1); correct fix: `scale(service='encoder-coord', replicas=6)` (call #20, t=37)
- `config_drift` on `thumbnails`: signal first visible in never; correct fix: never


## Failure tags

- reference: none
- noop: canary_missed=2, missed_event=13
- stop_early: canary_missed=2, missed_event=13, premature_resolve=24
- agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b: collateral=13, missed_event=5, over_investigation=19, premature_resolve=2, symptom_fix=7

## Hashes

- git commit: 1a340134f39a8d28f71938cbd7fc0c5f870e4a90
- uv.lock sha256: f81f22d9da9bbd58e877f95c5633af61a238b825a62fa9ef3562731db8e62d7d
- scenarios (24): eas-f1-2000, eas-f3-2001, eas-f5-2002, eas-f7-2003, med-f12-2004, med-f13-2005, med-f13-2006, med-f11-2007, med-f1-2008, med-f2-2009, med-f4-2010, med-f11-2011, har-f9-2012, har-f10-2013, har-f14-2014, har-f6-2015, har-f9-2016, har-f10-2017, har-f14-2018, har-f8-2019, har-f9-2020, har-f10-2021, har-f14-2022, har-f6-2023
