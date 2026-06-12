"""D08 backfill — load historical telemetry JSONL into ClickHouse.

Reads every run_*.jsonl under the given directories (default: app/logs/ and an
optional telemetry_history/) and batch-inserts each line as a telemetry row,
reusing the same table + tier logic as the live sink.

Usage:
    uv run python scripts/backfill_clickhouse.py
    uv run python scripts/backfill_clickhouse.py /path/to/history_dir
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain file (`python scripts/backfill_clickhouse.py`): put
# the backend root on sys.path so `app` imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import orjson

from app.ch_sink import sink
from app.schemas import TelemetryEvent

APP_DIR = Path(__file__).resolve().parents[1] / "app"
DEFAULT_DIRS = [APP_DIR / "logs", APP_DIR.parent / "telemetry_history"]


def _tier(model: str | None) -> str:
    if not model:
        return "tool"
    m = model.lower()
    return "cheap" if any(x in m for x in ("cheap", "haiku", "qwen", "pioneer")) else "premium"


def _rows_from_file(path: Path):
    run_id = path.stem.removeprefix("run_")
    rows = []
    for line in path.read_bytes().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = TelemetryEvent.model_validate(orjson.loads(line))
        except Exception:
            continue
        payload = orjson.dumps(ev.payload).decode("utf-8") if ev.payload is not None else ""
        rows.append([
            run_id, ev.ts, ev.stage, ev.vendor, ev.model, _tier(ev.model),
            ev.tokens_in, ev.tokens_out, ev.cost_usd, ev.latency_ms, ev.ttft_ms,
            1 if ev.escalated else 0, ev.claim_id, payload,
        ])
    return run_id, rows


COLUMNS = [
    "run_id", "ts", "stage", "vendor", "model", "tier", "tokens_in",
    "tokens_out", "cost_usd", "latency_ms", "ttft_ms", "escalated",
    "claim_id", "payload",
]


def main() -> int:
    dirs = [Path(a) for a in sys.argv[1:]] or DEFAULT_DIRS
    if not sink.enabled:
        print("CLICKHOUSE_URL not set — nothing to do.")
        return 1
    client = sink._connect()
    if client is None:
        print("Could not connect to ClickHouse.")
        return 1

    files = []
    for d in dirs:
        if d.exists():
            files.extend(sorted(d.glob("run_*.jsonl")))
    if not files:
        print(f"No run_*.jsonl files found under: {', '.join(str(d) for d in dirs)}")
        print("Live runs append to app/logs/ as audits execute — re-run this after a sweep.")
        return 0

    total_rows = 0
    for path in files:
        run_id, rows = _rows_from_file(path)
        if rows:
            client.insert(
                "telemetry",
                rows,
                column_names=COLUMNS,
                settings={"async_insert": 1, "wait_for_async_insert": 0},
            )
            total_rows += len(rows)
        print(f"  {path.name}: {len(rows)} events")
    print(f"\nBackfilled {total_rows} events from {len(files)} run(s) into ClickHouse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
