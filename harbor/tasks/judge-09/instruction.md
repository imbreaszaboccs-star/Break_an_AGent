# Production incident

You are the on-call engineer for a web platform of about a dozen services (user-facing entry service,
application services, a message queue with its worker, a database, a cache and an external provider). Users are being affected by an
incident that is already in progress. Find the root cause(s), fix them, and report what you found.

You interact with the platform only through the tools of the MCP server `oncall`. The platform is not reachable
any other way. Time is simulated: **every tool call advances the clock**, and the platform
keeps serving traffic (and failing) while you work.

## Rules of the clock

- The shift is **T = 120 minutes** (t = 0 .. 119). History before t = 0 is visible through the metrics and log tools.
- Actions take effect only when their duration has elapsed; observations return the state at the time of the call.
- The shift ends when you call `resolve_incident`, when t >= 120, or after 150 tool calls.
- After it ends you cannot act any more, but the platform keeps running for a further **45-minute epilog at 1.5x traffic**.
  Your score depends on how the platform fares through the epilog, so fixes must be durable, not cosmetic.
- `get_metrics` windows cover completed minutes only, so the effect of an action that has just finished shows up from the next minute on.
- A call with invalid arguments costs 1 minute and changes nothing.
- There may be more than one problem, and a second one can start later in the shift.
- Not every alert, recent deploy or warning is related to the incident.

## Tools (cost in simulated minutes)

- `get_status()`: time, remaining minutes, active alerts, cumulative spend. Cost: 1 min.
- `get_events(since=0)`: alerts, deploys and team messages. Cost: 1 min.
- `get_topology()`: services, replicas, dependency edges with circuit-breaker state; the database replica's sync state. Cost: 1 min.
- `get_metrics(services (1-5 names), window=5 (1-30))`: metric series per service: rps, error_rate, p50, p99, cpu, mem, conns, worker_util, disk, retries, queue_lag, cache_hit_rate. Cost: 1 min.
- `get_logs(service, level=ALL|ERROR|WARN|INFO, grep='', limit=50 (1-200))`: log lines of the last 60 minutes. Cost: 1 min.
- `get_traces(endpoint ('/' + a direct dependency of the entry service), n=5 (1-10))`: sample request traces. Cost: 2 min.
- `get_deploys(service=None)`: deploy history incl. has_schema_migration and reversible. Cost: 1 min.
- `get_config(service)`: current config and its change audit log. Cost: 1 min.
- `get_flags()`: feature flags and their change audit log. Cost: 1 min.
- `get_runbook(topic)`: generic SRE runbook text. Cost: 1 min.
- `rollback(service, version)`: roll back to an older version. Cost: 5 min.
- `restart(service)`: restart a service. Cost: 3 min.
- `scale(service, replicas (1-20))`: set the replica count (adds spend). Cost: 4 min.
- `set_config(service, key, value)`: keys: max_retries 0-10, timeout_ms 10-30000, pool_size 1-100, rate_limit_rps 0-100000 (0 = off), log_level, dlq_enabled. Cost: 2 min.
- `set_flag(flag, on)`: turn a feature flag on or off. Cost: 1 min.
- `set_circuit_breaker(service, dep, mode=closed|open|fallback)`: set the breaker of one dependency edge. Cost: 2 min.
- `failover_db()`: fail over the database to its replica. Cost: 6 min.
- `run_maintenance(service, action)`: actions: rotate_cert, prune_logs, purge_dlq, warm_cache, vacuum_db, rebalance_shards, compact_wal, flush_dns (valid kinds differ per action). Cost: 3 min.
- `wait(minutes (1-30))`: let time pass. Cost: n min.
- `resolve_incident(root_causes=[{service, fault_class}], summary='')`: close the incident; ends your interaction. Cost: 0 min.

`fault_class` is one of: `bad_deploy`, `memory_leak`, `retry_storm`, `config_drift`, `external_dependency`, `cert_expiry`, `disk_full`, `cache_stampede`, `poison_message`, `bad_canary`, `thread_starvation`, `under_provisioned`.
In `resolve_incident`, list one entry per root cause: the service where the fault lives and its class.

## Scoring

Per minute t, `offered` is the user traffic and `good` the share served successfully and fast enough.
Error budget: `w_t = 1` while the cumulative outage minutes (sum of (offered - good) / offered) are <= 15, else `w_t = 2`.

```
U        = 1 - sum_t w_t * (offered_t - good_t) / sum_t w_t * offered_t        (t over the shift and the epilog)
R_avail  = clip((U - U_noop) / (U_oracle - U_noop), 0, 1)     # U_noop: doing nothing, U_oracle: an omniscient operator
R_fixed  = share of the real faults that are actually fixed at the end of the epilog
R_diag   = 1 if the set of (service, fault_class) you reported equals the true set, else 0
raw      = 0.6 * R_avail + 0.3 * R_fixed + 0.1 * R_diag
score    = clip(raw * M_dataloss - P_collateral - P_cost, 0, 1)
```

- `M_dataloss` = 0.25 if you fail over to a database replica that is not in sync, or roll back past an irreversible schema migration; otherwise 1.
- `P_collateral` = 0.10 per rollback, restart, failover_db or harmful maintenance (vacuum_db, rebalance_shards, compact_wal)
  that is not part of fixing a real fault, and 0.05 per other unnecessary change (set_flag, set_config, set_circuit_breaker,
  scale, other maintenance) that neither fixes a real fault nor targets the service where one lives.
- `P_cost` = 0.10 if the mean spend over shift and epilog exceeds 1.3x that of doing nothing.

The reward of this task is `score`. Stopping early or changing things at random does not pay off.
