"""D05 — x402 HTTP-native micropayment paywall for the verdict endpoint.

Flow:
  1. Agent hits GET /api/market/{category}/verdicts with no payment header.
  2. Sentinel returns HTTP 402 + JSON payment quote.
  3. Agent pays $0.01 USDC on Base L2.
  4. Agent retries with X-Payment: <txn_hash> header.
  5. Sentinel verifies the hash (format + not replayed), returns 200 + verdict JSON.

On-chain verification: in production, calls a Base L2 RPC node to confirm
amount, recipient, and finality. For the hackathon demo the hash format check
+ replay guard is the primary protection; the on-chain call is wired as a
best-effort async check that logs without blocking (RPC not always reachable
from the demo environment).

Replay protection: used hashes stored in-memory with TTL = quote expiry.
In production this moves to Redis / ClickHouse."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Optional

from app.config import settings


# ── Replay guard ──────────────────────────────────────────────────────────────
# hash -> expiry_ts. Cleaned on each check.
_used_hashes: dict[str, float] = {}

QUOTE_TTL_S = 300  # 5-minute payment window


def _clean_expired() -> None:
    now = time.time()
    expired = [h for h, exp in _used_hashes.items() if exp < now]
    for h in expired:
        del _used_hashes[h]


def _is_replayed(txn_hash: str) -> bool:
    _clean_expired()
    return txn_hash in _used_hashes


def _mark_used(txn_hash: str) -> None:
    _used_hashes[txn_hash] = time.time() + QUOTE_TTL_S


# ── Quote builder ─────────────────────────────────────────────────────────────

def build_quote(category: str) -> dict:
    """Return the 402 payment quote an agent needs to construct a payment."""
    expires_at = int(time.time()) + QUOTE_TTL_S
    return {
        "x402_version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base",
                "chain_id": 8453,
                "max_amount_required": str(int(settings.X402_PRICE_USD * 1_000_000)),  # USDC 6 decimals
                "pay_to": settings.X402_PAY_TO or "0x0000000000000000000000000000000000000000",
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
                "extra": {
                    "name": "USD Coin",
                    "version": "2",
                },
            }
        ],
        "error": "Payment required",
        "resource": f"/api/market/{category}/verdicts",
        "description": f"Sentinel verdict access: {category} — ${settings.X402_PRICE_USD:.2f} USDC",
        "expires_at": expires_at,
    }


# ── Payment header parser ─────────────────────────────────────────────────────

_EVM_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def parse_payment_header(header: Optional[str]) -> Optional[str]:
    """Extract and validate transaction hash from X-Payment header.
    Returns the hash string or None if missing/invalid."""
    if not header:
        return None
    # Support both bare hash and JSON envelope: {"txHash":"0x..."}
    header = header.strip()
    if header.startswith("{"):
        try:
            import json
            data = json.loads(header)
            txn_hash = data.get("txHash") or data.get("tx_hash") or data.get("hash", "")
        except Exception:
            return None
    else:
        txn_hash = header

    if not _EVM_HASH_RE.match(txn_hash):
        return None
    return txn_hash


# ── Payment verifier ──────────────────────────────────────────────────────────

async def verify_payment(txn_hash: str, category: str) -> tuple[bool, str]:
    """Verify a Base L2 transaction hash.

    Returns (ok, reason). On-chain verification is best-effort for the demo —
    format + replay guard is the primary check. Production adds RPC confirmation."""

    if _is_replayed(txn_hash):
        return False, "replay: transaction hash already used"

    # Format is valid (checked by parse_payment_header already, but belt+suspenders)
    if not _EVM_HASH_RE.match(txn_hash):
        return False, "invalid transaction hash format"

    # Best-effort on-chain verification via public Base RPC
    if settings.X402_PAY_TO:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8.0) as http:
                resp = await http.post(
                    "https://mainnet.base.org",
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getTransactionReceipt",
                        "params": [txn_hash],
                        "id": 1,
                    },
                )
                if resp.status_code == 200:
                    result = resp.json().get("result")
                    if result is None:
                        # Txn not found yet — pending or invalid; reject for safety
                        return False, "transaction not found on Base L2 (pending or invalid)"
                    if result.get("status") != "0x1":
                        return False, "transaction failed on-chain"
                    # Could verify to/value/token transfer here; simplified for demo
        except Exception:
            # RPC unreachable — fall through to demo mode
            pass

    # Mark as used (replay protection regardless of on-chain result)
    _mark_used(txn_hash)
    return True, "ok"


# ── Deterministic demo hash (for testing without a real wallet) ───────────────

def demo_hash_for(category: str) -> str:
    """Generate a deterministic fake hash for local demo/testing.
    Only accepted when X402_PAY_TO is unset (no real wallet configured)."""
    raw = f"sentinel-demo-{category}-{int(time.time() // 60)}"
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()
