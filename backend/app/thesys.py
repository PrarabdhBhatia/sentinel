"""D10 — 'Interrogate the market' — streams Claude responses grounded in
live Sentinel audit data. Uses ANTHROPIC_API_KEY directly (no Thesys billing
required). THESYS_C1_API_KEY is kept in config but no longer required."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from app.config import settings
from app.schemas import MarketResult


log = logging.getLogger("sentinel.interrogate")


def _market_context(market: MarketResult) -> str:
    lines = [
        f"SENTINEL LIVE MARKET DATA — {market.category}",
        f"Claim Inflation Index: {market.claim_inflation_index:.2f}x",
        f"Vendors audited: {len(market.vendors)}",
        "",
    ]
    for v in sorted(market.vendors, key=lambda x: x.credibility_score or 0, reverse=True):
        score = f"{round((v.credibility_score or 0) * 100)}%" if v.credibility_score is not None else "n/a"
        n_total = len(v.judgments)
        n_pub  = sum(1 for j in v.judgments if j.verdict.value == "SUPPORTED")
        n_self = sum(1 for j in v.judgments if j.verdict.value == "SELF_REPORTED_ONLY")
        n_none = sum(1 for j in v.judgments if j.verdict.value == "NO_PUBLIC_RECEIPT_FOUND")
        lines.append(
            f"{v.vendor} ({v.url}): credibility={score}, "
            f"claims={n_total} [{n_pub} SUPPORTED / {n_self} SELF_REPORTED_ONLY / {n_none} NO_PUBLIC_RECEIPT_FOUND]"
        )
        for claim, judgment in zip(v.claims[:5], v.judgments[:5]):
            lines.append(f"  • [{judgment.verdict.value}] {claim.claim[:120]}")
    return "\n".join(lines)


_SYSTEM_PROMPT = """\
You are Sentinel's market intelligence assistant. Sentinel autonomously audits
software vendor marketing claims against public evidence.

Three verdict labels:
- SUPPORTED: independent public sources corroborate the claim
- SELF_REPORTED_ONLY: claim appears only on the vendor's own pages
- NO_PUBLIC_RECEIPT_FOUND: no public evidence found

Live audit data:
{market_context}

Answer the user's question directly and concisely, grounded in the data above.
Use markdown for tables or lists when it helps clarity."""


async def stream_interrogate(
    message: str,
    history: list[dict],
    market: MarketResult,
) -> AsyncIterator[str]:
    """Stream a Claude response grounded in live market data."""

    if not settings.ANTHROPIC_API_KEY:
        yield json.dumps({"type": "error", "content": "ANTHROPIC_API_KEY not set."})
        return

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        system = _SYSTEM_PROMPT.format(market_context=_market_context(market))

        messages = []
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        async with client.messages.stream(
            model=settings.PREMIUM_MODEL or "claude-sonnet-4-5",
            system=system,
            messages=messages,
            max_tokens=1024,
        ) as stream:
            async for delta in stream.text_stream:
                yield json.dumps({"type": "delta", "content": delta})

        yield json.dumps({"type": "done"})

    except Exception as exc:
        log.warning("interrogate stream error: %s", exc)
        yield json.dumps({"type": "error", "content": str(exc)})
