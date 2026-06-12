"""D09 — notify external surfaces via Composio when Sentinel detects a
claim-change re-audit.

Flow:
  1. Check which apps the user has connected in Composio (Slack, GitHub, etc.).
  2. Dispatch to the first available connected app in priority order.
  3. Never raises — notify is fire-and-forget on the demo path.

Priority: Slack → GitHub Issues → fallback log."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings


log = logging.getLogger("sentinel.notify")

_COMPOSIO_BASE = "https://backend.composio.dev/api/v1"


@dataclass(frozen=True)
class SentinelDelta:
    """Change envelope handed to notify(). Compact — Composio actions take
    short payloads better than full MarketResult dumps."""
    vendor: str
    url: str
    old_score: Optional[float]
    new_score: Optional[float]
    published_url: Optional[str] = None


def _delta_text(delta: SentinelDelta) -> str:
    old = f"{round((delta.old_score or 0) * 100)}%" if delta.old_score is not None else "n/a"
    new = f"{round((delta.new_score or 0) * 100)}%" if delta.new_score is not None else "n/a"
    direction = "▲" if (delta.new_score or 0) > (delta.old_score or 0) else "▼"
    pub = f"\n📄 Published: {delta.published_url}" if delta.published_url else ""
    return (
        f"🔔 *Sentinel detected a claim change*\n"
        f"*Vendor:* {delta.vendor} ({delta.url})\n"
        f"*Score:* {old} → {new} {direction}{pub}\n"
        f"_Sentinel re-audited this vendor because its marketing page changed._"
    )


async def _get_connected_apps(http: httpx.AsyncClient) -> list[str]:
    """Return list of app slugs the user has connected in Composio."""
    try:
        resp = await http.get(
            f"{_COMPOSIO_BASE}/connectedAccounts",
            headers={"x-api-key": settings.COMPOSIO_API_KEY},
            timeout=8.0,
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        items = data.get("items", [])
        return [item.get("appName", "").lower() for item in items if item.get("status") == "ACTIVE"]
    except Exception:
        return []


async def _execute_action(
    http: httpx.AsyncClient, action: str, params: dict
) -> bool:
    """Execute a Composio action. Returns True on success."""
    try:
        resp = await http.post(
            f"{_COMPOSIO_BASE}/actions/{action}/execute",
            headers={
                "x-api-key": settings.COMPOSIO_API_KEY,
                "Content-Type": "application/json",
            },
            json={"entityId": "default", "input": params},
            timeout=10.0,
        )
        if resp.status_code >= 400:
            log.warning("composio action %s failed: HTTP %s", action, resp.status_code)
            return False
        return True
    except Exception as exc:
        log.warning("composio action %s error: %s", action, exc)
        return False


async def notify(delta: SentinelDelta) -> None:
    """Dispatch a claim-change alert via the first available Composio-connected
    surface. No-op (with log) if COMPOSIO_API_KEY is unset."""
    if not settings.COMPOSIO_API_KEY:
        log.warning(
            "notify skipped: no key (COMPOSIO_API_KEY unset; vendor=%s %s→%s)",
            delta.vendor,
            delta.old_score,
            delta.new_score,
        )
        return

    message = _delta_text(delta)

    async with httpx.AsyncClient() as http:
        apps = await _get_connected_apps(http)
        log.warning("notify: connected apps=%s vendor=%s", apps, delta.vendor)

        # Slack — preferred surface for demo
        if "slack" in apps:
            ok = await _execute_action(
                http,
                "SLACKBOT_SENDS_A_MESSAGE_TO_A_CHANNEL_OR_A_DIRECT_MESSAGE",
                {"channel": "sentinel-alerts", "text": message},
            )
            if ok:
                log.warning("notify OK via Slack: vendor=%s", delta.vendor)
                return

        # GitHub — create an issue as a claim-change alert
        if "github" in apps:
            ok = await _execute_action(
                http,
                "GITHUB_CREATE_AN_ISSUE",
                {
                    "owner": "sentinel",
                    "repo": "alerts",
                    "title": f"Claim change: {delta.vendor}",
                    "body": message,
                    "labels": ["sentinel", "claim-change"],
                },
            )
            if ok:
                log.warning("notify OK via GitHub: vendor=%s", delta.vendor)
                return

        # Nothing connected yet — log with enough context for the dashboard
        log.warning(
            "notify: no connected app dispatched (apps=%s vendor=%s old=%s new=%s)",
            apps,
            delta.vendor,
            delta.old_score,
            delta.new_score,
        )
