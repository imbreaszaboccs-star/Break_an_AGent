-- Mean score per policy x difficulty x family (episodes = runs x scenarios).
SELECT policy, difficulty, family, count() AS n, round(avg(score), 3) AS mean, round(stddevPop(score), 3) AS std
FROM oncall_episodes
GROUP BY policy, difficulty, family
ORDER BY policy, difficulty, family;
