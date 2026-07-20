"""Bulk CSV input adapter.

Two-phase: validate synchronously (fast feedback), then enqueue asynchronously
after the user confirms. Never drops a row silently — every row becomes a
candidate or lands in the rejects list with a reason.
"""

import csv
import io
from decimal import Decimal, InvalidOperation

from charset_normalizer import from_bytes
from pydantic import BaseModel, ValidationError

from app.core.enums import InputChannel, SourcingMode
from app.schemas.candidate import ProductCandidateIn

CANONICAL_FIELDS: dict[str, list[str]] = {
    "name": ["name", "product_name", "title", "product", "item"],
    "upc": ["upc", "ean", "barcode", "gtin"],
    "asin": ["asin"],
    "url": ["url", "link", "product_url", "source_url"],
    "brand": ["brand", "manufacturer"],
    "local_price": ["price", "cost", "local_price", "buy_price"],
    "source_name": ["store", "supplier", "source", "vendor"],
    "moq": ["moq", "min_order", "minimum_order_quantity"],
}


class CSVRowResult(BaseModel):
    row_number: int
    candidate: ProductCandidateIn | None = None
    error: str | None = None
    duplicate: bool = False


class CSVValidationSummary(BaseModel):
    total_rows: int
    valid: int
    skipped: int
    duplicates: int
    rejects: list[CSVRowResult]
    header_mapping: dict[str, str]


def _decode(raw: bytes) -> str:
    """Handle UTF-8-BOM, Latin-1, etc. via charset detection."""
    best = from_bytes(raw).best()
    return str(best) if best else raw.decode("utf-8", errors="replace")


def _normalize(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def map_headers(raw_headers: list[str]) -> dict[str, str]:
    """Map canonical field -> the raw header name present in the file."""
    normalized = {h: _normalize(h) for h in raw_headers}
    mapping: dict[str, str] = {}
    for canonical, aliases in CANONICAL_FIELDS.items():
        for raw, norm in normalized.items():
            if norm in aliases:
                mapping[canonical] = raw
                break
    return mapping


def _parse_price(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = value.strip().lstrip("$").replace(",", "")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value.strip()))
    except (ValueError, TypeError):
        return None


def validate_csv(
    raw: bytes,
    *,
    sourcing_mode: SourcingMode,
    max_rows: int,
) -> CSVValidationSummary:
    """Phase 1: parse and validate. Streams rows; caps at max_rows."""
    text = _decode(raw)
    # Sniff delimiter (handles ; from European Excel), fall back to comma.
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)

    if not reader.fieldnames:
        return CSVValidationSummary(
            total_rows=0, valid=0, skipped=0, duplicates=0, rejects=[], header_mapping={}
        )

    mapping = map_headers(list(reader.fieldnames))
    if not any(k in mapping for k in ("name", "upc", "asin", "url")):
        raise ValueError(
            "CSV has no identifiable product column "
            "(need one of: name, upc, asin, url)"
        )

    results: list[CSVRowResult] = []
    seen: set[str] = set()
    valid = skipped = duplicates = 0

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        if i - 1 > max_rows:
            break
        try:
            candidate = ProductCandidateIn(
                name=row.get(mapping.get("name", "")),
                upc=row.get(mapping.get("upc", "")),
                asin=row.get(mapping.get("asin", "")),
                url=row.get(mapping.get("url", "")),
                brand=row.get(mapping.get("brand", "")),
                local_price=_parse_price(row.get(mapping.get("local_price", ""))),
                source_name=row.get(mapping.get("source_name", "")),
                moq=_parse_int(row.get(mapping.get("moq", ""))),
                sourcing_mode=sourcing_mode,
                input_channel=InputChannel.csv,
                raw_input=dict(row),
            )
        except ValidationError as e:
            skipped += 1
            results.append(CSVRowResult(row_number=i, error=_short_error(e)))
            continue

        h = candidate.compute_dedup_hash()
        if h in seen:
            duplicates += 1
            results.append(CSVRowResult(row_number=i, duplicate=True))
            continue
        seen.add(h)
        valid += 1
        results.append(CSVRowResult(row_number=i, candidate=candidate))

    return CSVValidationSummary(
        total_rows=len(results),
        valid=valid,
        skipped=skipped,
        duplicates=duplicates,
        rejects=[r for r in results if r.error or r.duplicate],
        header_mapping=mapping,
    )


def _short_error(e: ValidationError) -> str:
    try:
        return e.errors()[0].get("msg", "invalid row")
    except (IndexError, KeyError):
        return "invalid row"
