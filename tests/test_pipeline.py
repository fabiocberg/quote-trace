from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from quote_trace import build_llm_quotation, build_quotation
from quote_trace import llm_extractor
from quote_trace.__main__ import _load_environment
from quote_trace.documents import is_known_document_set
from quote_trace.llm_extractor import LLMExtractionError, _read_documents
from quote_trace.models import money


DOCS = Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture(scope="module")
def quotation() -> dict:
    return build_quotation(DOCS)


@pytest.fixture(scope="module")
def lines(quotation: dict) -> dict[str, dict]:
    return {line["service"]["id"]: line for line in quotation["cost_lines"]}


def test_supplier_email_supersedes_camissa_pack(lines: dict[str, dict]) -> None:
    family = lines["camissa_family"]
    classic = lines["camissa_classic"]
    assert (family["unit_rate"], family["line_total"]) == ("375.00", "1500.00")
    assert (classic["unit_rate"], classic["line_total"]) == ("230.00", "920.00")
    assert family["rate_provenance"][0]["document"].endswith("rates.txt")
    assert family["rate_provenance"][1]["document"].endswith("v3.pdf")


def test_money_is_decimal_and_rounds_half_up() -> None:
    assert isinstance(money("1.005"), Decimal)
    assert money("1.005") == Decimal("1.01")


def test_missing_document_set_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Missing input document"):
        build_quotation(tmp_path)


def test_per_unit_accommodation_is_not_multiplied_by_people(lines: dict[str, dict]) -> None:
    assert lines["camissa_family"]["pricing_quantity"] == "1 room × 4 nights"
    assert lines["ilha_beach"]["line_total"] == "2340.00"


def test_kudu_costs_all_five_people_for_three_nights(lines: dict[str, dict]) -> None:
    assert lines["kudu_suite"]["unit_rate"] == "890.00"
    assert lines["kudu_suite"]["pricing_quantity"] == "5 people × 3 nights"
    assert lines["kudu_suite"]["line_total"] == "13350.00"
    assert lines["kudu_triple"]["line_total"] == "0.00"


def test_complimentary_transfer_is_explicit_zero(lines: dict[str, dict]) -> None:
    assert lines["hds_marula"]["confidence"] == "confirmed"
    assert lines["hds_marula"]["unit_rate"] == "0.00"
    assert lines["hds_marula"]["line_total"] == "0.00"


def test_marula_overlap_is_not_silently_resolved(lines: dict[str, dict]) -> None:
    for service_id in ("marula_family", "marula_pool"):
        line = lines[service_id]
        assert line["confidence"] == "unresolved"
        assert line["line_total"] is None
        assert len(line["candidate_amounts"]) == 3


def test_expired_helicopter_rate_is_only_indicative(lines: dict[str, dict]) -> None:
    for service_id in ("heli_out", "heli_back"):
        assert lines[service_id]["confidence"] == "indicative"
        assert lines[service_id]["unit_rate"] == "395.00"


def test_missing_rates_remain_unresolved(lines: dict[str, dict]) -> None:
    ids = ("flight_cpt_hds", "flight_mqp_vnx", "flight_vnx_jnb", "ilha_grande", "jnb_meet_departure")
    assert all(lines[service_id]["line_total"] is None for service_id in ids)


def test_route_mismatch_does_not_receive_a_similar_rate(lines: dict[str, dict]) -> None:
    assert lines["marula_kudu"]["confidence"] == "unresolved"
    assert lines["marula_kudu"]["unit_rate"] is None
    assert lines["kudu_mqp"]["confidence"] == "conditional"
    assert lines["kudu_mqp"]["line_total"] == "950.00"


def test_totals_reconcile_and_are_not_client_ready(quotation: dict) -> None:
    totals = quotation["totals"]
    assert totals == {
        "confirmed_subtotal": "21380.00",
        "conditional_subtotal": "1285.00",
        "indicative_subtotal": "3950.00",
        "known_amounts_total_not_client_ready": "26615.00",
        "unresolved_lines": 8,
        "client_ready_total": None,
        "statement": "No final client-ready total exists until every needs_review item affecting price or applicability is resolved.",
    }


def test_every_line_has_quantity_source_and_priced_lines_have_rate_source(quotation: dict) -> None:
    for line in quotation["cost_lines"]:
        source = line["service"]["source"]
        assert source["document"] and source["page"] and source["excerpt"]
        if line["line_total"] is not None:
            assert line["formula"]
            assert line["rate_provenance"]


def test_service_coverage_matches_golden_summary(quotation: dict) -> None:
    actual = {
        "lines": [
            {
                "id": line["service"]["id"],
                "confidence": line["confidence"],
                "line_total": line["line_total"],
            }
            for line in quotation["cost_lines"]
        ],
        "totals": quotation["totals"],
    }
    golden = json.loads((Path(__file__).parent / "fixtures" / "golden-summary.json").read_text())
    assert actual == golden


def _llm_response(extraction: dict) -> dict:
    return {"output": [{"content": [{"type": "output_text", "text": json.dumps(extraction)}]}]}


def _generic_extraction(*, excerpt: str = "Private transfer Airport to Hotel", valid_to: str | None = None) -> dict:
    return {
        "quotation_reference": "TEST-1",
        "lines": [{
            "id": "airport_transfer",
            "date": "2027-07-05",
            "category": "road_transfer",
            "description": "Private airport transfer",
            "operational_quantity": "2 vehicles",
            "service_source": {"document": "booking.txt", "page": 1, "section": "Services", "excerpt": excerpt},
            "rate_amount": "125.50",
            "currency": "USD",
            "rate_unit": "per vehicle",
            "rate_source": {
                "document": "rates.txt",
                "page": 1,
                "section": "Transfers",
                "excerpt": "Airport to Hotel: USD 125.50 per vehicle",
            },
            "valid_from": "2027-01-01",
            "valid_to": valid_to or "2027-12-31",
            "factors": [{"value": "2", "label": "vehicles"}],
            "safe_to_calculate": True,
            "reason": "Exact route, unit and travel date match.",
            "review_action": "Verify the extracted pairing.",
        }],
    }


def _generic_docs(tmp_path: Path) -> None:
    (tmp_path / "booking.txt").write_text("Services\nPrivate transfer Airport to Hotel\nDate: 2027-07-05\n")
    (tmp_path / "rates.txt").write_text("Transfers\nAirport to Hotel: USD 125.50 per vehicle\n")


def test_known_document_set_does_not_need_llm() -> None:
    assert is_known_document_set(DOCS)


def test_forced_llm_uses_only_commercial_sources_from_challenge() -> None:
    assert list(_read_documents(DOCS)) == [
        "MRA-2027-0641-Halloran-operational-quotation.pdf",
        "Supplier-Rate-Pack-SA-2027-v3.pdf",
        "Supplier-email-Camissa-2027-rates.txt",
    ]


def test_unfamiliar_documents_require_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _generic_docs(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMExtractionError, match="OPENAI_API_KEY"):
        build_llm_quotation(tmp_path)


def test_dotenv_loads_api_key_from_current_project_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    _load_environment()

    assert os.environ["OPENAI_API_KEY"] == "from-dotenv"


def test_dotenv_does_not_override_existing_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "from-environment")

    _load_environment()

    assert os.environ["OPENAI_API_KEY"] == "from-environment"


def test_llm_extracts_but_decimal_calculates_locally(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    captured: dict = {}

    def fake_request(payload: dict, api_key: str) -> dict:
        captured.update(payload)
        assert api_key == "test-key"
        return _llm_response(_generic_extraction())

    result = build_llm_quotation(tmp_path, api_key="test-key", request_fn=fake_request)
    line = result["cost_lines"][0]
    line_schema = captured["text"]["format"]["schema"]["properties"]["lines"]["items"]["properties"]
    assert "line_total" not in line_schema
    assert captured["background"] is True
    assert line["line_total"] == "251.00"
    assert line["formula"] == "2 vehicles × USD 125.50 = USD 251.00"
    assert line["confidence"] == "conditional"
    assert result["currency"] == "USD"
    assert "UNKNOWN" not in result["totals"]["by_currency"]
    assert result["totals"]["by_currency"]["USD"]["conditional_subtotal"] == "251.00"
    assert result["totals"]["client_ready_total"] is None


def test_unresolved_line_without_currency_does_not_create_a_fake_currency(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    extraction = _generic_extraction()
    extraction["lines"][0].update({
        "rate_amount": None,
        "currency": None,
        "rate_unit": None,
        "rate_source": None,
        "valid_from": None,
        "valid_to": None,
        "factors": [],
        "safe_to_calculate": False,
        "reason": "No applicable rate was found.",
    })

    result = build_llm_quotation(
        tmp_path,
        api_key="test-key",
        request_fn=lambda _payload, _key: _llm_response(extraction),
    )

    assert result["currency"] is None
    assert result["totals"]["by_currency"] == {}
    assert result["totals"]["unresolved_lines"] == 1
    assert result["totals"]["unresolved_without_currency"] == 1


def test_unresolved_currency_does_not_hide_the_single_priced_currency(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    extraction = _generic_extraction()
    unresolved = dict(extraction["lines"][0])
    unresolved.update({
        "id": "unpriced_service",
        "rate_amount": None,
        "currency": None,
        "rate_unit": None,
        "rate_source": None,
        "valid_from": None,
        "valid_to": None,
        "factors": [],
        "safe_to_calculate": False,
        "reason": "No applicable rate was found.",
    })
    extraction["lines"].append(unresolved)

    result = build_llm_quotation(
        tmp_path,
        api_key="test-key",
        request_fn=lambda _payload, _key: _llm_response(extraction),
    )

    assert result["currency"] == "USD"
    assert list(result["totals"]["by_currency"]) == ["USD"]
    assert result["totals"]["unresolved_lines"] == 1
    assert result["totals"]["unresolved_without_currency"] == 1


def test_known_documents_use_llm_as_audited_candidate_not_as_costing_authority() -> None:
    authoritative = build_quotation(DOCS)
    priced_line = next(line for line in authoritative["cost_lines"] if line["unit_rate"] is not None)
    extraction = {
        "quotation_reference": authoritative["quotation_reference"],
        "lines": [{
            "id": "candidate_line",
            "date": priced_line["service"]["date"],
            "category": priced_line["service"]["category"],
            "description": priced_line["service"]["description"],
            "operational_quantity": priced_line["service"]["operational_quantity"],
            "service_source": priced_line["service"]["source"],
            "rate_amount": priced_line["unit_rate"],
            "currency": priced_line["currency"],
            "rate_unit": priced_line["rate_unit"],
            "rate_source": priced_line["rate_provenance"][0],
            "valid_from": None,
            "valid_to": None,
            "factors": [{"value": "1", "label": "candidate unit"}],
            "safe_to_calculate": True,
            "reason": "Candidate extraction for audit.",
            "review_action": "Compare with deterministic rules.",
        }],
    }

    result = build_llm_quotation(
        DOCS,
        api_key="test-key",
        request_fn=lambda _payload, _key: _llm_response(extraction),
    )

    assert result["currency"] == "USD"
    assert len(result["cost_lines"]) == 31
    assert result["totals"] == authoritative["totals"]
    assert result["extraction"]["mode"] == "llm_assisted_deterministic"
    assert result["extraction"]["audit"] == {
        "candidate_line_count": 1,
        "authoritative_line_count": 31,
        "candidate_validation": "passed",
        "validation_error": None,
        "candidate_accepted_for_costing": False,
        "reason": (
            "Schema and citation validation do not prove that a semantic rate "
            "association is commercially correct."
        ),
    }


def test_invalid_llm_candidate_cannot_block_known_deterministic_costing() -> None:
    extraction = _generic_extraction(excerpt="Evidence invented by the model")

    result = build_llm_quotation(
        DOCS,
        api_key="test-key",
        request_fn=lambda _payload, _key: _llm_response(extraction),
    )

    assert result["currency"] == "USD"
    assert len(result["cost_lines"]) == 31
    assert result["extraction"]["audit"]["candidate_validation"] == "rejected"
    assert result["extraction"]["audit"]["validation_error"]
    assert result["extraction"]["audit"]["candidate_accepted_for_costing"] is False


def test_llm_timeout_must_be_positive(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    with pytest.raises(LLMExtractionError, match="greater than zero"):
        build_llm_quotation(tmp_path, api_key="test-key", timeout_seconds=0)


def test_openai_background_response_is_polled_until_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter([
        {"id": "resp_test", "status": "queued"},
        {"id": "resp_test", "status": "in_progress"},
        {"id": "resp_test", "status": "completed", "output": []},
    ])
    methods: list[str] = []

    def fake_api_request(request, *, timeout_seconds: float) -> dict:
        methods.append(request.get_method())
        assert timeout_seconds > 0
        return next(responses)

    monkeypatch.setattr(llm_extractor, "_api_request", fake_api_request)
    monkeypatch.setattr(llm_extractor.time, "sleep", lambda _seconds: None)

    response = llm_extractor._request_openai(
        {"model": "gpt-5-mini", "background": True},
        "test-key",
        timeout_seconds=10,
    )

    assert response["status"] == "completed"
    assert methods == ["POST", "GET", "GET"]


def test_llm_rate_outside_validity_is_never_confirmed(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    extraction = _generic_extraction(valid_to="2026-12-31")
    extraction["lines"][0]["valid_from"] = "2026-01-01"
    result = build_llm_quotation(
        tmp_path,
        api_key="test-key",
        request_fn=lambda _payload, _key: _llm_response(extraction),
    )
    assert result["cost_lines"][0]["confidence"] == "indicative"
    assert result["totals"]["by_currency"]["USD"]["indicative_subtotal"] == "251.00"


def test_llm_inverted_validity_window_fails_closed(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    extraction = _generic_extraction(valid_to="2026-12-31")
    extraction["lines"][0]["valid_from"] = "2027-01-01"
    with pytest.raises(LLMExtractionError, match="inverted rate validity"):
        build_llm_quotation(
            tmp_path,
            api_key="test-key",
            request_fn=lambda _payload, _key: _llm_response(extraction),
        )


def test_llm_hallucinated_evidence_fails_closed(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    with pytest.raises(LLMExtractionError, match="excerpt was not found"):
        build_llm_quotation(
            tmp_path,
            api_key="test-key",
            request_fn=lambda _payload, _key: _llm_response(_generic_extraction(excerpt="Imaginary limousine")),
        )


def test_llm_evidence_tolerates_formatting_but_preserves_literal_source(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    extraction = _generic_extraction()
    extraction["lines"][0]["rate_source"]["excerpt"] = (
        "Airport to Hotel — USD 125.500 per vehicle"
    )

    result = build_llm_quotation(
        tmp_path,
        api_key="test-key",
        request_fn=lambda _payload, _key: _llm_response(extraction),
    )

    assert result["cost_lines"][0]["rate_provenance"][0]["excerpt"] == (
        "Airport to Hotel: USD 125.50 per vehicle"
    )


def test_llm_evidence_does_not_accept_changed_commercial_unit(tmp_path: Path) -> None:
    _generic_docs(tmp_path)
    extraction = _generic_extraction()
    extraction["lines"][0]["rate_source"]["excerpt"] = (
        "Airport to Hotel: USD 125.50 per person"
    )

    with pytest.raises(LLMExtractionError, match="excerpt was not found"):
        build_llm_quotation(
            tmp_path,
            api_key="test-key",
            request_fn=lambda _payload, _key: _llm_response(extraction),
        )
