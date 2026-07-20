import hashlib
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import InputChannel, SourcingMode


class ProductCandidateIn(BaseModel):
    """What an input adapter produces. Identity + source context only —
    no researched data, no bookkeeping. Enriched into a DB row downstream."""

    name: str | None = None
    upc: str | None = None
    asin: str | None = None
    url: str | None = None
    brand: str | None = None
    category_hint: str | None = None

    local_price: Decimal | None = None
    currency: str = "USD"
    source_name: str | None = None
    source_location: str | None = None
    quantity_available: int | None = None
    moq: int | None = None

    sourcing_mode: SourcingMode
    input_channel: InputChannel
    raw_input: dict | None = None

    @model_validator(mode="after")
    def require_identifier(self):
        if not any([self.name, self.upc, self.asin, self.url]):
            raise ValueError("candidate needs at least one of: name, upc, asin, url")
        return self

    def compute_dedup_hash(self) -> str:
        """Stable key for dedup: prefer the strongest identifier available."""
        basis = (
            self.upc
            or self.asin
            or (self.name or "").strip().lower()
            or (self.url or "").strip().lower()
        )
        return hashlib.sha256(basis.encode()).hexdigest()


class ProductCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: object
    name: str | None
    asin: str | None
    status: str
    sourcing_mode: str
