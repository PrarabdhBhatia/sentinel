"""D04 — publish a finalized MarketResult to Senso KB + cited.md.

Flow:
  1. Format the MarketResult as a structured markdown audit document.
  2. POST to Senso KB via /org/kb/raw — stores it as a searchable KB document.
  3. Return the cited.md URL for this category.

Failure is always non-fatal — publish is fire-and-forget on the demo path.
The audit cache is the source of truth; this published copy is the mirror."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.schemas import MarketResult, Verdict


log = logging.getLogger("sentinel.publish")

_SENSO_BASE = "https://apiv2.senso.ai/api/v1"


def _format_audit_markdown(market: MarketResult) -> str:
    """Render MarketResult as a rich markdown document suitable for cited.md."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    category_slug = market.category.lower().replace(" ", "-")

    lines: list[str] = [
        f"# Sentinel Audit: {market.category}",
        f"",
        f"**Audited:** {ts}  ",
        f"**Methodology:** We measure *public substantiation*, never truth.  ",
        f"Verdicts: `PUBLICLY_SUBSTANTIATED` / `SELF_REPORTED_ONLY` / `NO_PUBLIC_RECEIPT_FOUND`  ",
        f"Absence of a public receipt is not proof of falsity.",
        f"",
        f"---",
        f"",
        f"## Market Overview",
        f"",
        f"- **Vendors audited:** {len(market.vendors)}",
        f"- **Claim Inflation Index:** {market.claim_inflation_index:.2f}x",
        f"  *(claims made ÷ claims publicly substantiated)*",
        f"",
        f"---",
        f"",
        f"## Vendor Leaderboard",
        f"",
    ]

    ranked = sorted(
        [v for v in market.vendors if v.credibility_score is not None],
        key=lambda v: v.credibility_score or 0,
        reverse=True,
    )
    unranked = [v for v in market.vendors if v.credibility_score is None]

    for i, vendor in enumerate(ranked, 1):
        score_pct = round((vendor.credibility_score or 0) * 100)
        n_total = len(vendor.judgments)
        n_pub = sum(1 for j in vendor.judgments if j.verdict == Verdict.SUPPORTED)
        n_self = sum(1 for j in vendor.judgments if j.verdict == Verdict.SELF_REPORTED_ONLY)
        n_none = sum(1 for j in vendor.judgments if j.verdict == Verdict.NO_PUBLIC_RECEIPT_FOUND)

        lines += [
            f"### {i}. {vendor.vendor}",
            f"",
            f"**URL:** {vendor.url}  ",
            f"**Credibility score:** {score_pct}%  ",
            f"**Claims:** {n_total} total — "
            f"{n_pub} PUBLICLY_SUBSTANTIATED · {n_self} SELF_REPORTED_ONLY · {n_none} NO_PUBLIC_RECEIPT_FOUND",
            f"",
        ]

        substantiated = [j for j in vendor.judgments if j.verdict == Verdict.SUPPORTED]
        if substantiated:
            lines.append("**Publicly substantiated claims:**")
            lines.append("")
            for j in substantiated[:5]:
                claim_text = next(
                    (c.claim for c in vendor.claims if c.claim_id == j.claim_id), j.claim_id
                )
                lines.append(f"- ✓ {claim_text}")
                if j.receipts:
                    for r in j.receipts[:2]:
                        lines.append(f"  - Source: {r}")
            lines.append("")

        if vendor.advice:
            lines += [f"**Buyer guidance:** {vendor.advice}", ""]

    for vendor in unranked:
        lines += [
            f"### {vendor.vendor}",
            f"",
            f"**URL:** {vendor.url}  ",
            f"**Status:** {vendor.status.replace('_', ' ')}",
            f"",
        ]

    lines += [
        "---",
        "",
        f"## About Sentinel",
        "",
        "Sentinel autonomously audits software vendor marketing pages, verifies every "
        "claim against public evidence via a cost-aware inference cascade, and publishes "
        "machine-readable trust data that AI agents can access via micropayment.",
        "",
        f"Category slug: `{category_slug}`  ",
        f"Next audit: automatic (watch interval {settings.WATCH_INTERVAL_S}s)",
        "",
        "---",
        "",
        "*Powered by Senso — your AI-searchable knowledge base.*",
    ]

    return "\n".join(lines)


async def publish(market: MarketResult) -> Optional[str]:
    """Format and push a MarketResult to the Senso KB. Returns the cited.md URL
    on success, None on skip or failure. Never raises."""
    if not settings.SENSO_API_KEY:
        log.warning(
            "publish skipped: no key (SENSO_API_KEY unset; category=%s n_vendors=%d)",
            market.category,
            len(market.vendors),
        )
        return None

    markdown = _format_audit_markdown(market)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    title = f"{ts} — Sentinel Audit: {market.category}"
    category_slug = market.category.lower().replace(" ", "-")

    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                f"{_SENSO_BASE}/org/kb/raw",
                headers={
                    "x-api-key": settings.SENSO_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"title": title, "text": markdown},
            )
            if resp.status_code >= 400:
                log.warning(
                    "publish failed: HTTP %s — %s", resp.status_code, resp.text[:200]
                )
                return None

            data = resp.json()
            kb_node_id = data.get("kb_node_id", "")
            url = f"https://cited.md/sentinel/{category_slug}"
            log.warning(
                "publish OK: kb_node_id=%s category=%s url=%s",
                kb_node_id,
                market.category,
                url,
            )
            return url

    except Exception as exc:
        log.warning("publish error: %s", exc)
        return None
