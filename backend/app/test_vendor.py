"""Fictional test vendor — Nimbus Support AI.

The demo lever. On stage we POST a new puffy claim to /test-vendor/nimbus and
the sentinel loop autonomously detects the diff and re-audits.

FICTIONAL by design: a real company's score being live-edited on stage is
defamation theatre. Nimbus is invented — name, claims, score motion are all
ours to control. Per the constitution: NEVER live-edit a real vendor.

Storage is process-memory (no DB). The text is served as a small HTML doc
so trafilatura's extractor pulls the claims out as plain text — which is
what ingest sha256s for change detection."""

from __future__ import annotations

import asyncio
import html
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NimbusState:
    headline: str = "The fastest AI customer-support agent in the industry."
    tagline: str = (
        "Industry-leading deflection, autonomous resolution, "
        "and a model trained on more conversations than anyone else."
    )
    claims: list[str] = field(default_factory=lambda: [
        "99.99% accuracy on customer support queries",
        "Sub-second median response time across every channel",
        "70% cost reduction vs human agents in the first month",
        "10x faster resolution than legacy support tools",
    ])
    last_modified_ts: float = 0.0
    _lock: Optional[asyncio.Lock] = None

    def __post_init__(self) -> None:
        # Lazy: created on first mutation so the dataclass is still picklable
        # for any future state-serialization needs.
        self._lock = None

    async def _ensure_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock


# Process-singleton — the dispatch's "in memory/file" budget.
_STATE = NimbusState()


def state() -> NimbusState:
    return _STATE


def render_html() -> str:
    """Render the current Nimbus marketing page. Keep the markup honest HTML
    so trafilatura yields stable plain text — the sentinel loop hashes the
    extracted text, not the raw HTML."""
    s = _STATE
    claim_items = "\n      ".join(
        f"<li>{html.escape(claim)}</li>" for claim in s.claims
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Nimbus Support AI — Marketing</title>
  </head>
  <body>
    <article>
      <h1>Nimbus Support AI</h1>
      <p><strong>{html.escape(s.headline)}</strong></p>
      <p>{html.escape(s.tagline)}</p>
      <section>
        <h2>What we deliver</h2>
        <ul>
      {claim_items}
        </ul>
      </section>
      <footer>
        <p>© Nimbus Support AI — a fictional vendor for Sentinel testing.</p>
      </footer>
    </article>
  </body>
</html>
"""


async def update(
    *,
    headline: Optional[str] = None,
    tagline: Optional[str] = None,
    claims: Optional[list[str]] = None,
) -> NimbusState:
    """Replace any of headline/tagline/claims. None means 'keep'. Returns the
    fresh state for the response body."""
    s = _STATE
    lock = await s._ensure_lock()
    async with lock:
        if headline is not None:
            s.headline = headline
        if tagline is not None:
            s.tagline = tagline
        if claims is not None:
            # Defensive copy + str coerce — POST bodies arrive as JSON arrays.
            s.claims = [str(c).strip() for c in claims if str(c).strip()]
        import time
        s.last_modified_ts = time.time()
    return s
