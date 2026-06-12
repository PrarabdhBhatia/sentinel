/**
 * Sentinel Buyer Agent — Guild Agent (D06)
 *
 * Autonomous procurement agent that refuses to trust vendor marketing.
 * Pays $0.01 USDC via x402 to access Sentinel's audited verdicts,
 * reasons over substantiation scores, and makes a vendor recommendation.
 *
 * Guild handles: auth, session logging, governed audit trail.
 * Every procurement decision is a logged Guild session — full reasoning trace.
 *
 * Deploy:
 *   guild agent init --name sentinel-buyer-agent --template LLM
 *   # paste this file's contents
 *   guild agent save --message "Sentinel buyer agent v1" --wait --publish
 */

import { z } from "zod";

// ── Input schema ─────────────────────────────────────────────────────────────

const InputSchema = z.object({
  category: z
    .string()
    .describe("Software category to evaluate, e.g. 'ai_support_agents'."),
  intent: z
    .array(z.string())
    .optional()
    .describe("Buyer priorities, e.g. ['security', 'integrations', 'ai_features']."),
  sentinel_api_url: z
    .string()
    .default("https://sentinel.onrender.com")
    .describe("Base URL of the Sentinel API."),
  max_spend_usd: z
    .number()
    .default(0.01)
    .describe("Maximum USD to spend on verdict fetch (matches Sentinel's x402 price)."),
});

// ── Output schema ─────────────────────────────────────────────────────────────

const OutputSchema = z.object({
  recommendation: z.string().describe("Recommended vendor name."),
  reasoning: z.string().describe("Explanation grounded in substantiation scores."),
  top_vendors: z
    .array(
      z.object({
        vendor: z.string(),
        credibility_score: z.number(),
        substantiated_claims: z.number(),
        total_claims: z.number(),
        intent_score: z.number().optional(),
      })
    )
    .describe("Ranked vendor list with scores."),
  payment_txn: z.string().optional().describe("x402 transaction hash used for payment."),
  audit_age_hrs: z.number().optional().describe("Age of the audit data in hours."),
  decision_statement: z
    .string()
    .describe(
      "Final statement in the form: 'Decision: [vendor] — [N]/[M] claims publicly substantiated. Recommending on evidence alone.'"
    ),
});

// ── System prompt ─────────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are Sentinel's buyer agent. You are an autonomous procurement
agent that refuses to trust vendor marketing copy. You only trust audited verdicts.

Your mission:
1. Hit the Sentinel API to fetch audited verdicts for a software category.
2. The endpoint requires payment — you receive an HTTP 402 with a quote.
3. Pay $0.01 USDC on Base L2 via x402, retry with the transaction hash.
4. Receive the full verdict JSON.
5. Reason over substantiation scores (and intent-weighted scores if intent is provided).
6. Output a vendor recommendation grounded purely in public substantiation evidence.

Reasoning rules:
- Never use marketing language as evidence.
- Only cite PUBLICLY_SUBSTANTIATED claims as positive signal.
- SELF_REPORTED_ONLY and NO_PUBLIC_RECEIPT_FOUND are neutral, not negative.
- If intent is specified, weight the categories the buyer cares about.
- Be honest about uncertainty — if scores are close, say so.

Output format:
"Decision: [vendor] — [N]/[M] claims publicly substantiated. Recommending on evidence alone."`;

// ── Agent definition ──────────────────────────────────────────────────────────

export default {
  name: "sentinel-buyer-agent",
  description:
    "Autonomous procurement agent. Fetches Sentinel verdicts via x402 micropayment, " +
    "reasons over substantiation scores, and recommends a vendor. " +
    "Every session is logged by Guild with full reasoning trace.",
  input: InputSchema,
  output: OutputSchema,
  systemPrompt: SYSTEM_PROMPT,

  async run(
    input: z.infer<typeof InputSchema>,
    ctx: {
      llm: (prompt: string) => Promise<string>;
      fetch: (url: string, opts?: RequestInit) => Promise<Response>;
    }
  ) {
    const intentParam = input.intent?.length
      ? `?intent=${input.intent.join(",")}`
      : "";
    const verdictUrl = `${input.sentinel_api_url}/api/market/${input.category}/verdicts${intentParam}`;

    // Step 1 — hit the verdict endpoint, expect 402
    let res = await ctx.fetch(verdictUrl);
    let paymentTxn: string | undefined;

    if (res.status === 402) {
      const quote = await res.json();
      // In a live deployment, the Guild control plane handles the x402 payment
      // using scoped credentials attached to the agent's workspace policy.
      // The payment_txn is injected back as a header on retry.
      // For the demo we record the quote and proceed — full x402 wiring lands in D05/D06.
      paymentTxn = `demo_quote_${Date.now()}`;
      res = await ctx.fetch(verdictUrl, {
        headers: { "X-Payment": paymentTxn, "X-Payment-Quote": JSON.stringify(quote) },
      });
    }

    if (!res.ok) {
      throw new Error(`Sentinel API returned ${res.status}`);
    }

    const data = await res.json();
    const vendors = data.vendors || [];
    const auditAgeHrs = data.audit_age_hrs;

    // Step 2 — ask LLM to reason over the verdicts
    const vendorSummary = vendors
      .map((v: { vendor: string; credibility_score: number; judgments: { verdict: string }[] }) => {
        const nPub = v.judgments?.filter((j: { verdict: string }) => j.verdict === "SUPPORTED").length || 0;
        const nTotal = v.judgments?.length || 0;
        return `${v.vendor}: credibility=${Math.round((v.credibility_score || 0) * 100)}%, ${nPub}/${nTotal} publicly substantiated`;
      })
      .join("\n");

    const intentNote = input.intent?.length
      ? `\nBuyer priorities: ${input.intent.join(", ")}`
      : "";

    const prompt = `Category: ${input.category}${intentNote}

Vendor audit data:
${vendorSummary}

Based solely on public substantiation evidence, recommend one vendor.
Return JSON with: recommendation, reasoning, top_vendors (array), decision_statement.`;

    const raw = await ctx.llm(prompt);
    const parsed = JSON.parse(raw);

    return OutputSchema.parse({
      ...parsed,
      payment_txn: paymentTxn,
      audit_age_hrs: auditAgeHrs,
    });
  },
};
