"""Optional ClickHouse telemetry sink.

The JSONL log remains the authoritative replay source. This module is a
best-effort warehouse sink for demo analytics: if ClickHouse is unavailable,
pipeline telemetry must continue without blocking or surfacing errors.
"""

from __future__ import annotations

import asyncio
import time
from threading import Lock
from urllib.parse import urlparse

import clickhouse_connect
import orjson

from app.config import settings
from app.schemas import TelemetryEvent


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS telemetry (
    run_id String,
    ts DateTime64(3, 'UTC'),
    stage String,
    vendor Nullable(String),
    model Nullable(String),
    tier String,
    tokens_in UInt64,
    tokens_out UInt64,
    cost_usd Float64,
    latency_ms Float64,
    ttft_ms Nullable(Float64),
    escalated UInt8,
    claim_id Nullable(String),
    payload String
) ENGINE = MergeTree
ORDER BY (run_id, ts, stage)
"""


class ClickHouseSink:
    def __init__(self) -> None:
        self._client = None
        self._lock = Lock()
        self._disabled_until = 0.0

    @property
    def enabled(self) -> bool:
        return bool(settings.CLICKHOUSE_URL)

    def _connect(self):
        if not self.enabled:
            return None
        if time.monotonic() < self._disabled_until:
            return None
        if self._client is not None:
            return self._client

        with self._lock:
            if self._client is not None:
                return self._client
            parsed = urlparse(settings.CLICKHOUSE_URL)
            secure = parsed.scheme == "https"
            host = parsed.hostname or "localhost"
            port = parsed.port or (8443 if secure else 8123)
            username = parsed.username or settings.CLICKHOUSE_USER
            password = parsed.password or settings.CLICKHOUSE_PASSWORD
            database = (parsed.path or "").strip("/") or settings.CLICKHOUSE_DATABASE
            kwargs = dict(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                secure=secure,
            )
            if secure:
                # macOS Python ships without a usable system CA bundle, so TLS to
                # ClickHouse Cloud fails with CERTIFICATE_VERIFY_FAILED. Point the
                # driver at certifi's bundle (already in the dep tree via httpx).
                try:
                    import certifi

                    kwargs["ca_cert"] = certifi.where()
                except Exception:
                    pass
            client = clickhouse_connect.get_client(**kwargs)
            client.command(_CREATE_TABLE_SQL)
            self._client = client
            return client

    def insert_event_sync(self, run_id: str, event: TelemetryEvent) -> None:
        client = self._connect()
        if client is None:
            return

        payload = ""
        if event.payload is not None:
            payload = orjson.dumps(event.payload).decode("utf-8")

        model = event.model or ""
        tier = "tool"
        if model:
            tier = "cheap" if any(x in model.lower() for x in ("cheap", "haiku", "qwen", "pioneer")) else "premium"

        client.insert(
            "telemetry",
            [
                [
                    run_id,
                    event.ts,
                    event.stage,
                    event.vendor,
                    event.model,
                    tier,
                    event.tokens_in,
                    event.tokens_out,
                    event.cost_usd,
                    event.latency_ms,
                    event.ttft_ms,
                    1 if event.escalated else 0,
                    event.claim_id,
                    payload,
                ]
            ],
            column_names=[
                "run_id",
                "ts",
                "stage",
                "vendor",
                "model",
                "tier",
                "tokens_in",
                "tokens_out",
                "cost_usd",
                "latency_ms",
                "ttft_ms",
                "escalated",
                "claim_id",
                "payload",
            ],
            settings={"async_insert": 1, "wait_for_async_insert": 0},
        )

    async def insert_event(self, run_id: str, event: TelemetryEvent) -> None:
        try:
            await asyncio.to_thread(self.insert_event_sync, run_id, event)
        except Exception:
            self._client = None
            self._disabled_until = time.monotonic() + 30.0


sink = ClickHouseSink()


def emit_telemetry_event(run_id: str, event: TelemetryEvent) -> None:
    """Schedule a ClickHouse insert when a running event loop exists."""
    if not sink.enabled:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(sink.insert_event(run_id, event))
