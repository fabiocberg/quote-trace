# QuoteTrace

QuoteTrace is a Python CLI that turns operational and commercial travel documents into a structured, traceable quotation with deterministic costing.

The project was built for Aterra's Lead AI Engineer technical exercise. It prioritizes financial correctness and auditability: every calculated amount records its quantity, rate, formula, confidence level, and source-document evidence.

## About the project

Travel documents commonly combine bookings, supplier rates, commercial exceptions, email corrections, and incomplete information. Producing a single total would hide those uncertainties and could make an incorrect association look financially authoritative.

QuoteTrace separates the workflow into explicit responsibilities:

```text
Documents
    ↓
Extraction and normalization
    ↓
Evidence and commercial-rule validation
    ↓
Deterministic calculations with Decimal
    ↓
Traceable JSON + review items
```

### Extraction strategy

The application provides two execution paths:

- **Deterministic adapter:** handles the documents supplied with the exercise. It validates file identity and applies known, explicit rules without calling an external API.
- **LLM-assisted extraction:** handles unfamiliar text-based documents. The model proposes services, quantities, factors, and rate associations through a strict schema.

When `--extractor llm` is forced for the known exercise documents, the LLM is genuinely called, but its output remains an audited proposal. Final pricing still comes from the reviewed deterministic adapter. This prevents a plausible model response from silently overriding rules such as per-vehicle units, overlapping seasons, route direction, or email precedence.

The LLM is used only for semantic ambiguity. It never calculates line amounts, subtotals, or totals, and it never decides whether a quotation is ready for a client. In the generic path, QuoteTrace still:

- verifies that model-cited excerpts exist in the local documents;
- tolerates presentation-only differences in citations, such as punctuation, letter case, whitespace, and decimal trailing zeros, while preserving the literal local excerpt in the output;
- validates dates, currencies, quantities, and decimal strings;
- calculates every amount locally with `Decimal`;
- limits LLM-extracted lines to `conditional` confidence at best;
- stops processing when evidence cannot be verified.

This boundary is deliberate: arithmetic can be correct while the commercial result is wrong because the model extracted the wrong rate or quantity.

### Confidence policy

Every cost line receives one explicit classification:

- `confirmed`: current rate, unambiguous match, and complete formula;
- `conditional`: calculable amount that still requires operational or human validation;
- `indicative`: known amount whose rate is not valid for the applicable date;
- `unresolved`: insufficient reliable information to calculate an amount.

Subtotals are separated by confidence. Unresolved lines are excluded from monetary sums, and `client_ready_total` remains `null` while commercial decisions are pending. The system prefers refusing to calculate over inventing certainty.

### Technical decisions

- Python 3.11 or later with a small dependency surface.
- Monetary values represented with `Decimal`, never `float`.
- Explicit financial rounding to two decimal places.
- Monetary values serialized as decimal strings in JSON.
- One output line for every operational service, including complimentary and unresolved items.
- Quantity and rate provenance preserved by document, page, section, and excerpt.
- Precedence, validity, and billing-unit rules kept outside the LLM.
- Explicit failure for empty documents, fabricated evidence, and unsupported formats.

## Running the project

### Requirements

- Python 3.11 or later;
- an OpenAI API key only for unfamiliar documents or when LLM extraction is explicitly forced.

### Installation

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### Configuring the OpenAI API key

Copy the example environment file in the project root:

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder value:

```dotenv
OPENAI_API_KEY=sk-your-key-here
```

QuoteTrace loads this file automatically at startup. There is no need to run `export` or pass the key with each command. `.env` is ignored by Git and must not be committed, shared, or included in the submission archive.

An `OPENAI_API_KEY` already defined in the process environment takes precedence over the `.env` value. The supplied exercise documents continue to work when neither is configured.

### Running with the exercise documents

This path is fully local and does not require an API key:

```bash
python -m quote_trace \
  --input ../docs \
  --output output/costed-quotation.json
```

The generated reference result is available at [`output/costed-quotation.json`](output/costed-quotation.json).

### Running with other documents

The default mode is `auto`: it selects the deterministic adapter for the recognized exercise set and falls back to the LLM extractor for other supported document sets.

```bash
python -m quote_trace \
  --input path/to/documents \
  --output output/other-quotation.json
```

Supported formats are text-layer PDFs, TXT, MD, EML, and CSV. Scanned PDFs fail explicitly because OCR is outside this version's scope.

> LLM mode sends the documents' textual content to the OpenAI API. Enable it only when applicable privacy and data-processing policies permit that transfer.

### Selecting an extraction mode

```bash
# Automatic selection — the default behavior
python -m quote_trace --input ../docs --output output/result.json --extractor auto

# Prevent any LLM call
python -m quote_trace --input ../docs --output output/result.json --extractor deterministic

# Force LLM-assisted extraction
python -m quote_trace --input path/to/documents --output output/result.json --extractor llm

# Select a different extraction model
python -m quote_trace --input path/to/documents --output output/result.json --model gpt-5-mini

# Increase the overall limit for an exceptionally slow extraction
python -m quote_trace --input path/to/documents --output output/result.json --extractor llm --timeout-seconds 900
```

The default model is `gpt-5-mini`. LLM extraction starts as a background response and is polled until completion, with a default overall limit of 600 seconds. This avoids holding one HTTP connection open throughout generation. The program does not automatically create a second response after a network failure because doing so could duplicate processing and charges.

When `--extractor llm` is forced for the original exercise directory, only the operational quotation, rate pack, and supplier email are sent. Briefs and transcripts provide development context rather than commercial evidence, so they are excluded. In this case, `extraction.mode` is `llm_assisted_deterministic`: the candidate line count is recorded under `extraction.audit`, but LLM-proposed rates, factors, and totals never enter the authoritative quotation. If the proposal cites nonexistent evidence or fails local validation, its audit status becomes `rejected` without preventing the known adapter from producing the deterministic quotation.

### Running the tests

```bash
python -m pytest
```

Run the complete acceptance sequence with:

```bash
python -m pytest
python -m quote_trace --input ../docs --output output/costed-quotation.json
python -m json.tool output/costed-quotation.json >/dev/null
```

The test suite covers supplier-email precedence, billing-unit semantics, complimentary services, overlapping seasons, expired rates, route mismatches, missing prices, provenance, and exact subtotal reconciliation. The LLM boundary is tested through a simulated HTTP client and consumes no external API calls.

### Interpreting the output

The JSON has four primary areas:

- `cost_lines`: services, quantities, rates, formulas, amounts, and provenance;
- `totals`: confidence-partitioned subtotals and the final-total gate;
- `needs_review`: detected issues, their impact, and required human action;
- `extraction`: extractor metadata, present on the LLM path.

`known_amounts_total_not_client_ready` exists only for internal reconciliation. It is not an approved client total.

In the generic schema (`1.2`), the top-level `currency` contains the single currency used by priced lines. An unpriced line without a currency increments `totals.unresolved_without_currency`; it neither creates a fictional `UNKNOWN` currency nor forces `currency` to `null`. A `null` value remains correct when no line has a price or when the quotation contains more than one real currency.

## Project structure

```text
quote-trace/
├── src/quote_trace/
│   ├── __main__.py          # CLI arguments and extractor selection
│   ├── documents.py         # Known-set reading and validation
│   ├── llm_extractor.py     # Generic extraction, schema, and evidence validation
│   ├── models.py            # Domain models, confidence, and money utilities
│   └── pipeline.py          # Commercial rules and quotation assembly
├── tests/
│   ├── fixtures/
│   │   └── golden-summary.json
│   └── test_pipeline.py     # Deterministic pipeline and LLM-boundary tests
├── output/
│   └── costed-quotation.json
├── .env.example             # Safe API configuration template
├── NOTE.md                  # Technical submission note
├── RECORDING.md             # Suggested presentation script
└── pyproject.toml           # Package, dependencies, and test configuration
```

### Module responsibilities

`documents.py` understands only the format supplied with the exercise. It ensures that expected files exist, extracts PDF text, and validates minimum identity markers before any commercial rule executes.

`llm_extractor.py` is the probabilistic boundary. It reads supported textual formats, requests schema-constrained output from the API, verifies returned evidence, and converts the proposal into lines that always require review. For the known document set, it delegates final pricing to the deterministic adapter and records the proposal only as audit data. Its request function is injectable so tests do not require network access.

`models.py` owns domain contracts and monetary policy. `pipeline.py` owns the exercise-specific deterministic rules, including rate precedence, billing units, validity, and confidence classification.

`__main__.py` keeps the interface thin: it parses arguments, selects the extractor, writes JSON only after successful processing, and returns readable errors when input cannot be handled safely.

### Known limitations

This version is not a universal document parser. It does not provide OCR, image processing, spreadsheet ingestion, or booking-system integration. Very large documents would also require chunking and cross-chunk reconciliation before being sent to a model.

A production evolution should add coordinate-preserving OCR, versioned supplier schemas, cross-entity validation, observability without sensitive-data exposure, and an auditable workflow for approving conditional lines.
