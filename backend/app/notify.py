"""D09 seam — notify external surfaces (Slack / GitHub / X via Composio) when
sentinel detects a claim-change re-audit.

Same shape as publish.py: wired NOW so D09 lights up the moment COMPOSIO_API_KEY
lands. Until then, no-op + log. Never raises."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.config import settings


log = logging.getLogger("sentinel.notify")


@dataclass(frozen=True)
class SentinelDelta:
    """The change envelope handed to notify(). Compact on purpose — Composio
    actions take short payloads better than full MarketResult dumps."""
    vendor: str
    url: str
    old_score: Optional[float]
    new_score: Optional[float]
    published_url: Optional[str] = None


async def notify(delta: SentinelDelta) -> None:
    """No-op until COMPOSIO_API_KEY is set. WARNING-level for the same reason
    as publish.py — this is an observable seam, not chatter."""
    if not settings.COMPOSIO_API_KEY:
        log.warning(
            "notify skipped: no key (COMPOSIO_API_KEY unset; vendor=%s %s→%s)",
            delta.vendor,
            delta.old_score,
            delta.new_score,
        )
        return

    # D09 implementation: pick a Composio action (Slack post / GitHub issue
    # / X tweet — whichever auth'd fastest at the venue) and dispatch.
    log.warning("notify stub reached with COMPOSIO_API_KEY set but no implementation (D09)")
