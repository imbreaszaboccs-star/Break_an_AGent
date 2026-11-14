-- ClickHouse schema for OnCall rollouts. Rows are exactly what src/oncall/logsink.py writes (JSONEachRow):
--   call row : type='call',  episode, scenario, i, tool, args{}, t_before, t_after, result{}
--   final row: type='final', episode, scenario, score, tags[], breakdown{}, truth{faults, herring}
-- Nested objects are stored as JSON text (String) and read with JSONExtract*. Missing fields fall back to defaults.
-- The inserts need  input_format_skip_unknown_fields=1  and  input_format_json_read_objects_as_strings=1
-- (analysis/load.py sets them per request; for logsink's direct insert set them on the user/profile, UNVERIFIED on Aiven).

CREATE TABLE IF NOT EXISTS oncall_rollouts
(
    type       LowCardinality(String),
    episode    String,
    scenario   String,
    i          UInt16 DEFAULT 0,
    tool       LowCardinality(String) DEFAULT '',
    args       String DEFAULT '',
    t_before   Int32 DEFAULT 0,
    t_after    Int32 DEFAULT 0,
    result     String DEFAULT '',
    score      Float64 DEFAULT 0,
    tags       Array(String),
    breakdown  String DEFAULT '',
    truth      String DEFAULT '',
    -- derived from the episode id: `<policy>[-r<run>]-<scenario>`, e.g. agent_vllm_gemma-ft-r2-eas-f1-10000
    policy     LowCardinality(String) MATERIALIZED replaceRegexpOne(replaceOne(episode, concat('-', scenario), ''), '-r[0-9]+$', ''),
    run        UInt16 MATERIALIZED toUInt16OrZero(extract(replaceOne(episode, concat('-', scenario), ''), '-r([0-9]+)$')),
    difficulty LowCardinality(String) MATERIALIZED multiIf(startsWith(scenario, 'med'), 'medium', startsWith(scenario, 'exp'), 'expert', 'hard'),
    -- ponytail: family label is parsed from the scenario id (`<diff>-f<N>-<seed>`); adjust if the id format changes.
    family     LowCardinality(String) MATERIALIZED upper(extract(scenario, '-(f[0-9]+)-'))
)
ENGINE = MergeTree
ORDER BY (policy, scenario, episode, type, i);

-- one row per episode, with the score components pulled out of the breakdown
CREATE VIEW IF NOT EXISTS oncall_episodes AS
SELECT
    policy, run, episode, scenario, difficulty, family, score, tags,
    JSONExtractFloat(breakdown, 'R_avail')      AS r_avail,
    JSONExtractFloat(breakdown, 'R_fixed')      AS r_fixed,
    JSONExtractFloat(breakdown, 'R_diag')       AS r_diag,
    JSONExtractFloat(breakdown, 'P_collateral') AS p_collateral,
    JSONExtractUInt(breakdown, 'n_calls')       AS n_calls,
    arrayMap(x -> JSONExtractString(x, 'node'), JSONExtractArrayRaw(truth, 'faults')) AS fault_nodes
FROM oncall_rollouts
WHERE type = 'final';
