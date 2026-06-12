"""Stage INGEST. URL -> markdown text. Primary: httpx + trafilatura. Fallback:
Jina Reader (r.jina.ai/ prefix) for JS-heavy pages. Hard fail -> grey card
'unreachable — skipped'. Failure is a STATE, never a propagated exception.

NEVER use Browser Use here. NEVER fetch G2/Capterra directly (they block) —
that's Stage B's snippet-only constraint, mentioned here as cross-ref."""

from __future__ import annotations

import re

import httpx
import trafilatura  # type: ignore[import-untyped]

from app import cache
from app.config import settings
from app.telemetry import TelemetryBus, measure

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Enterprise SaaS sites that render entirely in JS — skip httpx, go straight
# to Jina Reader which handles these reliably.
_JINA_FIRST_DOMAINS = {
    "intercom.com",
    "zendesk.com",
    "freshworks.com",
    "salesforce.com",
    "hubspot.com",
    "servicenow.com",
    "workday.com",
    "atlassian.com",
    "notion.so",
    "linear.app",
}


async def ingest(url: str, *, bus: TelemetryBus, vendor: str | None = None) -> str:
    """Fetch `url`, return clean markdown text. On any failure return an empty
    string and leave the per-vendor status='unreachable' decision to the
    orchestrator (this stage's contract is text-or-empty, not text-or-raise)."""
    async with measure(bus, stage="ingest", vendor=vendor) as _m:
        cached = cache.get("ingest", url)
        if cached is not None:
            return cached

        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lstrip("www.")
            jina_first = any(domain.endswith(d) for d in _JINA_FIRST_DOMAINS)

            async with httpx.AsyncClient(
                timeout=settings.SCRAPE_TIMEOUT_S,
                follow_redirects=True,
                headers=_HEADERS,
            ) as http:
                if jina_first:
                    text = await _jina_fallback(http, url)
                    if len(text.strip()) < 200:
                        resp = await http.get(url)
                        text = trafilatura.extract(
                            resp.text,
                            include_links=False,
                            include_images=False,
                            favor_recall=True,
                        ) or text
                else:
                    resp = await http.get(url)
                    if resp.status_code >= 400:
                        return await _jina_fallback(http, url)
                    text = trafilatura.extract(
                        resp.text,
                        include_links=False,
                        include_images=False,
                        favor_recall=True,
                    ) or ""
                    if len(text.strip()) < 200:
                        text = await _jina_fallback(http, url) or text
                result = text[:15_000]
                if result.strip():
                    cache.set("ingest", url, result)
                return result
        except Exception:
            return ""


_JINA_NOISE_RE = re.compile(
    r"(!\[Image\s*\d*\]|imagedelivery\.net|cdn\.|clickagy|tracking|utm_|clkgy|pixel\.gif)",
    re.IGNORECASE,
)


def _clean_jina_markdown(raw: str) -> str:
    """Strip Jina Reader output of image-link noise and nav-only lines so the
    LLM extractor receives clean prose, not markdown soup."""
    cleaned = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Title:") or stripped.startswith("URL Source"):
            continue
        if _JINA_NOISE_RE.search(stripped):
            continue
        # Nav-only lines: pure markdown links with no surrounding text
        if re.fullmatch(r"\[.*?\]\(https?://[^\)]+\)", stripped):
            continue
        # Lines under 20 chars after stripping markdown are just noise
        text_only = re.sub(r"\[([^\]]*)\]\([^\)]*\)", r"\1", stripped)
        if len(text_only.strip()) < 20:
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)


async def _jina_fallback(http: httpx.AsyncClient, url: str) -> str:
    """Use Jina Reader as a fallback for JS-heavy or blocked pages."""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        resp = await http.get(jina_url, timeout=settings.SCRAPE_TIMEOUT_S * 2)
        if resp.status_code < 400 and resp.text.strip():
            return _clean_jina_markdown(resp.text)[:15_000]
    except Exception:
        pass
    return ""


async def fetch_text_uncached(url: str) -> str:
    """Same fetch path as ingest() — trafilatura with Jina Reader fallback —
    but bypasses both cache reads and writes and emits no telemetry. The
    sentinel loop uses this to peek at fresh content for change-detection
    without polluting the per-run bus or stale cache state.

    Loopback URLs (our /test-vendor/* served by FastAPI) come back as plain
    HTML which trafilatura handles. On any failure: return empty string —
    the sentinel loop treats unreachable as 'no change'."""
    try:
        async with httpx.AsyncClient(
            timeout=settings.SCRAPE_TIMEOUT_S,
            follow_redirects=True,
            headers=_HEADERS,
        ) as http:
            resp = await http.get(url)
            if resp.status_code >= 400:
                return await _jina_fallback(http, url)
            text = trafilatura.extract(
                resp.text,
                include_links=False,
                include_images=False,
                favor_recall=True,
            ) or ""
            if len(text.strip()) < 200:
                # Test page may legitimately be short — accept the raw text
                # before falling back to Jina (which would just re-fetch).
                if not text.strip():
                    text = await _jina_fallback(http, url)
            return text[:15_000]
    except Exception:
        return ""
