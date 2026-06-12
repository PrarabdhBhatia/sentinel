# Airbyte + ClickHouse Cloud, no Docker

Sentinel does not need Docker. The backend writes telemetry to local JSONL files
by default, and can also stream each event to ClickHouse Cloud when these env
vars are set:

```bash
CLICKHOUSE_URL=https://<host>:8443
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=<password>
CLICKHOUSE_DATABASE=default
```

Run the app normally:

```bash
cd backend
uv run uvicorn app.server:app --port 8010
```

Each telemetry event is inserted into a `telemetry` table with fields for
`run_id`, `stage`, `vendor`, `model`, `tier`, token counts, cost, latency,
escalation, and raw payload JSON.

## Where Airbyte Fits

Use Airbyte Cloud when you want a managed connector UI without running Docker
locally:

1. Create an Airbyte Cloud workspace.
2. Add ClickHouse Cloud as the destination.
3. Choose a source that matters for the demo, such as Google Sheets, GitHub,
   Slack, HubSpot, or Postgres.
4. Sync that source into ClickHouse next to Sentinel's `telemetry` table.
5. Query both datasets in ClickHouse for the demo.

Good demo line:

> Airbyte brings external market context into ClickHouse, while Sentinel streams
> live audit telemetry into the same warehouse.

This keeps Airbyte load-bearing without making the local demo depend on Docker.

## Demo Queries

```sql
SELECT
  stage,
  count() AS events,
  round(sum(cost_usd), 4) AS cost_usd
FROM telemetry
GROUP BY stage
ORDER BY events DESC;
```

```sql
SELECT
  vendor,
  countIf(escalated = 1) AS escalations,
  count() AS events
FROM telemetry
GROUP BY vendor
ORDER BY escalations DESC;
```

```sql
SELECT
  tier,
  count() AS calls,
  round(avg(latency_ms), 1) AS avg_latency_ms,
  round(sum(cost_usd), 4) AS cost_usd
FROM telemetry
WHERE model IS NOT NULL
GROUP BY tier;
```
