-- Failure-tag distribution per policy: episodes carrying each tag and their share of the policy's episodes.
WITH totals AS (SELECT policy, count() AS episodes FROM oncall_episodes GROUP BY policy)
SELECT e.policy AS policy, tag, count() AS episodes_with_tag, round(count() / any(t.episodes), 3) AS share
FROM oncall_episodes AS e
ARRAY JOIN e.tags AS tag
INNER JOIN totals AS t ON t.policy = e.policy
GROUP BY e.policy, tag
ORDER BY policy, episodes_with_tag DESC;
