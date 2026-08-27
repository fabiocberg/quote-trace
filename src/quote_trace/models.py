from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any


MONEY_QUANTUM = Decimal("0.01")


def money(value: str | int | Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def money_text(value: Decimal | None) -> str | None:
    return None if value is None else f"{money(value):.2f}"


class Confidence(str, Enum):
    CONFIRMED = "confirmed"
    CONDITIONAL = "conditional"
    INDICATIVE = "indicative"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class SourceReference:
    document: str
    page: int | None
    section: str
    excerpt: str


@dataclass(frozen=True)
class Rate:
    amount: Decimal
    currency: str
    unit: str
    source: SourceReference
    validity: str | None = None
    supersedes: tuple[SourceReference, ...] = ()


@dataclass(frozen=True)
class BookedService:
    id: str
    date: str
    category: str
    description: str
    source: SourceReference
    operational_quantity: str


@dataclass
class CostLine:
    service: BookedService
    pricing_quantity: str | None
    unit_rate: Decimal | None
    currency: str | None
    rate_unit: str | None
    line_total: Decimal | None
    formula: str | None
    confidence: Confidence
    confidence_reason: str
    rate_provenance: list[SourceReference] = field(default_factory=list)
    candidate_amounts: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewItem:
    id: str
    service_ids: tuple[str, ...]
    issue: str
    impact: str
    required_action: str


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return money_text(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
