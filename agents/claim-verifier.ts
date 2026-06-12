/**
 * Sentinel Claim Verifier — Guild Agent (D06)
 *
 * Judges a single atomic marketing claim against public evidence snippets
 * and returns a structured verdict. Invoked once per claim during every audit.
 *
 * Guild handles: auth, credential scoping, session logging, audit trail.
 * No API keys in this file — the control plane injects them.
 *
 * Deploy:
 *   guild agent init --name sentinel-claim-verifier --template LLM
 *   # paste this file's contents into the scaffolded agent.ts
 *   guild agent save --message "Sentinel claim verifier v1" --wait --publish
 */

import { z } from "zod";

// ── Input schema ─────────────────────────────────────────────────────────────

const InputSchema = z.object({
  claim: z.string().describe("The atomic marketing claim to verify."),
  evidence_snippets: z
    .array(z.string())
    .describe("Public web snippets retrieved by Tavily for this claim."),
  evidence_urls: z
    .array(z.string())
    .describe("Source URLs for the evidence snippets."),
  vendor: z.string().describe("Vendor name (for logging)."),
  confidence_threshold: z
    .number()
    .min(0)
    .max(1)
    .default(0.7)
    .describe("If confidence < threshold the result is flagged for escalation."),
});

// ── Output schema ─────────────────────────────────────────────────────────────

const OutputSchema = z.object({
  verdict: z
    .enum(["PUBLICLY_SUBSTANTIATED", "SELF_REPORTED_ONLY", "NO_PUBLIC_RECEIPT_FOUND"])
    .describe("Sentinel verdict — measures public substantiation, never truth."),
  confidence: z
    .number()
    .min(0)
    .max(1)
    .describe("Confidence in the verdict (0.0–1.0)."),
  rationale: z
    .string()
    .describe("One-sentence explanation grounded in the evidence."),
  receipts: z
    .array(z.string())
    .describe("URLs from evidence that support the verdict."),
  escalate: z
    .boolean()
    .describe("True when confidence < threshold — caller should escalate to premium tier."),
});

// ── System prompt ─────────────────────────────────────────────────────────────

const SYSTEM_PROMPT = `You are Sentinel's claim verifier. Your job is to judge a single
marketing claim against public evidence retrieved from the web.

VERDICT RULES — use exactly one:
- PUBLICLY_SUBSTANTIATED: independent public sources (case studies, third-party reviews,
  published methodology, press coverage) directly corroborate this specific claim.
- SELF_REPORTED_ONLY: the claim appears only on the vendor's own surfaces — their site,
  blog, or press releases — and you see no independent corroboration.
- NO_PUBLIC_RECEIPT_FOUND: you found no public evidence for or against this claim.
  This is NOT the same as "false" — absence of receipt is a valid, neutral verdict.

BANNED WORDS — never use: Verified, Unverified, Unsupported, False, True.
These imply truth judgments. Sentinel measures public substantiation only.

CONFIDENCE:
- High (0.8–1.0): multiple independent sources clearly confirm/contradict
- Medium (0.5–0.79): some evidence but ambiguous or limited
- Low (0.0–0.49): sparse evidence; uncertain judgment

Respond with valid JSON matching the output schema. Nothing else.`;

// ── Agent definition ──────────────────────────────────────────────────────────

export default {
  name: "sentinel-claim-verifier",
  description:
    "Judges a single atomic marketing claim against public web evidence. " +
    "Returns PUBLICLY_SUBSTANTIATED / SELF_REPORTED_ONLY / NO_PUBLIC_RECEIPT_FOUND " +
    "with confidence score. Every judgment is a logged Guild session.",
  input: InputSchema,
  output: OutputSchema,
  systemPrompt: SYSTEM_PROMPT,

  async run(input: z.infer<typeof InputSchema>, ctx: { llm: (prompt: string) => Promise<string> }) {
    const evidenceBlock =
      input.evidence_snippets.length > 0
        ? input.evidence_snippets
            .map((s, i) => `[${i + 1}] ${s}\nSource: ${input.evidence_urls[i] || "unknown"}`)
            .join("\n\n")
        : "No public evidence found for this claim.";

    const prompt = `Vendor: ${input.vendor}

Claim: "${input.claim}"

Public evidence retrieved:
${evidenceBlock}

Return a JSON object with: verdict, confidence, rationale, receipts (array of URLs), escalate (boolean).`;

    const raw = await ctx.llm(prompt);

    // Parse and validate
    const parsed = JSON.parse(raw);
    const result = OutputSchema.parse({
      ...parsed,
      escalate: parsed.confidence < input.confidence_threshold,
    });

    return result;
  },
};
