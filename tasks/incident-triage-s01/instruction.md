You are the on-call engineer for a small web platform. Customers use the three **user-facing**
services; those depend on application services, which depend on data services. Something is
broken, and the loudest alert is not necessarily where the problem is.

You work through the `incident-triage` MCP server. Every tool call advances a shared clock:
looking things up costs 1 tick, changing things (restart, rollback, set_config, scale) costs
3 ticks, and `wait` lets time pass. Your shift is **45 ticks**. Effects of a change are not
reported back; observe them yourself. Incidents can begin at any time during the first
20 ticks of the shift, so a quiet dashboard early on is not proof that the shift is over.

When you are done (or out of ideas), call `submit` with up to three findings
`{"service": ..., "kind": ...}` for root causes you found **and fixed**. `kind` is one of
`bad_deploy`, `bad_config`, `resource_exhaustion`, `stuck_process`.

You are scored on the health of the user-facing services after the shift, weighted by traffic,
compared with doing nothing. Credit for a finding requires that the fault was actually fixed;
needless changes to healthy services cost points; finishing sooner earns a small bonus.
