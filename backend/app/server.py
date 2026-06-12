"""FastAPI surface.

POST /audit                       — start a run, returns its run_id (D00)
GET  /audit/{run_id}/stream       — per-run SSE telemetry (D00)
GET  /audit/{run_id}/results      — per-run partial/final MarketResult (D00)
GET  /healthz                     — liveness

D03 additions (sentinel autonomy layer):
GET  /test-vendor/nimbus          — fictional editable vendor page (HTML)
POST /test-vendor/nimbus          — replace claims on the test page (JSON)
GET  /sentinel/status             — live watcher state (watching/triggers/etc.)
GET  /activity/stream             — SSE of the global activity bus
                                    (every sentinel_trigger + per-trigger
                                    pipeline event, ready for D07's feed)
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from app import sentinel, test_vendor
from app.telemetry import TelemetryBus


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Start the sentinel loop on boot, cancel on shutdown. Lazy state init
    means the watcher's MarketResult and activity bus exist before the first
    request hits the dashboard."""
    await sentinel.start()
    try:
        yield
    finally:
        await sentinel.stop()


app = FastAPI(
    title="Sentinel — Autonomous burden of proof for the agentic web",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# run_id -> bus. In-memory is fine for the demo (single process, no restart).
_RUNS: dict[str, TelemetryBus] = {}
# run_id -> task running the orchestrator. Held so we don't GC the coroutine.
_TASKS: dict[str, asyncio.Task] = {}


class AuditRequest(BaseModel):
    category: str
    vendor_urls: list[tuple[str, str]] = Field(
        ...,
        description="List of (vendor_name, url) tuples to audit.",
    )
    naive: bool = False
    n: Optional[int] = None


class AuditAccepted(BaseModel):
    run_id: str
    stream_url: str
    results_url: str


@app.post("/audit", response_model=AuditAccepted)
async def audit(req: AuditRequest) -> AuditAccepted:
    bus = TelemetryBus()
    _RUNS[bus.run_id] = bus

    from app.pipeline.orchestrator import run_market

    task = asyncio.create_task(
        run_market(
            req.category,
            req.vendor_urls,
            bus=bus,
            naive=req.naive,
            n=req.n,
        )
    )
    _TASKS[bus.run_id] = task

    return AuditAccepted(
        run_id=bus.run_id,
        stream_url=f"/audit/{bus.run_id}/stream",
        results_url=f"/audit/{bus.run_id}/results",
    )


@app.get("/audit/{run_id}/stream")
async def stream(run_id: str) -> EventSourceResponse:
    bus = _RUNS.get(run_id)
    if bus is None:
        raise HTTPException(status_code=404, detail="run not found")

    queue = bus.subscribe()

    async def gen():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue
                yield {
                    "event": "telemetry",
                    "data": orjson.dumps(event.model_dump(mode="json")).decode("utf-8"),
                }
                if event.stage == "market_done":
                    break
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(gen())


@app.get("/audit/{run_id}/results")
async def results(run_id: str) -> Any:
    """Returns partial or final MarketResult as the audit progresses."""
    bus = _RUNS.get(run_id)
    if bus is None:
        raise HTTPException(status_code=404, detail="run not found")

    task = _TASKS.get(run_id)
    partial = bus.partial_result

    if task and task.done() and not task.exception():
        final = task.result()
        return orjson.loads(orjson.dumps(final.model_dump(mode="json")))

    if partial is not None:
        return orjson.loads(orjson.dumps(partial.model_dump(mode="json")))  # type: ignore[attr-defined]

    return {"category": "", "vendors": [], "claim_inflation_index": 0.0, "telemetry_summary": {}}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# D03 — Sentinel autonomy layer
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/test-vendor/nimbus", response_class=HTMLResponse)
async def test_vendor_nimbus_get() -> HTMLResponse:
    """Fictional vendor marketing page. Trafilatura extracts the claim list
    as plain text; the sentinel loop hashes that to detect changes."""
    return HTMLResponse(content=test_vendor.render_html())


class NimbusUpdate(BaseModel):
    headline: Optional[str] = None
    tagline: Optional[str] = None
    claims: Optional[list[str]] = None


@app.post("/test-vendor/nimbus")
async def test_vendor_nimbus_post(payload: NimbusUpdate) -> JSONResponse:
    """Replace any subset of headline/tagline/claims. On stage this is the
    one-line curl that triggers the autonomous re-audit within one interval."""
    s = await test_vendor.update(
        headline=payload.headline,
        tagline=payload.tagline,
        claims=payload.claims,
    )
    return JSONResponse(
        {
            "headline": s.headline,
            "tagline": s.tagline,
            "claims": s.claims,
            "last_modified_ts": s.last_modified_ts,
        }
    )


@app.get("/sentinel/status")
async def sentinel_status() -> dict:
    return sentinel.status_snapshot()


@app.get("/activity/stream")
async def activity_stream(request: Request) -> EventSourceResponse:
    """Global activity feed — sentinel_trigger, every per-trigger pipeline
    stage event (ingest/extract/hunt/judge_*/advise/vendor_done), and
    sentinel_reaudit_done. D07's UI subscribes here."""
    bus = sentinel.state().activity_bus
    queue = bus.subscribe()

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue
                yield {
                    "event": "activity",
                    "data": orjson.dumps(event.model_dump(mode="json")).decode("utf-8"),
                }
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(gen())
