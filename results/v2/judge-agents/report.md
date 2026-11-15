# OnCall report: suite `judge`

## Score per policy (mean ± std)

| policy | n | all | medium | hard | expert |
|---|---|---|---|---|---|
| reference | 24 | 0.969 ± 0.018 | 0.977 ± 0.008 | 0.968 ± 0.015 | 0.963 ± 0.024 |
| noop | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | 24 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:gemini:gemini-4-carbon | 72 | 0.871 ± 0.148 | 0.934 ± 0.042 | 0.880 ± 0.106 | 0.812 ± 0.213 |
| agent:gemini:gemini-4-argon | 72 | 0.850 ± 0.217 | 0.927 ± 0.060 | 0.824 ± 0.260 | 0.825 ± 0.226 |
| agent:verda:kimi-k3-1-pro | 72 | 0.759 ± 0.243 | 0.930 ± 0.059 | 0.666 ± 0.251 | 0.746 ± 0.256 |
| agent:gemini:gemini-3.8-flash | 72 | 0.748 ± 0.257 | 0.911 ± 0.063 | 0.714 ± 0.286 | 0.668 ± 0.264 |
| agent:verda:deepseek-4-1-flash-1017 | 72 | 0.724 ± 0.283 | 0.905 ± 0.083 | 0.646 ± 0.330 | 0.687 ± 0.266 |
| agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b | 72 | 0.636 ± 0.318 | 0.847 ± 0.223 | 0.571 ± 0.326 | 0.560 ± 0.308 |
| agent:gemini:gemini-3.1-pro-preview | 72 | 0.582 ± 0.282 | 0.635 ± 0.203 | 0.575 ± 0.289 | 0.551 ± 0.325 |

## Score per fault family (mean ± std)

| policy | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 | F13 | F14 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | R14 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | - | - | - | - | - | - | - | - | 0.985 ± 0.013 | 0.965 ± 0.000 | 0.969 ± 0.000 | 0.980 ± 0.000 | - | 0.976 ± 0.030 | 0.957 ± 0.000 | 0.964 ± 0.000 | 0.970 ± 0.003 | 0.992 ± 0.000 | - | 0.971 ± 0.000 | - | 0.981 ± 0.000 | 0.931 ± 0.016 | 0.975 ± 0.000 | 0.963 ± 0.000 | 0.957 ± 0.026 | 0.969 ± 0.011 | 0.974 ± 0.000 |
| noop | - | - | - | - | - | - | - | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| stop_early | - | - | - | - | - | - | - | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | - | 0.000 ± 0.000 | - | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| agent:gemini:gemini-4-carbon | - | - | - | - | - | - | - | - | 0.854 ± 0.119 | 0.897 ± 0.010 | 0.952 ± 0.002 | 0.933 ± 0.006 | - | 0.856 ± 0.074 | 0.858 ± 0.001 | 0.970 ± 0.011 | 0.849 ± 0.021 | 0.845 ± 0.007 | - | 0.948 ± 0.008 | - | 0.882 ± 0.075 | 0.471 ± 0.212 | 0.956 ± 0.005 | 0.945 ± 0.041 | 0.931 ± 0.024 | 0.971 ± 0.009 | 0.968 ± 0.003 |
| agent:gemini:gemini-4-argon | - | - | - | - | - | - | - | - | 0.935 ± 0.020 | 0.934 ± 0.006 | 0.958 ± 0.002 | 0.924 ± 0.011 | - | 0.857 ± 0.109 | 0.851 ± 0.012 | 0.973 ± 0.012 | 0.850 ± 0.014 | 0.799 ± 0.000 | - | 0.956 ± 0.007 | - | 0.845 ± 0.095 | 0.179 ± 0.143 | 0.955 ± 0.002 | 0.951 ± 0.003 | 0.932 ± 0.025 | 0.969 ± 0.007 | 0.968 ± 0.003 |
| agent:verda:kimi-k3-1-pro | - | - | - | - | - | - | - | - | 0.714 ± 0.141 | 0.734 ± 0.287 | 0.957 ± 0.017 | 0.818 ± 0.018 | - | 0.809 ± 0.252 | 0.715 ± 0.111 | 0.966 ± 0.013 | 0.853 ± 0.020 | 0.916 ± 0.058 | - | 0.954 ± 0.005 | - | 0.532 ± 0.272 | 0.322 ± 0.215 | 0.966 ± 0.011 | 0.877 ± 0.109 | 0.632 ± 0.329 | 0.806 ± 0.045 | 0.971 ± 0.008 |
| agent:gemini:gemini-3.8-flash | - | - | - | - | - | - | - | - | 0.786 ± 0.152 | 0.689 ± 0.306 | 0.944 ± 0.010 | 0.818 ± 0.021 | - | 0.781 ± 0.122 | 0.692 ± 0.133 | 0.956 ± 0.015 | 0.813 ± 0.022 | 0.841 ± 0.000 | - | 0.930 ± 0.030 | - | 0.386 ± 0.338 | 0.221 ± 0.252 | 0.958 ± 0.005 | 0.807 ± 0.122 | 0.885 ± 0.083 | 0.797 ± 0.039 | 0.976 ± 0.004 |
| agent:verda:deepseek-4-1-flash-1017 | - | - | - | - | - | - | - | - | 0.706 ± 0.148 | 0.887 ± 0.075 | 0.950 ± 0.005 | 0.816 ± 0.022 | - | 0.776 ± 0.239 | 0.848 ± 0.012 | 0.911 ± 0.052 | 0.854 ± 0.017 | 0.833 ± 0.145 | - | 0.953 ± 0.012 | - | 0.539 ± 0.301 | 0.048 ± 0.080 | 0.899 ± 0.059 | 0.785 ± 0.061 | 0.755 ± 0.209 | 0.587 ± 0.298 | 0.977 ± 0.004 |
| agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b | - | - | - | - | - | - | - | - | 0.544 ± 0.204 | 0.477 ± 0.472 | 0.841 ± 0.013 | 0.835 ± 0.091 | - | 0.736 ± 0.221 | 0.372 ± 0.185 | 0.963 ± 0.008 | 0.827 ± 0.095 | 0.563 ± 0.493 | - | 0.911 ± 0.048 | - | 0.294 ± 0.316 | 0.162 ± 0.245 | 0.962 ± 0.008 | 0.601 ± 0.337 | 0.745 ± 0.234 | 0.580 ± 0.166 | 0.967 ± 0.021 |
| agent:gemini:gemini-3.1-pro-preview | - | - | - | - | - | - | - | - | 0.383 ± 0.234 | 0.336 ± 0.056 | 0.623 ± 0.197 | 0.641 ± 0.181 | - | 0.841 ± 0.100 | 0.622 ± 0.209 | 0.874 ± 0.040 | 0.840 ± 0.038 | 0.553 ± 0.115 | - | 0.624 ± 0.184 | - | 0.322 ± 0.302 | 0.328 ± 0.229 | 0.589 ± 0.330 | 0.723 ± 0.148 | 0.688 ± 0.196 | 0.403 ± 0.425 | 0.778 ± 0.280 |

## Gap reference - agent (95% bootstrap CI over scenarios)

- agent:gemini:gemini-4-carbon: 0.098 [0.054, 0.154] over 24 scenarios; per run: 0.109, 0.092, 0.093 (positive in every run)
- agent:gemini:gemini-4-argon: 0.119 [0.051, 0.211] over 24 scenarios; per run: 0.120, 0.115, 0.122 (positive in every run)
- agent:verda:kimi-k3-1-pro: 0.210 [0.130, 0.301] over 24 scenarios; per run: 0.192, 0.224, 0.214 (positive in every run)
- agent:gemini:gemini-3.8-flash: 0.221 [0.142, 0.311] over 24 scenarios; per run: 0.239, 0.235, 0.189 (positive in every run)
- agent:verda:deepseek-4-1-flash-1017: 0.244 [0.155, 0.346] over 24 scenarios; per run: 0.273, 0.220, 0.240 (positive in every run)
- agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b: 0.332 [0.238, 0.431] over 24 scenarios; per run: 0.338, 0.268, 0.392 (positive in every run)
- agent:gemini:gemini-3.1-pro-preview: 0.387 [0.304, 0.470] over 24 scenarios; per run: 0.387, 0.377, 0.396 (positive in every run)

## Annotated failures: agent:gemini:gemini-4-carbon

### exp-r9-2030: score 0.200, tags: herring_followed, premature_resolve, collateral, loop_not_broken, over_investigation
- truth: [['redis-main', 'cache_invalidation_loop'], ['auth-svc', 'clock_skew'], ['tenant-svc', 'bad_deploy']] · fixed: [False, True, True] · resolved as: [['auth-svc', 'clock_skew'], ['redis-main', 'cache_invalidation_loop'], ['tenant-svc', 'bad_deploy']]
- first intervention: `rollback(version='v3.4.1', service='tenant-svc')` (call #56, t=59) — necessary
- `cache_invalidation_loop` on `redis-main`: signal first visible in `get_metrics(services=['gateway', 'tenant-svc', 'pg-main', 'redis-main', 'auth-svc'], window=15)` (call #6, t=5); correct fix: `set_config(value=1500, key='timeout_ms', service='redis-main')` (call #71, t=80)
- `clock_skew` on `auth-svc`: signal first visible in `get_logs(service='auth-svc', limit=50)` (call #11, t=10); correct fix: `run_maintenance(action='sync_clock', service='auth-svc')` (call #57, t=64)
- `bad_deploy` on `tenant-svc`: signal first visible in `get_deploys()` (call #5, t=4); correct fix: `rollback(version='v3.4.1', service='tenant-svc')` (call #56, t=59)

### har-r9-2026: score 0.587, tags: collateral, over_investigation
- truth: [['cache-cluster', 'cache_invalidation_loop'], ['billing', 'cert_expiry']] · fixed: [True, True] · resolved as: [['billing', 'cert_expiry'], ['cache-cluster', 'cache_invalidation_loop']]
- first intervention: `run_maintenance(action='rotate_cert', service='billing')` (call #55, t=57) — necessary
- `cache_invalidation_loop` on `cache-cluster`: signal first visible in `get_metrics(services=['cache-cluster', 'projects', 'report-svc', 'metering', 'alerts-api'], window=15)` (call #10, t=9); correct fix: `set_config(value=1000, service='cache-cluster', key='timeout_ms')` (call #72, t=78)
- `cert_expiry` on `billing`: signal first visible in `get_events(since=0)` (call #2, t=1); correct fix: `run_maintenance(action='rotate_cert', service='billing')` (call #55, t=57)

### exp-f9-2037: score 0.671, tags: collateral
- truth: [['edge-cache', 'cache_stampede'], ['accounts', 'clock_skew'], ['blob-origin', 'external_dependency']] · fixed: [True, True, True] · resolved as: [['accounts', 'clock_skew'], ['blob-origin', 'external_dependency'], ['edge-cache', 'cache_stampede']]
- first intervention: `run_maintenance(service='edge-cache', action='warm_cache')` (call #15, t=14) — necessary
- `cache_stampede` on `edge-cache`: signal first visible in `get_events(since=0)` (call #2, t=1); correct fix: `run_maintenance(service='edge-cache', action='warm_cache')` (call #15, t=14)
- `clock_skew` on `accounts`: signal first visible in `get_logs(service='accounts')` (call #11, t=10); correct fix: `run_maintenance(action='sync_clock', service='accounts')` (call #18, t=19)
- `external_dependency` on `blob-origin`: signal first visible in `get_events(since=0)` (call #40, t=49); correct fix: `set_circuit_breaker(service='queue-api', mode='fallback', dep='blob-origin')` (call #42, t=51)


## Annotated failures: agent:gemini:gemini-4-argon

### har-r9-2026: score 0.000, tags: premature_resolve, collateral, loop_not_broken, over_investigation
- truth: [['cache-cluster', 'cache_invalidation_loop'], ['billing', 'cert_expiry']] · fixed: [False, True] · resolved as: [['billing', 'expired_cert_dismissed_alert'], ['cache-cluster', 'cache_invalidation_loop']]
- first intervention: `run_maintenance(service='billing', action='rotate_cert')` (call #54, t=56) — necessary
- `cache_invalidation_loop` on `cache-cluster`: signal first visible in `get_metrics(window=15, services=['cache-cluster', 'gateway', 'report-svc', 'metering', 'alerts-api'])` (call #9, t=8); correct fix: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #75, t=79)
- `cert_expiry` on `billing`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='billing', action='rotate_cert')` (call #54, t=56)

### exp-r9-2030: score 0.200, tags: premature_resolve, loop_not_broken
- truth: [['redis-main', 'cache_invalidation_loop'], ['auth-svc', 'clock_skew'], ['tenant-svc', 'bad_deploy']] · fixed: [False, True, True] · resolved as: [['auth-svc', 'clock_skew'], ['tenant-svc', 'cache_invalidation_loop']]
- first intervention: `rollback(version='v3.4.1', service='tenant-svc')` (call #19, t=18) — necessary
- `cache_invalidation_loop` on `redis-main`: signal first visible in `get_metrics(services=['gateway', 'tenant-svc', 'billing', 'pg-main', 'redis-main'], window=15)` (call #7, t=6); correct fix: `set_config(key='timeout_ms', value=1500, service='redis-main')` (call #65, t=74)
- `clock_skew` on `auth-svc`: signal first visible in `get_logs(service='auth-svc')` (call #10, t=9); correct fix: `run_maintenance(service='auth-svc', action='sync_clock')` (call #20, t=23)
- `bad_deploy` on `tenant-svc`: signal first visible in `get_deploys()` (call #5, t=4); correct fix: `rollback(version='v3.4.1', service='tenant-svc')` (call #19, t=18)

### exp-r8-2033: score 0.701, tags: premature_resolve, silent_harm_missed, over_investigation
- truth: [['notify-svc', 'mail_backlog_ramp'], ['public-api', 'progressive_gray'], ['billing-svc', 'config_drift']] · fixed: [False, True, True] · resolved as: [['billing-svc', 'thread_starvation'], ['notify-svc', 'mail_backlog_ramp'], ['public-api', 'progressive_gray']]
- first intervention: `set_flag(on=False, flag='bulk-export')` (call #21, t=21) — necessary
- `mail_backlog_ramp` on `notify-svc`: signal first visible in `get_events()` (call #2, t=1); correct fix: `set_config(value=80, key='send_rate_per_s', service='notify-svc')` (call #29, t=31)
- `progressive_gray` on `public-api`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(action='restart_networkd', service='public-api')` (call #26, t=26)
- `config_drift` on `billing-svc`: signal first visible in `get_metrics(window=15, services=['metering', 'billing-svc', 'notify-svc', 'redis-main', 'saas-db'])` (call #6, t=5); correct fix: `set_flag(on=False, flag='bulk-export')` (call #21, t=21)


## Annotated failures: agent:verda:kimi-k3-1-pro

### exp-r9-2030: score 0.000, tags: herring_followed, collateral, loop_not_broken
- truth: [['redis-main', 'cache_invalidation_loop'], ['auth-svc', 'clock_skew'], ['tenant-svc', 'bad_deploy']] · fixed: [False, True, True] · resolved as: None
- first intervention: `rollback(service='tenant-svc', version='v3.4.1')` (call #11, t=10) — necessary
- `cache_invalidation_loop` on `redis-main`: signal first visible in `get_metrics(services=['workspace-svc', 'reports', 'metering', 'redis-main', 'jobs-runner'], window=15)` (call #6, t=5); correct fix: `set_config(service='redis-main', key='timeout_ms', value=1500)` (call #31, t=34)
- `clock_skew` on `auth-svc`: signal first visible in `get_logs(service='auth-svc', level='ERROR', limit=100)` (call #21, t=24); correct fix: `run_maintenance(service='auth-svc', action='sync_clock')` (call #71, t=90)
- `bad_deploy` on `tenant-svc`: signal first visible in `get_metrics(services=['gateway', 'tenant-svc', 'pg-main', 'billing', 'auth-svc'], window=15)` (call #5, t=4); correct fix: `rollback(service='tenant-svc', version='v3.4.1')` (call #11, t=10)

### har-r8-2025: score 0.201, tags: premature_resolve, over_investigation, missed_event
- truth: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'config_drift']] · fixed: [True, False] · resolved as: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'progressive_gray']]
- first intervention: `set_config(service='order-svc', key='send_rate_per_s', value=1)` (call #20, t=19) — necessary
- `mail_backlog_ramp` on `order-svc`: signal first visible in `get_events(since=0)` (call #2, t=1); correct fix: `set_config(service='order-svc', key='send_rate_per_s', value=1)` (call #20, t=19)
- `config_drift` on `stock-svc`: signal first visible in `get_metrics(services=['edge-api', 'checkout', 'order-svc', 'payments-gw', 'stock-svc'], window=15)` (call #48, t=55); correct fix: never

### har-r9-2026: score 0.263, tags: collateral
- truth: [['cache-cluster', 'cache_invalidation_loop'], ['billing', 'cert_expiry']] · fixed: [True, True] · resolved as: [['billing', 'cert_expiry'], ['cache-cluster', 'bad_config_push'], ['cache-cluster', 'cache_invalidation_loop']]
- first intervention: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #22, t=21) — necessary
- `cache_invalidation_loop` on `cache-cluster`: signal first visible in `get_metrics(services=['cache-cluster', 'projects', 'report-svc', 'metering', 'jobs-queue'], window=15)` (call #17, t=16); correct fix: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #22, t=21)
- `cert_expiry` on `billing`: signal first visible in `get_events(since=0)` (call #2, t=1); correct fix: `run_maintenance(service='billing', action='rotate_cert')` (call #28, t=30)


## Annotated failures: agent:gemini:gemini-3.8-flash

### har-r8-2025: score 0.000, tags: premature_resolve, silent_harm_missed, over_investigation, missed_event
- truth: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'config_drift']] · fixed: [False, False] · resolved as: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'progressive_gray']]
- first intervention: `set_config(key='send_rate_per_s', value=30, service='order-svc')` (call #34, t=33) — necessary
- `mail_backlog_ramp` on `order-svc`: signal first visible in `get_events(since=-30)` (call #3, t=2); correct fix: `set_config(key='send_rate_per_s', value=30, service='order-svc')` (call #34, t=33)
- `config_drift` on `stock-svc`: signal first visible in `get_metrics(window=15, services=['stock-svc'])` (call #52, t=55); correct fix: never

### har-r9-2026: score 0.000, tags: premature_resolve, collateral, loop_not_broken, over_investigation
- truth: [['cache-cluster', 'cache_invalidation_loop'], ['billing', 'cert_expiry']] · fixed: [False, True] · resolved as: [['billing', 'cert_expiry'], ['cache-cluster', 'bad_config_push']]
- first intervention: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #41, t=41) — necessary
- `cache_invalidation_loop` on `cache-cluster`: signal first visible in `get_metrics(window=30, services=['projects', 'accounts', 'billing', 'cache-cluster', 'gateway'])` (call #20, t=19); correct fix: `set_config(service='cache-cluster', key='timeout_ms', value=1000)` (call #41, t=41)
- `cert_expiry` on `billing`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='billing', action='rotate_cert')` (call #62, t=73)

### exp-r9-2030: score 0.050, tags: premature_resolve, collateral, loop_not_broken, over_investigation
- truth: [['redis-main', 'cache_invalidation_loop'], ['auth-svc', 'clock_skew'], ['tenant-svc', 'bad_deploy']] · fixed: [False, True, True] · resolved as: [['auth-svc', 'clock_skew'], ['redis-main', 'bad_config_push'], ['tenant-svc', 'bad_deploy']]
- first intervention: `rollback(service='tenant-svc', version='v3.4.1')` (call #71, t=72) — necessary
- `cache_invalidation_loop` on `redis-main`: signal first visible in `get_metrics(window=15, services=['redis-main'])` (call #16, t=15); correct fix: `set_config(key='timeout_ms', service='redis-main', value=1500)` (call #76, t=83)
- `clock_skew` on `auth-svc`: signal first visible in `get_logs(service='auth-svc', level='ERROR')` (call #15, t=14); correct fix: `run_maintenance(service='auth-svc', action='sync_clock')` (call #72, t=77)
- `bad_deploy` on `tenant-svc`: signal first visible in `get_deploys()` (call #4, t=3); correct fix: `rollback(service='tenant-svc', version='v3.4.1')` (call #71, t=72)


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


## Annotated failures: agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b

### exp-r8-2033: score 0.000, tags: collateral, silent_harm_missed, gray_missed, over_investigation
- truth: [['notify-svc', 'mail_backlog_ramp'], ['public-api', 'progressive_gray'], ['billing-svc', 'config_drift']] · fixed: [False, False, True] · resolved as: None
- first intervention: `drain_instance(service='public-api', instance='public-api-3')` (call #23, t=24) — necessary
- `mail_backlog_ramp` on `notify-svc`: signal first visible in `get_events()` (call #2, t=1); correct fix: never
- `progressive_gray` on `public-api`: signal first visible in `get_events()` (call #2, t=1); correct fix: never
- `config_drift` on `billing-svc`: signal first visible in `get_metrics(services=['public-api', 'saas-db', 'redis-main', 'billing-svc', 'projects'], window=10)` (call #4, t=3); correct fix: `set_flag(flag='bulk-export', on=False)` (call #53, t=78)

### har-r8-2025: score 0.000, tags: premature_resolve, silent_harm_missed, over_investigation, missed_event
- truth: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'config_drift']] · fixed: [False, False] · resolved as: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'external_dependency']]
- first intervention: `set_config(service='order-svc', key='send_rate_per_s', value=1)` (call #23, t=27) — necessary
- `mail_backlog_ramp` on `order-svc`: signal first visible in `get_events()` (call #2, t=1); correct fix: `set_config(service='order-svc', key='send_rate_per_s', value=1)` (call #23, t=27)
- `config_drift` on `stock-svc`: signal first visible in `get_metrics(services=['stock-svc'], window=10)` (call #36, t=56); correct fix: never

### har-r9-2026: score 0.000, tags: symptom_fix, collateral, loop_not_broken, over_investigation
- truth: [['cache-cluster', 'cache_invalidation_loop'], ['billing', 'cert_expiry']] · fixed: [False, True] · resolved as: None
- first intervention: `set_config(service='accounts', key='max_retries', value=0)` (call #26, t=25) — NOT a fix step and not on a faulty node
- `cache_invalidation_loop` on `cache-cluster`: signal first visible in `get_metrics(services=['cache-cluster', 'projects', 'billing'], window=10)` (call #12, t=11); correct fix: never
- `cert_expiry` on `billing`: signal first visible in `get_events()` (call #2, t=1); correct fix: `run_maintenance(service='billing', action='rotate_cert')` (call #49, t=75)


## Annotated failures: agent:gemini:gemini-3.1-pro-preview

### har-r8-2025: score 0.000, tags: symptom_fix, premature_resolve, collateral, silent_harm_missed, over_investigation, missed_event
- truth: [['order-svc', 'mail_backlog_ramp'], ['stock-svc', 'config_drift']] · fixed: [False, False] · resolved as: [['cart-svc', 'cert_expiry'], ['checkout', 'clock_skew'], ['checkout', 'external_dependency'], ['order-svc', 'mail_backlog_ramp']]
- first intervention: `set_config(value='on', key='conn_lifetime_jitter', service='cart-svc')` (call #38, t=40) — NOT a fix step and not on a faulty node
- `mail_backlog_ramp` on `order-svc`: signal first visible in `get_events()` (call #2, t=1); correct fix: `set_config(value=15, key='send_rate_per_s', service='order-svc')` (call #63, t=86)
- `config_drift` on `stock-svc`: signal first visible in `get_metrics(services=['order-svc', 'cart-svc', 'edge-api', 'stock-svc', 'catalog-svc'], window=10)` (call #49, t=61); correct fix: never

### exp-r8-2033: score 0.000, tags: collateral, silent_harm_missed, gray_missed, over_investigation
- truth: [['notify-svc', 'mail_backlog_ramp'], ['public-api', 'progressive_gray'], ['billing-svc', 'config_drift']] · fixed: [False, False, True] · resolved as: None
- first intervention: `set_config(value='on', key='conn_lifetime_jitter', service='billing-svc')` (call #17, t=18) — necessary
- `mail_backlog_ramp` on `notify-svc`: signal first visible in `get_events()` (call #1, t=0); correct fix: `set_config(value=5, key='send_rate_per_s', service='notify-svc')` (call #33, t=36)
- `progressive_gray` on `public-api`: signal first visible in `get_events()` (call #1, t=0); correct fix: never
- `config_drift` on `billing-svc`: signal first visible in `get_metrics(window=10, services=['public-api', 'reports', 'metering', 'billing-svc', 'redis-main'])` (call #4, t=3); correct fix: `set_flag(on=False, flag='bulk-export')` (call #94, t=114)

### exp-r9-2030: score 0.000, tags: collateral, loop_not_broken, over_investigation
- truth: [['redis-main', 'cache_invalidation_loop'], ['auth-svc', 'clock_skew'], ['tenant-svc', 'bad_deploy']] · fixed: [False, True, True] · resolved as: None
- first intervention: `set_config(service='auth-svc', value=0, key='max_retries')` (call #16, t=15) — necessary
- `cache_invalidation_loop` on `redis-main`: signal first visible in `get_metrics(services=['redis-main'], window=5)` (call #24, t=27); correct fix: `set_config(service='redis-main', key='timeout_ms', value=1500)` (call #51, t=63)
- `clock_skew` on `auth-svc`: signal first visible in `get_logs(service='auth-svc', limit=50)` (call #23, t=26); correct fix: `run_maintenance(service='auth-svc', action='sync_clock')` (call #30, t=33)
- `bad_deploy` on `tenant-svc`: signal first visible in `get_deploys(service='tenant-svc')` (call #4, t=3); correct fix: `rollback(version='v3.4.1', service='tenant-svc')` (call #37, t=44)


## Failure tags

- reference: none
- noop: canary_missed=1, config_push_missed=2, gray_missed=1, loop_not_broken=2, missed_event=12, silent_harm_missed=13
- stop_early: canary_missed=1, config_push_missed=2, gray_missed=1, loop_not_broken=2, missed_event=12, premature_resolve=24, silent_harm_missed=13
- agent:gemini:gemini-4-carbon: collateral=11, herring_followed=3, loop_not_broken=2, missed_event=1, over_investigation=29, premature_resolve=6, silent_harm_missed=1, symptom_fix=3
- agent:gemini:gemini-4-argon: collateral=3, loop_not_broken=5, missed_event=2, over_investigation=19, premature_resolve=9, silent_harm_missed=2
- agent:verda:kimi-k3-1-pro: collateral=20, herring_followed=2, loop_not_broken=1, missed_event=8, over_investigation=25, premature_resolve=13, silent_harm_missed=8, symptom_fix=8
- agent:gemini:gemini-3.8-flash: collateral=16, loop_not_broken=4, missed_event=5, over_investigation=55, premature_resolve=15, silent_harm_missed=9, symptom_fix=8
- agent:verda:deepseek-4-1-flash-1017: collateral=21, gray_missed=1, herring_followed=1, loop_not_broken=5, missed_event=6, over_investigation=22, premature_resolve=5, silent_harm_missed=5, symptom_fix=7
- agent:nemotron:nvidia/nemotron-3.5-super-vl-120b-a12b: collateral=30, config_push_missed=1, gray_missed=1, loop_not_broken=4, missed_event=6, over_investigation=34, premature_resolve=16, silent_harm_missed=13, symptom_fix=9
- agent:gemini:gemini-3.1-pro-preview: authority_bias=2, collateral=56, gray_missed=1, herring_followed=13, loop_not_broken=1, missed_event=4, over_investigation=27, premature_resolve=8, silent_harm_missed=6, symptom_fix=16

## Hashes

- git commit: d880657835f5c4a1b97ba3027b292f78ba3343ef
- uv.lock sha256: f81f22d9da9bbd58e877f95c5633af61a238b825a62fa9ef3562731db8e62d7d
- scenarios (24): med-r4-2005, med-r6-2007, med-r10-2009, med-r14-2011, med-f11-2000, med-f12-2001, har-r1-2023, har-r3-2024, har-r8-2025, har-r9-2026, har-r12-2010, har-r13-2011, har-f9-2012, har-f10-2013, har-f14-2014, har-r2-2015, exp-r9-2030, exp-f14-2031, exp-r3-2032, exp-r8-2033, exp-r12-2034, exp-r13-2035, exp-r11-2036, exp-f9-2037
