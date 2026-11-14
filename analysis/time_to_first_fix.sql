-- Simulated minute of the first successful intervention on a node that really has a fault.
-- ponytail: approximation of scoring._first_fix (which checks fault-specific fix semantics): here any ok
-- intervention with args.service in the truth fault nodes counts. Episodes without one have NULL.
WITH first_fix AS (
    SELECT c.episode AS episode, min(c.t_after) AS t_first_fix
    FROM oncall_rollouts AS c
    INNER JOIN oncall_episodes AS e ON e.episode = c.episode AND e.scenario = c.scenario
    WHERE c.type = 'call'
      AND c.tool IN ('rollback', 'restart', 'scale', 'set_config', 'set_flag', 'set_circuit_breaker', 'run_maintenance', 'failover_db')
      AND JSONExtractBool(c.result, 'ok')
      AND has(e.fault_nodes, JSONExtractString(c.args, 'service'))
    GROUP BY c.episode
)
SELECT e.policy AS policy, e.difficulty AS difficulty,
       count() AS episodes, countIf(f.t_first_fix IS NOT NULL) AS fixed_any,
       round(avgIf(f.t_first_fix, f.t_first_fix IS NOT NULL), 1) AS mean_t_first_fix,
       round(quantileIf(0.5)(f.t_first_fix, f.t_first_fix IS NOT NULL), 1) AS median_t_first_fix
FROM oncall_episodes AS e
LEFT JOIN first_fix AS f ON f.episode = e.episode
GROUP BY policy, difficulty
ORDER BY policy, difficulty;
