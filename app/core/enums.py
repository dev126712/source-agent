from enum import Enum


class SourcingMode(str, Enum):
    retail_arb = "retail_arb"
    wholesale = "wholesale"
    artisan = "artisan"


class InputChannel(str, Enum):
    photo = "photo"
    barcode = "barcode"
    text = "text"
    csv = "csv"
    discovery = "discovery"  # location-based auto-discovery


class SubscriptionTier(str, Enum):
    free = "free"
    premium = "premium"  # unlocks scheduled/background discovery


class CandidateStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"
    skipped = "skipped"


class Verdict(str, Enum):
    strong = "strong"
    marginal = "marginal"
    avoid = "avoid"
