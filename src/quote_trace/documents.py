from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


OPERATIONAL_FILE = "MRA-2027-0641-Halloran-operational-quotation.pdf"
RATE_PACK_FILE = "Supplier-Rate-Pack-SA-2027-v3.pdf"
EMAIL_FILE = "Supplier-email-Camissa-2027-rates.txt"


def is_known_document_set(input_dir: Path) -> bool:
    return all((input_dir / name).is_file() for name in (OPERATIONAL_FILE, RATE_PACK_FILE, EMAIL_FILE))


@dataclass(frozen=True)
class DocumentSet:
    operational_pages: tuple[str, ...]
    rate_pack_pages: tuple[str, ...]
    supplier_email: str


def _read_pdf(path: Path) -> tuple[str, ...]:
    try:
        pages = tuple((page.extract_text() or "").strip() for page in PdfReader(path).pages)
    except Exception as exc:  # pragma: no cover - library-specific failures
        raise ValueError(f"Could not read {path.name}: {exc}") from exc
    if not pages or any(not page for page in pages):
        raise ValueError(f"{path.name} contains an empty or unreadable page")
    return pages


def load_documents(input_dir: Path) -> DocumentSet:
    required = [OPERATIONAL_FILE, RATE_PACK_FILE, EMAIL_FILE]
    missing = [name for name in required if not (input_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing input document(s): {', '.join(missing)}")

    documents = DocumentSet(
        operational_pages=_read_pdf(input_dir / OPERATIONAL_FILE),
        rate_pack_pages=_read_pdf(input_dir / RATE_PACK_FILE),
        supplier_email=(input_dir / EMAIL_FILE).read_text(encoding="ascii"),
    )
    anchors = {
        "operational quotation": ("REF: MRA-2027-0641", "Beach Villa Grande"),
        "rate pack": ("SA-RATES-2027-v3", "Do not carry forward previously quoted fares"),
        "supplier email": ("corrected rates", "These supersede anything you have on file for 2027"),
    }
    bodies = {
        "operational quotation": "\n".join(documents.operational_pages),
        "rate pack": "\n".join(documents.rate_pack_pages),
        "supplier email": documents.supplier_email,
    }
    for label, expected in anchors.items():
        absent = [anchor for anchor in expected if anchor not in bodies[label]]
        if absent:
            raise ValueError(f"Unexpected {label} content; missing anchor(s): {absent}")
    return documents
