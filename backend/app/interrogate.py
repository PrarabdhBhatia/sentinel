"""D10 — "Interrogate the market" (Thesys C1 / OpenUI).

Question in → generative UI out, grounded in a real MarketResult. This is the
constitution-safe shape of the C1 panel (§4): the model is constrained to emit
a small WIDGET JSON which the React side renders with OUR glass primitives, so
generated content renders *inside* our design language and can never define it.

Routing (decided per-call):
  THESYS_C1_API_KEY + THESYS_C1_MODEL set
    → literal Thesys C1 via its OpenAI-compatible endpoint (prize-eligible).
  either blank
    → fall back to the premium chat() tier (Claude via TF or direct Anthropic).
      Still REAL inference — no mock, no canned answer — so the panel works on
      stage today and upgrades to C1 the moment the booth hands over the model id.

No defamation surface: the system prompt carries the same substantiation-not-truth
discipline as the rest of the pipeline, and the only verdict vocabulary allowed is
the three-value enum.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from openai import AsyncOpenAI

from app import clients
from app.config import settings
from app.schemas import MarketResult, Verdict


# Verdict → the exact UI label. Mirrors VERDICT_META in App.tsx; banned words
# ("verified", "unsupported", …) never appear.
VERDICT_LABEL = {
    Verdict.SUPPORTED.value: "Publicly substantiated",
    Verdict.SELF_REPORTED_ONLY.value: "Self-reported only",
    Verdict.NO_PUBLIC_RECEIPT_FOUND.value: "No public receipt",
}


_SYSTEM = """You are the analyst behind Sentinel's "Interrogate the market" panel.
You are given a market audit as JSON and a question. Answer ONLY from the audit
data — never invent vendors, scores, or claims that are not present.

DISCIPLINE: Sentinel measures PUBLIC SUBSTANTIATION, never truth. Never say a
claim is "false", "fake", "verified", or "unverified". The only verdict words you
may use are exactly: "Publicly substantiated", "Self-reported only",
"No public receipt".

Respond with a SINGLE JSON object, no prose outside it, of the form:
{
  "answer": "<one or two sentence plain-language answer>",
  "widgets": [ <zero or more widgets, in display order> ]
}

Widget types (use whichever best answer the question; omit the rest):
- {"type":"metric","label":str,"value":str,"tone":"good"|"warn"|"bad"|"neutral"}
- {"type":"bar","title":str,"rows":[{"label":str,"value":number,"display":str,"tone":...}]}
    value is 0..100 for the bar fill; display is the human label (e.g. "3.4x").
- {"type":"table","columns":[str,...],"rows":[[str,...],...]}
- {"type":"verdict_list","title":str,"items":[{"vendor":str,"claim":str,"verdict":"Publicly substantiated"|"Self-reported only"|"No public receipt"}]}

Keep it tight: at most 3 widgets, at most 6 rows each. Prefer a bar or table for
comparisons, a verdict_list when the question is about specific claims. tone maps
to color: good=emerald, warn=amber, bad=red, neutral=grey."""


def compile_context(market: MarketResult) -> str:
    """Compact, token-lean grounding doc. One line of structure per vendor plus
    its claim/verdict pairs, so the model can answer comparative questions
    without us shipping the whole verbose MarketResult."""
    vendors: list[dict[str, Any]] = []
    for v in market.vendors:
        judge_by_claim = {j.claim_id: j for j in v.judgments}
        claims = []
        for c in v.claims:
            j = judge_by_claim.get(c.claim_id)
            claims.append(
                {
                    "claim": c.claim,
                    "verdict": VERDICT_LABEL.get(j.verdict.value, "No public receipt")
                    if j
                    else "No public receipt",
                }
            )
        supported = sum(
            1 for j in v.judgments if j.verdict == Verdict.SUPPORTED
        )
        vendors.append(
            {
                "vendor": v.vendor,
                "score_pct": round(v.credibility_score * 100)
                if v.credibility_score is not None
                else None,
                "claims_total": len(v.claims),
                "claims_substantiated": supported,
                "claims": claims,
            }
        )
    doc = {
        "category": market.category,
        "claim_inflation_index": round(market.claim_inflation_index, 2),
        "vendors": vendors,
    }
    return json.dumps(doc, ensure_ascii=False)


_c1_client: Optional[AsyncOpenAI] = None


def _use_c1() -> bool:
    return bool(settings.THESYS_C1_API_KEY and settings.THESYS_C1_MODEL)


def c1_client() -> AsyncOpenAI:
    global _c1_client
    if _c1_client is None or _c1_client.base_url != settings.THESYS_C1_BASE_URL:
        _c1_client = AsyncOpenAI(
            base_url=settings.THESYS_C1_BASE_URL,
            api_key=settings.THESYS_C1_API_KEY,
            max_retries=0,
        )
    return _c1_client


def _coerce(payload: Any) -> dict[str, Any]:
    """Normalise the model output into {answer, widgets} regardless of how the
    model phrased it. A parse miss degrades to an answer-only card rather than
    throwing — the panel should never 500 on stage."""
    if not isinstance(payload, dict):
        return {"answer": str(payload), "widgets": []}
    answer = str(payload.get("answer", "")).strip()
    widgets = payload.get("widgets")
    if not isinstance(widgets, list):
        widgets = []
    return {"answer": answer, "widgets": widgets}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Strip a ```json fence if the model wrapped its reply.
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.removeprefix("json").strip().strip("`").strip()
    try:
        return _coerce(json.loads(text))
    except json.JSONDecodeError:
        # Last resort: grab the outermost {...} span.
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return _coerce(json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                pass
    return {"answer": text or "No answer produced.", "widgets": []}


async def interrogate(question: str, market: MarketResult) -> dict[str, Any]:
    """Answer a free-text question over a MarketResult, returning a widget spec.
    Returns {"answer": str, "widgets": [...], "engine": "c1"|"premium"}."""
    context = compile_context(market)
    user = f"AUDIT DATA:\n{context}\n\nQUESTION: {question.strip()}"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]

    if _use_c1():
        resp = await c1_client().chat.completions.create(
            model=settings.THESYS_C1_MODEL,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=1200,
            temperature=0.2,
        )
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        out = _extract_json(text)
        out["engine"] = "c1"
        return out

    # Fallback: premium chat() tier. Real inference, same prompt.
    result = await clients.chat("premium", messages, max_tokens=1200, temperature=0.2)
    out = _extract_json(result.text)
    out["engine"] = "premium"
    return out
