"""SQLAlchemy models.

Importing this package registers every model on ``Base.metadata``. Alembic's
autogenerate relies on that — a model that is never imported is invisible to it
and silently omitted from migrations.
"""

from app.db.session import Base
from app.models.candidate import ProductCandidate
from app.models.discovery import DiscoveryRun, SeenProduct
from app.models.report import SourcingReport, SourcingRun

__all__ = [
    "Base",
    "ProductCandidate",
    "DiscoveryRun",
    "SeenProduct",
    "SourcingReport",
    "SourcingRun",
]
