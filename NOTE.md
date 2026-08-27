# Submission note

I built a small Python CLI that reads the three supplied documents and emits a deterministic, provenance-first JSON quotation. Python was the fastest honest choice for a two-hour document exercise: PDF extraction is mature, `Decimal` makes monetary behaviour explicit, and the resulting boundary can still feed a TypeScript application as validated JSON.

The default path recognizes these documents, validates their identity, extracts commercial rates, and preserves page/section/excerpt references. The costing layer is deterministic: every priced line records factors, unit rate, formula, confidence, and source. Supplier correspondence explicitly supersedes the Camissa rate-pack values.

For unfamiliar text-based PDFs and text files, the CLI has a real LLM extraction path using OpenAI Structured Outputs. The model may propose services, quantities and rate associations, but cannot provide totals. QuoteTrace validates cited excerpts against local pages and performs all arithmetic with `Decimal`. Because semantic pairing is probabilistic, LLM-derived prices are never automatically confirmed and always enter the review queue.

The output does not claim a final total. It partitions confirmed, conditional, and indicative amounts and excludes unresolved lines. In particular, I did not guess the Marula season on an overlapping boundary date, map Beach Villa Grande to Infinity Beach Villa, reuse a Cape Town meet-and-greet rate in Johannesburg, price a mismatched transfer route, or treat carried-forward 2026 helicopter rates as current. Flights remain unpriced because the pack explicitly requires live pricing.

With more time, I would add OCR, layout fixtures, property-based tests for unit conversions and date boundaries, and a review workflow that records the human decision resolving each issue.

I used AI assistance to inspect documents, challenge assumptions, scaffold code, and identify edge cases. I overrode permissive regex matches that selected neighbouring rates; golden tests protect those failures. The implemented LLM boundary deliberately excludes arithmetic, subtotal reconciliation, automatic confirmation, and the decision that a quote is safe to send.
