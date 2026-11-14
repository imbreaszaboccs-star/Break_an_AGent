# OnCall report: suite `judge`

## Score per policy (mean ± std)

| policy | n | all | medium | hard | expert |
|---|---|---|---|---|---|
| reference | 24 | 0.969 ± 0.018 | 0.977 ± 0.008 | 0.968 ± 0.015 | 0.963 ± 0.024 |
| noop | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:verda:deepseek-4-1-flash-1017 | 72 | 0.724 ± 0.283 | 0.905 ± 0.083 | 0.646 ± 0.330 | 0.687 ± 0.266 |

## Score per fault family (mean ± std)

| policy | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | R14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | - | - | - | - | - | - | - | - | 0.985 ± 0.013 | 0.965 ± 0.000 | 0.969 ± 0.000 | 0.980 ± 0.000 | - | 0.976 ± 0.030 | 0.957 ± 0.000 | 0.964 ± 0.000 | 0.970 ± 0.003 | 0.992 ± 0.000 | - | 0.971 ± 0.000 | - | 0.981 ± 0.000 | 0.931 ± 0.016 | 0.975 ± 0.000 | 0.963 ± 0.000 | 0.957 ± 0.026 | 0.969 ± 0.011 | 0.974 ± 0.000 |
| noop | - | - | - | - | - | - | - | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | - | - | - | - | - | - | - | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:verda:deepseek-4-1-flash-1017 | - | - | - | - | - | - | - | - | 0.706 ± 0.148 | 0.887 ± 0.075 | 0.950 ± 0.005 | 0.816 ± 0.022 | - | 0.776 ± 0.239 | 0.848 ± 0.012 | 0.911 ± 0.052 | 0.854 ± 0.017 | 0.833 ± 0.145 | - | 0.953 ± 0.012 | - | 0.539 ± 0.301 | 0.048 ± 0.080 | 0.899 ± 0.059 | 0.785 ± 0.061 | 0.755 ± 0.209 | 0.587 ± 0.298 | 0.977 ± 0.004 |

## Gap reference - agent (95% bootstrap CI over scenarios)

- agent:verda:deepseek-4-1-flash-1017: 0.244 [0.155, 0.346] over 24 scenarios; per run: 0.273, 0.220, 0.240 (positive in every run)

## Annotated failures: agent:verda:deepseek-4-1-flash-1017

### har-r8-2025: score 0.000, tags: silent_harm_missed, over_investigation, missed_event
- truth: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'config_drift']] · fixed: [False, False] · resolved as: None
- first intervention: `set_config(service='order-svc', key='send_rate_per_s', value=20)` (call #19, t=18) — necessary
- `mail_backlog_ramp` on `order-svc`: signal first visible in `get_events(since=0)` (call #2, t=1); correct fix: `set_config(service='order-svc', key='send_rate_per_s', value=20)` (call #19, t=18)
- `config_drift` on `stock-svc`: signal first visible in `get_logs(level='ERROR', limit=40, service='stock-svc')` (call #40, t=63); correct fix: never

### har-r9-2026: score 0.000, tags: collateral, loop_not_broken
- truth: [['cache-cluster', 'cache_invalidation_loop'], ['billing', 'cert_expiry']] · fixed: [False, True] · resolved as: None
- first intervention: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #16, t=16) — necessary
- `cache_invalidation_loop` on `cache-cluster`: signal first visible in `get_metrics(services=['cache-cluster', 'identity'], window=15)` (call #11, t=11); correct fix: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #16, t=16)
- `cert_expiry` on `billing`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(action='rotate_cert', service='billing')` (call #46, t=63)

### exp-r9-2030: score 0.000, tags: herring_followed, collateral, loop_not_broken
- truth: [['redis-main', 'cache_invalidation_loop'], ['auth-svc', 'clock_skew'], ['tenant-svc', 'bad_deploy']] · fixed: [False, True, True] · resolved as: None
- first intervention: `run_maintenance(service='auth-svc', action='sync_clock')` (call #21, t=21) — necessary
- `cache_invalidation_loop` on `redis-main`: signal first visible in `get_metrics(services=['redis-main'], window=10)` (call #12, t=12); correct fix: `set_config(service='redis-main', key='timeout_ms', value=1500)` (call #22, t=24)
- `clock_skew` on `auth-svc`: signal first visible in `get_logs(level='ERROR', limit=25, service='auth-svc')` (call #17, t=17); correct fix: `run_maintenance(service='auth-svc', action='sync_clock')` (call #21, t=21)
- `bad_deploy` on `tenant-svc`: signal first visible in `get_metrics(services=['gateway', 'tenant-svc', 'pg-main', 'auth-svc', 'workspace-svc'], window=10)` (call #4, t=3); correct fix: `rollback(service='tenant-svc', version='v3.4.1')` (call #78, t=103)


## Failure tags

- reference: none
- noop: canary_missed=1, config_push_missed=2, gray_missed=1, loop_not_broken=2, missed_event=12, silent_harm_missed=13
- stop_early: canary_missed=1, config_push_missed=2, gray_missed=1, loop_not_broken=2, missed_event=12, premature_resolve=24, silent_harm_missed=13
- agent:verda:deepseek-4-1-flash-1017: collateral=21, gray_missed=1, herring_followed=1, loop_not_broken=5, missed_event=6, over_investigation=22, premature_resolve=5, silent_harm_missed=5, symptom_fix=7

## Hashes

- git commit: bbab5dce1824d4a9fa143d6a3a7a9beba2d29e51
- uv.lock sha256: f81f22d9da9bbd58e877f95c5633af61a238b825a62fa9ef3562731db8e62d7d
- scenarios (24): med-r4-2005, med-r6-2007, med-r10-2009, med-r14-2011, med-f11-2000, med-f12-2001, har-r1-2023, har-r3-2024, har-r8-2025, har-r9-2026, har-r12-2010, har-r13-2011, har-f9-2012, har-f10-2013, har-f14-2014, har-r2-2015, exp-r9-2030, exp-f14-2031, exp-r3-2032, exp-r8-2033, exp-r12-2034, exp-r13-2035, exp-r11-2036, exp-f9-2037
