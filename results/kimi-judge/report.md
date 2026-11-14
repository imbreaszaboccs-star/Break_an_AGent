# OnCall report: suite `judge`

## Score per policy (mean ± std)

| policy | n | all | easy | medium | hard |
|---|---|---|---|---|---|
| reference | 24 | 0.979 ± 0.011 | 0.978 ± 0.004 | 0.980 ± 0.010 | 0.978 ± 0.014 |
| noop | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:verda:kimi-k3-1-pro | 72 | 0.874 ± 0.182 | 0.922 ± 0.167 | 0.957 ± 0.038 | 0.802 ± 0.215 |

## Score per fault family (mean ± std)

| policy | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 0.974 ± 0.001 | 1.000 ± 0.000 | 0.978 ± 0.000 | 0.977 ± 0.000 | 0.981 ± 0.000 | 0.991 ± 0.008 | 0.981 ± 0.000 | 0.976 ± 0.000 | 0.983 ± 0.006 | 0.974 ± 0.022 | 0.970 ± 0.004 | 0.985 ± 0.000 | 0.982 ± 0.003 | 0.967 ± 0.011 |
| noop | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:verda:kimi-k3-1-pro | 0.977 ± 0.002 | 0.988 ± 0.007 | 0.959 ± 0.008 | 0.956 ± 0.005 | 0.970 ± 0.005 | 0.956 ± 0.063 | 0.783 ± 0.338 | 0.554 ± 0.361 | 0.734 ± 0.134 | 0.832 ± 0.226 | 0.966 ± 0.005 | 0.863 ± 0.005 | 0.970 ± 0.011 | 0.820 ± 0.226 |

## Gap reference - agent (95% bootstrap CI over scenarios)

- agent:verda:kimi-k3-1-pro: 0.105 [0.060, 0.158] over 24 scenarios; per run: 0.130, 0.069, 0.116 (positive in every run)

## Annotated failures: agent:verda:kimi-k3-1-pro

### har-f10-2017: score 0.250, tags: missed_event
- truth: [['order-worker', 'poison_message'], ['purchase-api', 'config_drift']] · fixed: [True, False] · resolved as: [['order-worker', 'poison_message']]
- first intervention: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #14, t=13) — necessary
- `poison_message` on `order-worker`: signal first visible in `get_metrics(services=['gateway', 'purchase-api', 'order-svc', 'orders-queue', 'order-worker'], window=15)` (call #4, t=3); correct fix: `set_config(service='order-worker', key='dlq_enabled', value=True)` (call #14, t=13)
- `config_drift` on `purchase-api`: appeared at t=44, after the agent had already resolved at t=23 (the instruction says faults can arrive mid-shift)

### har-f8-2019: score 0.341, tags: missed_event
- truth: [['inventory', 'memory_leak'], ['payments-gw', 'external_dependency']] · fixed: [True, False] · resolved as: [['inventory', 'memory_leak']]
- first intervention: `rollback(service='inventory', version='v1.2.1')` (call #13, t=12) — necessary
- `memory_leak` on `inventory`: signal first visible in `get_metrics(services=['web-gw', 'orders-api', 'checkout-svc', 'inventory', 'products-api'], window=15)` (call #4, t=3); correct fix: `rollback(service='inventory', version='v1.2.1')` (call #13, t=12)
- `external_dependency` on `payments-gw`: appeared at t=47, after the agent had already resolved at t=41 (the instruction says faults can arrive mid-shift)

### har-f14-2014: score 0.354, tags: missed_event
- truth: [['upload', 'bad_deploy'], ['encoder-coord', 'under_provisioned'], ['thumbnails', 'config_drift']] · fixed: [True, True, False] · resolved as: [['encoder-coord', 'under_provisioned'], ['upload', 'bad_deploy']]
- first intervention: `scale(service='encoder-coord', replicas=6)` (call #8, t=7) — necessary
- `bad_deploy` on `upload`: signal first visible in `get_deploys(service='upload')` (call #4, t=3); correct fix: `rollback(service='upload', version='v2.7.0')` (call #9, t=11)
- `under_provisioned` on `encoder-coord`: signal first visible in `get_events(since=0)` (call #2, t=1); correct fix: `scale(service='encoder-coord', replicas=6)` (call #8, t=7)
- `config_drift` on `thumbnails`: appeared at t=38, after the agent had already resolved at t=23 (the instruction says faults can arrive mid-shift)


## Failure tags

- reference: none
- noop: canary_missed=2, missed_event=13
- stop_early: canary_missed=2, missed_event=13, premature_resolve=24
- agent:verda:kimi-k3-1-pro: collateral=15, missed_event=7, over_investigation=10, premature_resolve=1, symptom_fix=4

## Hashes

- git commit: bbab5dce1824d4a9fa143d6a3a7a9beba2d29e51
- uv.lock sha256: f81f22d9da9bbd58e877f95c5633af61a238b825a62fa9ef3562731db8e62d7d
- scenarios (24): eas-f1-2000, eas-f3-2001, eas-f5-2002, eas-f7-2003, med-f12-2004, med-f13-2005, med-f13-2006, med-f11-2007, med-f1-2008, med-f2-2009, med-f4-2010, med-f11-2011, har-f9-2012, har-f10-2013, har-f14-2014, har-f6-2015, har-f9-2016, har-f10-2017, har-f14-2018, har-f8-2019, har-f9-2020, har-f10-2021, har-f14-2022, har-f6-2023
