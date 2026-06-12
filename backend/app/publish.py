"""D04 seam — publish a finalized MarketResult to Senso / cited.md.

This module is wired into the sentinel loop NOW so D04 lights up the moment
SENSO_API_KEY lands in `.env`. Until then, `publish()` is a no-op that logs
its skip reason. The seam keeps `sentinel.py` agnostic of publisher details.

Return contract (D04 will preserve): published URL on success, None on skip
or failure. Failure must never raise — publish is fire-and-forget on the
demo path; the audit is the source of truth, the published copy is a mirror."""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings
from app.schemas import MarketResult


log = logging.getLogger("sentinel.publish")


async def publish(market: MarketResult) -> Optional[str]:
    """No-op until SENSO_API_KEY is set. Logs the skip so the activity feed
    can show 'published: skipped (no key)' rather than silent absence.

    WARNING-level on purpose: this is an instrumented seam, not background
    chatter. The root logger defaults to WARNING under uvicorn — INFO would
    silently disappear and the acceptance check would have to peek at debug
    output instead of the actual server log."""
    if not settings.SENSO_API_KEY:
        log.warning(
            "publish skipped: no key (SENSO_API_KEY unset; category=%s n_vendors=%d)",
            market.category,
            len(market.vendors),
        )
        return None

    # D04 implementation lands here — POST the compiled audit to Senso's
    # publish/ingest endpoint, return the cited.md URL.
    log.warning("publish stub reached with SENSO_API_KEY set but no implementation (D04)")
    return None
