"""Generalized selected-entity investigation orchestration.

The package resolves user-supplied entity targets to Money Sweep's canonical
``ENT_*`` identity layer before any lineage or correlation work. Name/alias
normalization is discovery-only unless it resolves through the committed
canonical alias registry; ambiguous matches fail closed to REVIEW.
"""

from .models import InvestigationTarget, ResolutionState
from .orchestrator import InvestigationResult, investigate
from .resolver import CanonicalEntityIndex

__all__ = [
    "CanonicalEntityIndex",
    "InvestigationResult",
    "InvestigationTarget",
    "ResolutionState",
    "investigate",
]
