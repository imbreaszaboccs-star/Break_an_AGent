-- Paired comparison of two policies on the same scenarios.
--   clickhouse-client --param_base=agent_vllm_google_gemma-3-4b-it --param_ft=agent_vllm_gemma-ft --queries-file analysis/gemma_base_vs_ft.sql
-- (policy = episode id without scenario/run suffix = policy name with ':' and '/' replaced by '_')
WITH per AS (
    SELECT scenario, any(difficulty) AS difficulty, any(family) AS family,
           avgIf(score, policy = {base:String}) AS base, avgIf(score, policy = {ft:String}) AS ft,
           countIf(policy = {base:String}) AS nb, countIf(policy = {ft:String}) AS nf
    FROM oncall_episodes
    WHERE policy IN ({base:String}, {ft:String})
    GROUP BY scenario
    HAVING nb > 0 AND nf > 0
)
SELECT 'all' AS grp, count() AS scenarios, round(avg(base), 3) AS base_mean, round(avg(ft), 3) AS ft_mean,
       round(avg(ft - base), 3) AS delta, round(countIf(ft > base) / count(), 3) AS win_rate
FROM per
UNION ALL
SELECT difficulty, count(), round(avg(base), 3), round(avg(ft), 3), round(avg(ft - base), 3), round(countIf(ft > base) / count(), 3)
FROM per GROUP BY difficulty
UNION ALL
SELECT family, count(), round(avg(base), 3), round(avg(ft), 3), round(avg(ft - base), 3), round(countIf(ft > base) / count(), 3)
FROM per GROUP BY family
ORDER BY grp;

-- Tag deltas: episodes carrying the tag (negative delta = fewer after fine-tuning)
SELECT tag, countIf(policy = {ft:String}) - countIf(policy = {base:String}) AS delta_episodes,
       countIf(policy = {base:String}) AS base, countIf(policy = {ft:String}) AS ft
FROM oncall_episodes
ARRAY JOIN tags AS tag
WHERE policy IN ({base:String}, {ft:String})
GROUP BY tag
ORDER BY delta_episodes;
