# Sponsor & Tool Use — what we use and how

How each sponsor tool is wired into Sentinel, where it lives in the code, and its
current status. Judging weights Tool Use 20 / Autonomy 20 — every tool here is
load-bearing (remove it and a demo beat breaks), not decorative.

Status legend: ✅ wired & working · 🟡 key in `.env`, integration partial/pending · ⬜ not started

## Use checklist

- [x] **Pioneer** — cheap-tier/adaptive inference seam exists; key present, final base URL/model still needed.
- [ ] **TrueFoundry** — planned gateway routing; not used until gateway env vars are set.
- [x] **Senso / cited.md** — onboarding/CLI installed and publish seam exists; final publish call pending.
- [x] **ClickHouse** — Cloud connected; live sink writing, backfill script + demo queries shipped (`backend/scripts/`).
- [~] **Airbyte Cloud** — destination = same ClickHouse Cloud; configuration tested as far as permissions allow, source sync still optional.
- [x] **Composio** — notification seam exists for claim-change alerts; action selection/auth pending.
- [x] **Thesys C1 / OpenUI** — Interrogate panel built; uses C1 when model env is set, premium fallback otherwise.
- [x] **x402** — verdict endpoint exists; demo mode returns paid JSON and emits `paid_fetch`, real wallet verification still pending.
- [x] **Guild.ai** — buyer agent created/published and used to reason over Sentinel verdict data; not embedded in backend/frontend.
- [ ] **Render** — not deployed yet.

| Sponsor | What it gives us | How Sentinel uses it | Status |
|---|---|---|---|
| **Pioneer** | Adaptive, OpenAI-compatible inference that improves from live traffic | Cheap tier of the judge cascade; every escalation logged back as corrective feedback | 🟡 API key in `.env`; `PIONEER_BASE_URL` + `PIONEER_MODEL` still needed from rep |
| **TrueFoundry** | AI Gateway — route/govern/observe all LLM traffic | Both cascade tiers (cheap + premium) routed through one gateway base URL | ⬜ no key yet |
| **Senso / cited.md** | Publish structured context that agents can cite | Auto-publish each completed market audit as a citeable doc | 🟡 key in `.env`; CLI + onboarding skill installed; publish path pending |
| **ClickHouse** | Fast analytical warehouse | Telemetry sink alongside JSONL; live demo queries (escalation rate, cost/market) | ✅ connected (Cloud, eastus2); sink live, table auto-created, backfill + demo queries shipped |
| **Composio** | Agent action / tool execution | Post claim-change alert (Slack / GitHub issue) when the sentinel loop fires | 🟡 key in `.env`; `notify.py` pending wire-up |
| **Thesys C1 / OpenUI** | Generative UI from a question + data | "Interrogate the market" panel — question in, glass-rendered charts/tables out | ✅ built today; runs on premium fallback until `THESYS_C1_MODEL` is set |
| **Airbyte Cloud** | Managed data movement into the warehouse | External context can sync into the same ClickHouse Cloud database as Sentinel telemetry | 🟡 destination configured against ClickHouse; source sync optional for demo |
| **x402** | Pay-per-fetch HTTP 402 rail | Verdict endpoint returns a quote when wallet is set; demo mode returns paid JSON and emits `paid_fetch` | 🟡 endpoint wired; real wallet/settlement pending |
| **Guild.ai** | Buyer-agent runtime / "Most Innovative Use of Agents" prize | Published procurement agent reasons over Sentinel verdict data and recommends a vendor | ✅ published v1.0.3; external CLI demo works, not embedded in app runtime |
| **Render** | Deploy platform | Host the backend + the live-editable test vendor page | ⬜ pending |

---

## Detail by tool

### Pioneer — adaptive cheap-tier inference
- **Role:** the technical heart. The judge cascade's cheap tier calls Pioneer's
  OpenAI-compatible endpoint; when the cheap judge is uncertain we escalate to the
  premium model and POST the disagreement pair back as labeled feedback, so the
  cheap judge improves with traffic.
- **Code:** [backend/app/clients.py](backend/app/clients.py) (cheap-tier client +
  cascade), `record_feedback()` on escalation (D02).
- **Config:** `PIONEER_API_KEY` (set), `PIONEER_BASE_URL`, `PIONEER_MODEL`,
  `PIONEER_FEEDBACK_URL` in [.env](.env) / [.env.example](.env.example).
- **Demo beat:** "escalation rate falls across runs — the cheap judge is learning."

### TrueFoundry — AI Gateway
- **Role:** all LLM traffic (cheap + premium) flows through one gateway for
  observability + governance.
- **Code:** [backend/app/clients.py](backend/app/clients.py) — `_use_tf()` routes
  both tiers through the gateway when `TRUEFOUNDRY_*` + `TF_MODEL_*` are set; falls
  back to the direct stand-in pair otherwise.
- **Config:** `TRUEFOUNDRY_API_KEY`, `TRUEFOUNDRY_BASE_URL`, `TF_MODEL_CHEAP`,
  `TF_MODEL_PREMIUM`.

### Senso / cited.md — publish to the agentic web
- **Role:** every finished market audit compiles to a structured, citeable doc and
  is published so other agents can discover + cite it.
- **Code:** [backend/app/publish.py](backend/app/publish.py) (D04).
- **CLI:** `@senso-ai/cli` installed; onboarding skill at
  [.claude/skills/senso-onboarding/](.claude/skills/senso-onboarding/).
- **Config:** `SENSO_API_KEY` (set). Org: **SENTINEL** (free tier).
- **Note:** the `cited-md` shared destination is the hackathon publish target.

### ClickHouse — telemetry warehouse
- **Role:** analytical store for the JSONL telemetry (historical run files + live
  runs); powers live demo queries.
- **Code:** ClickHouse sink alongside the JSONL `TelemetryBus` (D08, fire-and-forget
  so it never blocks the pipeline).
- **Config:** `CLICKHOUSE_URL`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`,
  `CLICKHOUSE_DATABASE`.
- **Acceptance:** ClickHouse Cloud is connected, `telemetry` is auto-created, and
  demo query returned live rows grouped by `hunt`, `judge_cheap`, `extract`, and
  `ingest`.

### Airbyte Cloud — external context into ClickHouse
- **Role:** no-Docker path for syncing sponsor/external context into the same
  ClickHouse Cloud warehouse as Sentinel telemetry.
- **Code/docs:** [docs/airbyte-clickhouse-cloud.md](docs/airbyte-clickhouse-cloud.md)
  plus ClickHouse destination configured in Airbyte Cloud.
- **Status:** optional for the live demo. Sentinel does not depend on Airbyte; the
  clean story is "Airbyte brings external context beside Sentinel's telemetry."

### Composio — act on the web
- **Role:** when the sentinel loop detects a claim change, post the delta to Slack
  or a GitHub issue.
- **Code:** [backend/app/notify.py](backend/app/notify.py) (D09).
- **Config:** `COMPOSIO_API_KEY` (set).

### Thesys C1 / OpenUI — generative UI  ✅ built today
- **Role:** "Interrogate the market" — a free-text question over the current
  `MarketResult` returns a constrained widget spec (metric / bar / table /
  verdict_list) that we render with our own glass primitives, so generated content
  renders **inside** our design language and can't clash (§4 contract).
- **Code:** backend [backend/app/interrogate.py](backend/app/interrogate.py) +
  `POST /interrogate` in [backend/app/server.py](backend/app/server.py); frontend
  [frontend/src/components/InterrogatePanel.tsx](frontend/src/components/InterrogatePanel.tsx),
  mounted in [frontend/src/App.tsx](frontend/src/App.tsx).
- **Routing:** literal Thesys C1 (OpenAI-compatible) when `THESYS_C1_API_KEY` +
  `THESYS_C1_MODEL` are set; otherwise real premium `chat()` — never a mock.
- **Config:** `THESYS_C1_API_KEY`, `THESYS_C1_BASE_URL`, `THESYS_C1_MODEL`.

### x402 — pay-per-fetch
- **Role:** the verdict API returns HTTP 402 + a quote; a paying agent gets the
  verdict JSON. The "agents pay for trust data" moat + the buyer-agent money moment.
- **Code:** payments wrapper on `GET /api/market/{category}/verdicts` in
  [backend/app/server.py](backend/app/server.py), helpers in [backend/app/x402.py](backend/app/x402.py).
- **Config:** `X402_PAY_TO`, `X402_PRICE_USD`.
- **Status:** demo mode works when `X402_PAY_TO` is blank: a verdict fetch returns
  paid JSON and emits `paid_fetch` so the dashboard "Agents paid" counter ticks.
  Real wallet/settlement verification remains pending.

### Guild.ai — buyer agent
- **Role:** the procurement agent side of the marketplace. Sentinel provides paid
  verdict data; the Guild agent reasons over substantiation and chooses a vendor.
- **Code:** [sentinel-buyer-agent/sentinel-buyer-agent/agent.ts](sentinel-buyer-agent/sentinel-buyer-agent/agent.ts).
- **Status:** published as `emanuel~sentinel-buyer-agent` v1.0.3. CLI demo works
  by passing Sentinel verdict JSON/summary into the Guild agent; latest run
  recommended Zendesk AI after comparing SUPPORTED ratios and tie-breakers.
- **Caveat:** not embedded inside Sentinel backend/frontend yet; the integration is
  an external Guild buyer-agent demo path.

### Render — deploy
- **Role:** host the backend + the live-editable test vendor page so the loop can be
  triggered on stage.
- **Config:** deploy-time, no env key in repo.
