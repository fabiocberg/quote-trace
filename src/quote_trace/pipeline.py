from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from .documents import EMAIL_FILE, OPERATIONAL_FILE, RATE_PACK_FILE, DocumentSet, load_documents
from .models import (
    BookedService,
    Confidence,
    CostLine,
    Rate,
    ReviewItem,
    SourceReference,
    money,
    money_text,
    to_jsonable,
)


def _ref(document: str, page: int | None, section: str, excerpt: str) -> SourceReference:
    return SourceReference(document=document, page=page, section=section, excerpt=excerpt)


def _assert_source(documents: DocumentSet, reference: SourceReference) -> None:
    if reference.document == OPERATIONAL_FILE:
        body = documents.operational_pages[reference.page - 1] if reference.page else "\n".join(documents.operational_pages)
    elif reference.document == RATE_PACK_FILE:
        body = documents.rate_pack_pages[reference.page - 1] if reference.page else "\n".join(documents.rate_pack_pages)
    else:
        body = documents.supplier_email
    if reference.excerpt not in body:
        raise ValueError(
            f"Source excerpt for {reference.section!r} was not found in "
            f"{reference.document} page {reference.page}: {reference.excerpt!r}"
        )


def _service(
    documents: DocumentSet,
    service_id: str,
    date: str,
    category: str,
    description: str,
    page: int,
    excerpt: str,
    operational_quantity: str,
) -> BookedService:
    source = _ref(OPERATIONAL_FILE, page, "TRAVEL ARRANGEMENTS", excerpt)
    _assert_source(documents, source)
    return BookedService(service_id, date, category, description, source, operational_quantity)


def _amount_after(text: str, label_pattern: str, occurrence: int = 1) -> Decimal:
    matches = list(re.finditer(label_pattern + r"[\s\S]{0,180}?([0-9][0-9,]*\.[0-9]{2})", text, re.IGNORECASE))
    if len(matches) < occurrence:
        raise ValueError(f"Could not extract rate using pattern: {label_pattern}")
    return money(matches[occurrence - 1].group(1).replace(",", ""))


def _rate(
    documents: DocumentSet,
    amount: Decimal,
    unit: str,
    page: int | None,
    section: str,
    excerpt: str,
    validity: str | None = None,
    supersedes: tuple[SourceReference, ...] = (),
    document: str = RATE_PACK_FILE,
) -> Rate:
    source = _ref(document, page, section, excerpt)
    _assert_source(documents, source)
    return Rate(amount, "USD", unit, source, validity, supersedes)


def _priced(
    service: BookedService,
    rate: Rate,
    factors: Iterable[tuple[Decimal, str]],
    confidence: Confidence = Confidence.CONFIRMED,
    reason: str = "Current rate and booked service match unambiguously.",
    extra_provenance: Iterable[SourceReference] = (),
) -> CostLine:
    factor_list = list(factors)
    multiplier = Decimal("1")
    for value, _ in factor_list:
        multiplier *= value
    total = money(multiplier * rate.amount)
    parts = [f"{value.normalize()} {label}" for value, label in factor_list]
    formula = " × ".join(parts + [f"USD {money_text(rate.amount)}"]) + f" = USD {money_text(total)}"
    return CostLine(
        service=service,
        pricing_quantity=" × ".join(parts),
        unit_rate=rate.amount,
        currency=rate.currency,
        rate_unit=rate.unit,
        line_total=total,
        formula=formula,
        confidence=confidence,
        confidence_reason=reason,
        rate_provenance=[rate.source, *rate.supersedes, *extra_provenance],
    )


def _unresolved(
    service: BookedService,
    reason: str,
    provenance: Iterable[SourceReference] = (),
    candidates: Iterable[dict[str, str]] = (),
) -> CostLine:
    return CostLine(
        service=service,
        pricing_quantity=None,
        unit_rate=None,
        currency=None,
        rate_unit=None,
        line_total=None,
        formula=None,
        confidence=Confidence.UNRESOLVED,
        confidence_reason=reason,
        rate_provenance=list(provenance),
        candidate_amounts=list(candidates),
    )


def build_quotation(input_dir: str | Path) -> dict:
    documents = load_documents(Path(input_dir))
    pack1, pack2, pack3 = documents.rate_pack_pages
    email = documents.supplier_email

    pack_camissa = _ref(RATE_PACK_FILE, 1, "1. CAPE TOWN — ACCOMMODATION", "Family Suite\nBed & Breakfast\n340.00")
    rates = {
        "meet_greet": _rate(documents, _amount_after(pack1, r"One Way Assistance \(Meet & Greet\)"), "per person per movement", 1, "2. CAPE TOWN — TOURING & TRANSFERS", "One Way Assistance (Meet & Greet)"),
        "cpt_transfer": _rate(documents, _amount_after(pack1, r"Transfer CIA to Zone 1, 06H00.?21H00, with guide"), "per vehicle one way", 1, "2. CAPE TOWN — TOURING & TRANSFERS", "Transfer CIA to Zone 1, 06H00–21H00, with guide"),
        "trailer": _rate(documents, _amount_after(pack1, r"Trailer supplement"), "per group per transfer", 1, "2a. Trailer supplement", "Trailer supplement, required for groups of 6 pax and above"),
        "camissa_family": _rate(documents, _amount_after(email, r"Family Suite \(B&B\)"), "per room per night", None, "Corrected 2027 rates", "Family Suite (B&B)        USD 375.00 per room per night", "2027 arrivals", (pack_camissa,), EMAIL_FILE),
        "camissa_classic": _rate(documents, _amount_after(email, r"Classic Room \(B&B\)"), "per room per night", None, "Corrected 2027 rates", "Classic Room (B&B)        USD 230.00 per room per night", "2027 arrivals", (_ref(RATE_PACK_FILE, 1, "1. CAPE TOWN — ACCOMMODATION", "Classic Room\nBed & Breakfast\n210.00"),), EMAIL_FILE),
        "hike": _rate(documents, _amount_after(pack1, r"SLOW Walks & Hikes . Rise & Climb, Table Mountain"), "per person", 1, "2. CAPE TOWN — TOURING & TRANSFERS", "SLOW Walks & Hikes — Rise & Climb, Table Mountain"),
        "peninsula": _rate(documents, _amount_after(pack1, r"Full Day Peninsula Scenic Tour, private"), "per vehicle", 1, "2. CAPE TOWN — TOURING & TRANSFERS", "Full Day Peninsula Scenic Tour, private"),
        "custom": _rate(documents, _amount_after(pack1, r"Custom Private Tour, full day"), "per person", 1, "2. CAPE TOWN — TOURING & TRANSFERS", "Custom Private Tour, full day"),
        "group_extra": _rate(documents, _amount_after(pack1, r"Per Group Extra"), "per group", 1, "2b. Custom Private Tour", "Per Group Extra of 140.00 per group"),
        "marula_levy": _rate(documents, _amount_after(pack2, r"Marula Reserve Conservation Levy"), "per person per night", 2, "3. MARULA RESERVE", "Marula Reserve Conservation Levy: 28.00 per person per night"),
        "kudu": _rate(documents, _amount_after(pack2, r"Luxury Suite\s+"), "per person sharing per night", 2, "4. KUDU SANDS", "Luxury Suite\n890.00\nper person sharing per night"),
        "kudu_levy": _rate(documents, _amount_after(pack2, r"Kudu Sands Conservation Levy"), "per person per night", 2, "4. KUDU SANDS", "Kudu Sands Conservation Levy: 35.00 per person per night"),
        "lowveld_out": _rate(documents, _amount_after(pack2, r"Kudu Sands lodges to MQP"), "per person one way", 2, "5. LOWVELD — ROAD TRANSFERS", "Kudu Sands lodges to MQP (Kruger Mpumalanga)"),
        "vehicle_fee": _rate(documents, _amount_after(pack2, r"Vehicle Entrance Fee"), "per group per entry", 2, "5. LOWVELD — ROAD TRANSFERS", "Vehicle Entrance Fee 40.00 per group per entry"),
        "entrance_fee": _rate(documents, _amount_after(pack2, r"(?<!Vehicle )Entrance Fee"), "per person per entry", 2, "5. LOWVELD — ROAD TRANSFERS", "Entrance Fee 25.00 per pax per entry"),
        "beach_villa": _rate(documents, _amount_after(pack3, r"Beach Villa\s+"), "per villa per night", 3, "6. MOZAMBIQUE", "Beach Villa\n780.00\nper villa per night"),
        "helicopter": _rate(documents, _amount_after(pack3, r"Helicopter transfer VNX \(Vilanculos\) . Benguerra"), "per person per way", 3, "7. MOZAMBIQUE — AIR & SEA TRANSFERS", "Helicopter transfer VNX (Vilanculos) – Benguerra island lodges", "01 Jan 25 – 31 Dec 26"),
    }
    no_airfare_ref = _ref(RATE_PACK_FILE, 3, "8. AIR — SCHEDULED AND CHARTER", "Airfares are not carried in this pack")
    gate_ref = _ref(RATE_PACK_FILE, 2, "5. LOWVELD — ROAD TRANSFERS", "depends on the gate used on the day")
    marula_ref = _ref(RATE_PACK_FILE, 2, "3. MARULA RESERVE", "01 Apr 27 – 09 Jul 27")
    free_transfer_ref = _ref(RATE_PACK_FILE, 2, "3. MARULA RESERVE", "Complimentary scheduled road transfer from Hoedspruit Airport (HDS)")
    triple_ref = _ref(RATE_PACK_FILE, 2, "4a. Triple occupancy", "No supplement and no reduction applies")
    for source in [*rates.values(), no_airfare_ref, gate_ref, marula_ref, free_transfer_ref, triple_ref]:
        if isinstance(source, Rate):
            for reference in [source.source, *source.supersedes]:
                _assert_source(documents, reference)
        else:
            _assert_source(documents, source)

    s = lambda *args: _service(documents, *args)
    services = {
        "cpt_meet_arrival": s("cpt_meet_arrival", "2027-07-05", "meet_and_greet", "Cape Town arrival assistance", 1, "One Way Assistance", "5 travellers × 1 movement"),
        "cpt_transfer_in": s("cpt_transfer_in", "2027-07-05", "road_transfer", "CPT to Camissa, guided daytime transfer", 1, "Pick up: CPT\nDrop off: The Camissa Boutique Hotel", "1 vehicle one way"),
        "cpt_trailer_in": s("cpt_trailer_in", "2027-07-05", "supplement", "Trailer supplement, inbound", 1, "Included: 1 x Trailer 6+ Pax per group", "1 group"),
        "camissa_family": s("camissa_family", "2027-07-05", "accommodation", "Camissa Family Suite, B&B", 1, "1 x Family Suite on a Bed and Breakfast basis", "1 room × 4 nights"),
        "camissa_classic": s("camissa_classic", "2027-07-05", "accommodation", "Camissa Classic Room, B&B", 1, "1 x Classic Room on a Bed and Breakfast basis", "1 room × 4 nights"),
        "table_mountain": s("table_mountain", "2027-07-06", "activity", "Rise & Climb Table Mountain hike", 1, "Half Day Rise & Climb - Table Mountain Hike", "5 people"),
        "peninsula": s("peninsula", "2027-07-07", "activity", "Private Full Day Peninsula Scenic Tour", 1, "Full Day Peninsula Scenic Tour", "1 vehicle"),
        "custom_tour": s("custom_tour", "2027-07-08", "activity", "Custom Private Tour", 1, "Custom Private Tour", "5 people"),
        "custom_extra": s("custom_extra", "2027-07-08", "supplement", "Custom tour per-group extra", 2, "Included: 1 x Per Group Extra per group", "1 group"),
        "cpt_transfer_out": s("cpt_transfer_out", "2027-07-09", "road_transfer", "Camissa to CPT, guided daytime transfer", 2, "Pick up: The Camissa Boutique Hotel\nDrop off: CPT", "1 vehicle one way"),
        "cpt_trailer_out": s("cpt_trailer_out", "2027-07-09", "supplement", "Trailer supplement, outbound", 2, "Included: 1 x Trailer 6+ Pax per group", "1 group"),
        "flight_cpt_hds": s("flight_cpt_hds", "2027-07-09", "flight", "Zambezi Air CPT to HDS", 2, "Arrival: 4Z, Hoedspruit", "5 people"),
        "hds_marula": s("hds_marula", "2027-07-09", "road_transfer", "Scheduled HDS to Marula transfer", 2, "Complimentary scheduled transfer", "5 guests, stay of 2 nights"),
        "marula_family": s("marula_family", "2027-07-09", "accommodation", "Marula Family Chalet, fully inclusive", 2, "Family Chalet on a Fully Inclusive", "1 chalet × 2 nights"),
        "marula_pool": s("marula_pool", "2027-07-09", "accommodation", "Marula Tented Pool Suite, fully inclusive", 2, "Tented Pool Suite on a Fully Inclusive", "1 suite × 2 nights"),
        "marula_levy": s("marula_levy", "2027-07-09", "levy", "Marula conservation levy", 2, "Included: 2 x Consv Levy compulsory pax", "5 people × 2 nights"),
        "marula_kudu": s("marula_kudu", "2027-07-11", "road_transfer", "Marula River Lodge to Kudu Ridge", 2, "Pick up: Marula River Lodge\nDrop off: Kudu Ridge Private Game Reserve", "5 people one way"),
        "kudu_gate_in": s("kudu_gate_in", "2027-07-11", "entrance_fee", "Vehicle entrance fee on arrival at Kudu", 2, "Included: 1 x Vehicle Entrance Fee per group", "1 group per entry"),
        "kudu_suite": s("kudu_suite", "2027-07-11", "accommodation", "Kudu Ridge Luxury Suites, fully inclusive", 2, "2 x Luxury Suite on a Fully Inclusive", "5 people × 3 nights"),
        "kudu_levy": s("kudu_levy", "2027-07-11", "levy", "Kudu conservation levy", 2, "Included: 3 x Conservation Levy compulsory pax", "5 people × 3 nights"),
        "kudu_triple": s("kudu_triple", "2027-07-11", "occupancy", "Luxury Suite triple occupancy", 2, "Included: 1 x Triple per group", "1 triple arrangement"),
        "kudu_mqp": s("kudu_mqp", "2027-07-14", "road_transfer", "Kudu Ridge to MQP", 2, "Pick up: Kudu Ridge Private Game Reserve\nDrop off: MQP", "5 people one way"),
        "kudu_gate_pax": s("kudu_gate_pax", "2027-07-14", "entrance_fee", "Passenger entrance fee at Kudu departure", 2, "Included: 1 x Entrance Fee per pax", "5 people per entry"),
        "kudu_gate_vehicle": s("kudu_gate_vehicle", "2027-07-14", "entrance_fee", "Vehicle entrance fee at Kudu departure", 2, "Included: 1 x Vehicle Entrance Fee per group", "1 group per entry"),
        "flight_mqp_vnx": s("flight_mqp_vnx", "2027-07-14", "flight", "Zambezi Air MQP to VNX", 3, "Arrival: 4Z, Vilancoulos", "5 people"),
        "heli_out": s("heli_out", "2027-07-14", "air_transfer", "VNX to Ilha Azul helicopter transfer", 3, "Pick up: VNX\nDrop off: Ilha Azul Beach Lodge", "5 people × 1 way"),
        "ilha_beach": s("ilha_beach", "2027-07-14", "accommodation", "Ilha Azul Beach Villa, fully inclusive", 3, "1 x Beach Villa & 1 x Beach Villa Grande", "1 villa × 3 nights"),
        "ilha_grande": s("ilha_grande", "2027-07-14", "accommodation", "Ilha Azul Beach Villa Grande, fully inclusive", 3, "1 x Beach Villa & 1 x Beach Villa Grande", "1 villa × 3 nights"),
        "heli_back": s("heli_back", "2027-07-17", "air_transfer", "Ilha Azul to VNX helicopter transfer", 3, "Pick up: Ilha Azul Beach Lodge\nDrop off: VNX", "5 people × 1 way"),
        "flight_vnx_jnb": s("flight_vnx_jnb", "2027-07-17", "flight", "Zambezi Air VNX to JNB", 3, "Arrival: 4Z, Johannesburg", "5 people"),
        "jnb_meet_departure": s("jnb_meet_departure", "2027-07-17", "meet_and_greet", "Johannesburg departure assistance", 3, "One Way Assistance", "5 travellers × 1 movement"),
    }

    zero_rate = Rate(money("0"), "USD", "included", free_transfer_ref)
    triple_zero = Rate(money("0"), "USD", "no supplement", triple_ref)
    lines = [
        _priced(services["cpt_meet_arrival"], rates["meet_greet"], [(Decimal(5), "people"), (Decimal(1), "movement")]),
        _priced(services["cpt_transfer_in"], rates["cpt_transfer"], [(Decimal(1), "vehicle")]),
        _priced(services["cpt_trailer_in"], rates["trailer"], [(Decimal(1), "group")], Confidence.CONDITIONAL, "Booked explicitly, but the normal threshold is 6+ passengers; five are travelling. Excess luggage may still justify it."),
        _priced(services["camissa_family"], rates["camissa_family"], [(Decimal(1), "room"), (Decimal(4), "nights")], reason="Supplier email explicitly supersedes the rate pack for all 2027 arrivals."),
        _priced(services["camissa_classic"], rates["camissa_classic"], [(Decimal(1), "room"), (Decimal(4), "nights")], reason="Supplier email explicitly supersedes the rate pack for all 2027 arrivals."),
        _priced(services["table_mountain"], rates["hike"], [(Decimal(5), "people")]),
        _priced(services["peninsula"], rates["peninsula"], [(Decimal(1), "vehicle")]),
        _priced(services["custom_tour"], rates["custom"], [(Decimal(5), "people")]),
        _priced(services["custom_extra"], rates["group_extra"], [(Decimal(1), "group")]),
        _priced(services["cpt_transfer_out"], rates["cpt_transfer"], [(Decimal(1), "vehicle")]),
        _priced(services["cpt_trailer_out"], rates["trailer"], [(Decimal(1), "group")], Confidence.CONDITIONAL, "Booked explicitly, but the normal threshold is 6+ passengers; five are travelling. Excess luggage may still justify it."),
        _unresolved(services["flight_cpt_hds"], "Scheduled air must be quoted live; the rate pack forbids carrying forward fares.", [no_airfare_ref]),
        _priced(services["hds_marula"], zero_rate, [(Decimal(1), "included transfer")], reason="The scheduled transfer is complimentary for stays of two nights or more; this stay is two nights."),
        _unresolved(services["marula_family"], "The 9 July boundary appears in both Green and Peak seasons, and the pack does not define boundary or stay-spanning policy.", [marula_ref, _ref(RATE_PACK_FILE, 2, "3. MARULA RESERVE", "Family Chalet\n620.00\n890.00")], _marula_candidates(pack2, "Family Chalet", "chalet")),
        _unresolved(services["marula_pool"], "The 9 July boundary appears in both Green and Peak seasons, and the pack does not define boundary or stay-spanning policy.", [marula_ref, _ref(RATE_PACK_FILE, 2, "3. MARULA RESERVE", "Tented Pool Suite\n540.00\n760.00")], _marula_candidates(pack2, "Tented Pool Suite", "suite")),
        _priced(services["marula_levy"], rates["marula_levy"], [(Decimal(5), "people"), (Decimal(2), "nights")]),
        _unresolved(services["marula_kudu"], "The booked label says HDS to Kudu, but pickup is Marula River Lodge. No rate for Marula-to-Kudu is supplied.", [_ref(RATE_PACK_FILE, 2, "5. LOWVELD — ROAD TRANSFERS", "HDS to Kudu Sands lodges")]),
        _priced(services["kudu_gate_in"], rates["vehicle_fee"], [(Decimal(1), "group"), (Decimal(1), "entry")], Confidence.CONDITIONAL, "The fee is published, but applicability depends on the gate used and must be confirmed.", [gate_ref]),
        _priced(services["kudu_suite"], rates["kudu"], [(Decimal(5), "people"), (Decimal(3), "nights")], reason="Rate is per person sharing; the triple note charges the fifth guest at the standard sharing rate.", extra_provenance=[triple_ref]),
        _priced(services["kudu_levy"], rates["kudu_levy"], [(Decimal(5), "people"), (Decimal(3), "nights")]),
        _priced(services["kudu_triple"], triple_zero, [(Decimal(1), "triple arrangement")], reason="The rate pack explicitly states no supplement and no reduction for triple occupancy."),
        _priced(services["kudu_mqp"], rates["lowveld_out"], [(Decimal(5), "people")], Confidence.CONDITIONAL, "Pickup/drop-off match Kudu-to-MQP, but the operational service title describes the reverse direction."),
        _priced(services["kudu_gate_pax"], rates["entrance_fee"], [(Decimal(5), "people"), (Decimal(1), "entry")], Confidence.CONDITIONAL, "The fee is published, but applicability depends on the gate used and must be confirmed.", [gate_ref]),
        _priced(services["kudu_gate_vehicle"], rates["vehicle_fee"], [(Decimal(1), "group"), (Decimal(1), "entry")], Confidence.CONDITIONAL, "The fee is published, but applicability depends on the gate used and must be confirmed.", [gate_ref]),
        _unresolved(services["flight_mqp_vnx"], "Scheduled air must be quoted live; the rate pack forbids carrying forward fares.", [no_airfare_ref]),
        _priced(services["heli_out"], rates["helicopter"], [(Decimal(5), "people"), (Decimal(1), "way")], Confidence.INDICATIVE, "The only tariff expired on 31 December 2026 and is explicitly carried forward pending 2027 confirmation."),
        _priced(services["ilha_beach"], rates["beach_villa"], [(Decimal(1), "villa"), (Decimal(3), "nights")]),
        _unresolved(services["ilha_grande"], "Beach Villa Grande is not listed. It must not be assumed to mean Infinity Beach Villa.", [_ref(RATE_PACK_FILE, 3, "6. MOZAMBIQUE", "Infinity Beach Villa")]),
        _priced(services["heli_back"], rates["helicopter"], [(Decimal(5), "people"), (Decimal(1), "way")], Confidence.INDICATIVE, "The only tariff expired on 31 December 2026 and is explicitly carried forward pending 2027 confirmation."),
        _unresolved(services["flight_vnx_jnb"], "Scheduled air must be quoted live; the rate pack forbids carrying forward fares.", [no_airfare_ref]),
        _unresolved(services["jnb_meet_departure"], "The supplied assistance rate is in the Cape Town section; there is no Johannesburg rate.", [rates["meet_greet"].source]),
    ]

    reviews = _reviews()
    subtotals = {
        confidence.value: money(sum((line.line_total or Decimal("0")) for line in lines if line.confidence == confidence))
        for confidence in (Confidence.CONFIRMED, Confidence.CONDITIONAL, Confidence.INDICATIVE)
    }
    known_total = money(sum(subtotals.values(), Decimal("0")))
    result = {
        "schema_version": "1.0",
        "quotation_reference": "MRA-2027-0641",
        "currency": "USD",
        "pricing_policy": "Only deterministic, source-backed calculations are included. Candidate amounts and unresolved lines are excluded from subtotals.",
        "cost_lines": [to_jsonable(line) for line in lines],
        "totals": {
            "confirmed_subtotal": money_text(subtotals["confirmed"]),
            "conditional_subtotal": money_text(subtotals["conditional"]),
            "indicative_subtotal": money_text(subtotals["indicative"]),
            "known_amounts_total_not_client_ready": money_text(known_total),
            "unresolved_lines": sum(line.confidence == Confidence.UNRESOLVED for line in lines),
            "client_ready_total": None,
            "statement": "No final client-ready total exists until every needs_review item affecting price or applicability is resolved.",
        },
        "needs_review": [to_jsonable(item) for item in reviews],
    }
    _validate_result(result, lines)
    return result


def _marula_candidates(pack_page: str, room: str, unit: str) -> list[dict[str, str]]:
    values = re.search(re.escape(room) + r"\s+([0-9]+\.[0-9]{2})\s+([0-9]+\.[0-9]{2})", pack_page)
    if not values:
        raise ValueError(f"Could not extract Marula candidate rates for {room}")
    green, peak = map(money, values.groups())
    return [
        {"scenario": "arrival-date rule selects Green for both nights", "unit_rate": money_text(green), "line_total": money_text(green * 2), "unit": f"per {unit} per night"},
        {"scenario": "nightly split: 9 Jul Green, 10 Jul Peak", "unit_rate": "mixed", "line_total": money_text(green + peak), "unit": f"per {unit} per night"},
        {"scenario": "Peak applies from 9 Jul", "unit_rate": money_text(peak), "line_total": money_text(peak * 2), "unit": f"per {unit} per night"},
    ]


def _reviews() -> list[ReviewItem]:
    return [
        ReviewItem("review-trailers", ("cpt_trailer_in", "cpt_trailer_out"), "Trailer booked for five passengers although the normal threshold is six.", "USD 130.00 is conditional.", "Confirm excess-luggage requirement or remove both supplements."),
        ReviewItem("review-marula-season", ("marula_family", "marula_pool"), "Green and Peak validity overlap on check-in date 9 July.", "Both Marula room costs are excluded from totals.", "Obtain the supplier's boundary and stay-spanning rule, then select the applicable candidate."),
        ReviewItem("review-marula-kudu-route", ("marula_kudu",), "Service label and actual pickup describe different origins.", "No transfer price is included.", "Re-quote the actual Marula River Lodge-to-Kudu Ridge routing."),
        ReviewItem("review-gates", ("kudu_gate_in", "kudu_gate_pax", "kudu_gate_vehicle"), "Gate charges depend on the gate used.", "USD 205.00 is conditional.", "Confirm the planned gates and which of the three booked fees apply."),
        ReviewItem("review-kudu-direction", ("kudu_mqp",), "Service title is KMIA-to-Kudu while pickup/drop-off are Kudu-to-MQP.", "USD 950.00 is conditional.", "Correct the operational title and confirm direction with the transfer operator."),
        ReviewItem("review-helicopters", ("heli_out", "heli_back"), "Only a tariff ending in 2026 is available and a 2027 increase is expected.", "USD 3,950.00 is indicative.", "Obtain and apply the confirmed 2027 helicopter rate."),
        ReviewItem("review-villa-grande", ("ilha_grande",), "Beach Villa Grande has no matching contracted room type.", "One villa for three nights is unpriced.", "Confirm the booked room type and obtain its exact rate; do not assume Infinity Beach Villa."),
        ReviewItem("review-flights", ("flight_cpt_hds", "flight_mqp_vnx", "flight_vnx_jnb"), "Scheduled airfares must be quoted live.", "All three flight sectors are excluded.", "Price every sector live with fare class, taxes, baggage and validity."),
        ReviewItem("review-jnb-assistance", ("jnb_meet_departure",), "No Johannesburg assistance tariff is supplied.", "Departure assistance is unpriced.", "Obtain a Johannesburg supplier rate."),
    ]


def _validate_result(result: dict, lines: list[CostLine]) -> None:
    ids = [line.service.id for line in lines]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate service ids in costed quotation")
    if len(lines) != 31:
        raise ValueError(f"Expected 31 operational service lines, found {len(lines)}")
    for line in lines:
        if line.line_total is not None and not line.formula:
            raise ValueError(f"Priced line {line.service.id} has no formula")
        if line.line_total is not None and not line.rate_provenance:
            raise ValueError(f"Priced line {line.service.id} has no rate provenance")
        if line.line_total is None and line.confidence != Confidence.UNRESOLVED:
            raise ValueError(f"Unpriced line {line.service.id} must be unresolved")
    expected = sum((line.line_total or Decimal("0")) for line in lines)
    actual = money(result["totals"]["known_amounts_total_not_client_ready"])
    if money(expected) != actual:
        raise ValueError("Totals do not reconcile with cost lines")
