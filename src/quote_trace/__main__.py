from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .documents import is_known_document_set
from .llm_extractor import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    LLMExtractionError,
    build_llm_quotation,
)
from .pipeline import build_quotation


def _load_environment() -> None:
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a traceable quotation with deterministic costing.")
    parser.add_argument("--input", type=Path, required=True, help="Directory containing the source documents")
    parser.add_argument("--output", type=Path, required=True, help="Destination JSON file")
    parser.add_argument(
        "--extractor",
        choices=("auto", "deterministic", "llm"),
        default="auto",
        help="auto uses deterministic adapters for the exercise files and LLM extraction otherwise",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OpenAI model used only by the LLM extractor (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "maximum time to wait for background LLM extraction "
            f"(default: {DEFAULT_TIMEOUT_SECONDS})"
        ),
    )
    return parser


def main() -> int:
    _load_environment()
    args = _parser().parse_args()
    try:
        use_llm = args.extractor == "llm" or (args.extractor == "auto" and not is_known_document_set(args.input))
        result = (
            build_llm_quotation(
                args.input,
                model=args.model,
                timeout_seconds=args.timeout_seconds,
            )
            if use_llm
            else build_quotation(args.input)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (FileNotFoundError, LLMExtractionError, ValueError, OSError) as exc:
        print(f"quote-trace: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(result['cost_lines'])} cost lines to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
