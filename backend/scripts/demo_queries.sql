-- D08 demo queries — run live during the demo against ClickHouse Cloud.
-- Sentinel telemetry lands in `telemetry`; Airbyte syncs external context into
-- its own tables in the same warehouse, so both sit side by side.

-- 1) Escalation rate by run — the Pioneer adaptive-inference story.
--    The cheap judge should escalate less as it learns from its own escalations.
SELECT
    run_id,
    countIf(stage LIKE 'judge%')                       AS judgments,
    countIf(escalated = 1)                             AS escalations,
    round(100.0 * countIf(escalated = 1) / nullIf(countIf(stage LIKE 'judge%'), 0), 1) AS escalation_pct
FROM telemetry
GROUP BY run_id
ORDER BY min(ts);

-- 2) Cost per market over time — total spend per run, cheap vs premium.
SELECT
    run_id,
    any(ts)                                            AS started,
    round(sumIf(cost_usd, tier = 'cheap'), 4)          AS cheap_usd,
    round(sumIf(cost_usd, tier = 'premium'), 4)        AS premium_usd,
    round(sum(cost_usd), 4)                            AS total_usd
FROM telemetry
GROUP BY run_id
ORDER BY started;

-- 3) Most-escalated vendors all-time — where the cheap tier was least sure.
SELECT
    vendor,
    countIf(escalated = 1)                             AS escalations,
    count()                                            AS events
FROM telemetry
WHERE vendor IS NOT NULL
GROUP BY vendor
ORDER BY escalations DESC
LIMIT 10;

-- Bonus) Spend + latency by pipeline stage.
SELECT
    stage,
    count()                                            AS events,
    round(avg(latency_ms), 0)                          AS avg_latency_ms,
    round(sum(cost_usd), 4)                            AS cost_usd
FROM telemetry
GROUP BY stage
ORDER BY events DESC;
