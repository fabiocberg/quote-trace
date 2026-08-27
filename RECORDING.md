# 3–5 minute recording guide

1. **Problem and safety principle (30 seconds)**  
   Explain that the objective is not merely to produce a number; it is to expose what the system does not know.

2. **Run the system (30 seconds)**  
   Run the test suite and CLI from the README. Show that 31 operational services are emitted and the JSON validates.

3. **Trace a confirmed value (45 seconds)**  
   Open `camissa_family`. Show the operational quantity, USD 375 email rate, superseded USD 340 pack reference, formula, and USD 1,500 total.

4. **Show deterministic unit handling (30 seconds)**  
   Compare Camissa's per-room calculation with Kudu's five-people-by-three-nights calculation and the zero-cost triple arrangement.

5. **Show uncertainty handling (60–90 seconds)**  
   Walk through the overlapping Marula season candidates, mismatched Marula-to-Kudu route, expired helicopter tariff, missing Beach Villa Grande, and live-priced flights.

6. **Totals and review gate (30 seconds)**  
   Show the partitioned subtotals and `client_ready_total: null`, then point to the concrete actions in `needs_review`.

7. **Generic-document path (30–45 seconds)**  
   Show `--extractor auto`, `deterministic`, and `llm`. Explain that unfamiliar text-based documents use structured LLM extraction, while cited evidence is checked locally and all arithmetic remains deterministic. Mention that this path requires `OPENAI_API_KEY`, always requires human review, and deliberately rejects scanned PDFs until OCR is added.
