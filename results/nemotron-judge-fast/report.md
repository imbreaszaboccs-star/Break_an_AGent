# OnCall report: suite `judge-fast`

## Score per policy (mean ± std)

| policy | n | all | easy | medium | hard |
|---|---|---|---|---|---|
| reference | 12 | 0.977 ± 0.014 | 0.976 ± 0.004 | 0.979 ± 0.008 | 0.977 ± 0.020 |
| noop | 12 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 12 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b | 36 | 0.789 ± 0.215 | 0.934 ± 0.061 | 0.857 ± 0.098 | 0.695 ± 0.261 |

## Score per fault family (mean ± std)

| policy | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 0.973 ± 0.000 | - | 0.978 ± 0.000 | - | - | 0.997 ± 0.000 | - | - | 0.985 ± 0.007 | 0.969 ± 0.029 | 0.967 ± 0.000 | 0.985 ± 0.000 | 0.982 ± 0.003 | 0.957 ± 0.000 |
| noop | 0.000 ± 0.000 | - | 0.000 ± 0.000 | - | - | 0.000 ± 0.000 | - | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 0.000 ± 0.000 | - | 0.000 ± 0.000 | - | - | 0.000 ± 0.000 | - | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b | 0.975 ± 0.004 | - | 0.893 ± 0.063 | - | - | 0.891 ± 0.000 | - | - | 0.640 ± 0.162 | 0.630 ± 0.355 | 0.922 ± 0.063 | 0.741 ± 0.039 | 0.882 ± 0.087 | 0.742 ± 0.338 |

## Gap reference - agent (95% bootstrap CI over scenarios)

- agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b: 0.188 [0.115, 0.267] over 12 scenarios; per run: 0.181, 0.222, 0.162 (positive in every run)

## Annotated failures: agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b

### har-f10-2017: score 0.248, tags: missed_event
- truth: [['order-worker', 'poison_message'], ['purchase-api', 'config_drift']] · fixed: [True, False] · resolved as: [['order-worker', 'poison_message']]
- first intervention: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #15, t=14) — necessary
- `poison_message` on `order-worker`: signal first visible in `get_metrics(services=['gateway', 'purchase-api', 'order-svc', 'orders-queue', 'order-worker'], window=10)` (call #4, t=3); correct fix: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #15, t=14)
- `config_drift` on `purchase-api`: appeared at t=44, after the agent had already resolved at t=33 (the instruction says faults can arrive mid-shift)

### har-f14-2014: score 0.353, tags: missed_event
- truth: [['upload', 'bad_deploy'], ['encoder-coord', 'under_provisioned'], ['thumbnails', 'config_drift']] · fixed: [True, True, False] · resolved as: [['encoder-coord', 'under_provisioned'], ['upload', 'bad_deploy']]
- first intervention: `rollback(service='upload', version='v2.7.0')` (call #7, t=6) — necessary
- `bad_deploy` on `upload`: signal first visible in `get_metrics(services=['upload', 'media-edge', 'encoder-coord'], window=10)` (call #4, t=3); correct fix: `rollback(service='upload', version='v2.7.0')` (call #7, t=6)
- `under_provisioned` on `encoder-coord`: signal first visible in `get_events()` (call #2, t=1); correct fix: `scale(service='encoder-coord', replicas=6)` (call #12, t=20)
- `config_drift` on `thumbnails`: signal first visible in never; correct fix: never

### har-f9-2016: score 0.389, tags: symptom_fix, collateral, over_investigation
- truth: [['redis-cache', 'cache_stampede'], ['checkout', 'cert_expiry']] · fixed: [True, True] · resolved as: [['catalog-svc', 'retry_storm'], ['redis-cache', 'cache_stampede']]
- first intervention: `set_config(service='catalog-svc', key='max_retries', value=0)` (call #19, t=18) — NOT a fix step and not on a faulty node
- `cache_stampede` on `redis-cache`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='redis-cache', action='warm_cache')` (call #22, t=24)
- `cert_expiry` on `checkout`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='checkout', action='rotate_cert')` (call #34, t=61)


## Failure tags

- reference: none
- noop: canary_missed=1, missed_event=6
- stop_early: canary_missed=1, missed_event=6, premature_resolve=12
- agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b: collateral=9, missed_event=3, over_investigation=11, symptom_fix=5

## Hashes

- git commit: 6ef3277ffaaeca23df6bdac5e5d3d62b4103bf39
- uv.lock sha256: f81f22d9da9bbd58e877f95c5633af61a238b825a62fa9ef3562731db8e62d7d
- scenarios (12): eas-f1-2000, eas-f3-2001, med-f12-2004, med-f13-2005, med-f13-2006, med-f11-2007, har-f9-2012, har-f10-2013, har-f14-2014, har-f6-2015, har-f9-2016, har-f10-2017
