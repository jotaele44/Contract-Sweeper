"""Adapter registry for the on-demand query module.

Adds an entry per concrete adapter. Sources without a concrete adapter
are served by :class:`NotImplementedAdapter` via :func:`get_adapter`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from .base import SourceAdapter
from ._stub import NotImplementedAdapter
from .capital_control import Sec13FCapitalControlAdapter
from .ckan_metastore import (
    CHIPAdapter,
    CMSOpenPaymentsAdapter,
    MedicaidFMAPAdapter,
)
from .cms_socrata import MedicareAdvantageAdapter, MedicarePartsAdapter
from .entity_base import EntityAdapter
from .fdic import FDICInstitutionsAdapter
from .fec import FECPRAdapter
from .fhlb import FHLBAdvancesAdapter
from .highergov import HigherGovSupplementalAdapter
from .lda import LDAAdapter
from .nih import NIHReporterAdapter
from .nonprofits import NonprofitsIRS990Adapter
from .nsf import NSFAwardsAdapter
from .ofac import OFACSDNAdapter
from .openfema import (
    OpenFEMAHmgpAdapter,
    OpenFEMANfipClaimsAdapter,
    OpenFEMAPaAdapter,
)
from .sam import SAMEntitiesAdapter
from .sba import SBALoansAdapter, SBAPaycheckProtectionAdapter
from .sbir import SBIRAdapter
from .usaspending import (
    DOEGrantsAdapter,
    DOJGrantsAdapter,
    DOTGrantsAdapter,
    EDGrantsAdapter,
    EPAGrantsAdapter,
    EXIMBankAdapter,
    HAFAdapter,
    HHSGrantsAdapter,
    HUDHCVSection8Adapter,
    OIAGrantsAdapter,
    SLFRFAdapter,
    SNAPNAPAdapter,
    USAspendingGrantsAdapter,
    USAspendingPrimeAdapter,
    USAspendingSubawardsAdapter,
    USACECivilWorksAdapter,
    USDAGrantsAdapter,
    VABenefitsAdapter,
    WICAdapter,
    WIOAAdapter,
)

#: Concrete adapters keyed by their registry source_id.
ADAPTER_REGISTRY: dict[str, Type[SourceAdapter]] = {
    USAspendingPrimeAdapter.source_id: USAspendingPrimeAdapter,
    USAspendingSubawardsAdapter.source_id: USAspendingSubawardsAdapter,
    USAspendingGrantsAdapter.source_id: USAspendingGrantsAdapter,
    OpenFEMAPaAdapter.source_id: OpenFEMAPaAdapter,
    OpenFEMAHmgpAdapter.source_id: OpenFEMAHmgpAdapter,
    FECPRAdapter.source_id: FECPRAdapter,
    NIHReporterAdapter.source_id: NIHReporterAdapter,
    SBIRAdapter.source_id: SBIRAdapter,
    EPAGrantsAdapter.source_id: EPAGrantsAdapter,
    DOTGrantsAdapter.source_id: DOTGrantsAdapter,
    EDGrantsAdapter.source_id: EDGrantsAdapter,
    HHSGrantsAdapter.source_id: HHSGrantsAdapter,
    DOEGrantsAdapter.source_id: DOEGrantsAdapter,
    DOJGrantsAdapter.source_id: DOJGrantsAdapter,
    USDAGrantsAdapter.source_id: USDAGrantsAdapter,
    OIAGrantsAdapter.source_id: OIAGrantsAdapter,
    LDAAdapter.source_id: LDAAdapter,
    NSFAwardsAdapter.source_id: NSFAwardsAdapter,
    OpenFEMANfipClaimsAdapter.source_id: OpenFEMANfipClaimsAdapter,
    SLFRFAdapter.source_id: SLFRFAdapter,
    HAFAdapter.source_id: HAFAdapter,
    EXIMBankAdapter.source_id: EXIMBankAdapter,
    VABenefitsAdapter.source_id: VABenefitsAdapter,
    WIOAAdapter.source_id: WIOAAdapter,
    WICAdapter.source_id: WICAdapter,
    SNAPNAPAdapter.source_id: SNAPNAPAdapter,
    HUDHCVSection8Adapter.source_id: HUDHCVSection8Adapter,
    USACECivilWorksAdapter.source_id: USACECivilWorksAdapter,
    FHLBAdvancesAdapter.source_id: FHLBAdvancesAdapter,
    FDICInstitutionsAdapter.source_id: FDICInstitutionsAdapter,
    NonprofitsIRS990Adapter.source_id: NonprofitsIRS990Adapter,
    SBALoansAdapter.source_id: SBALoansAdapter,
    SBAPaycheckProtectionAdapter.source_id: SBAPaycheckProtectionAdapter,
    HigherGovSupplementalAdapter.source_id: HigherGovSupplementalAdapter,
    MedicareAdvantageAdapter.source_id: MedicareAdvantageAdapter,
    MedicarePartsAdapter.source_id: MedicarePartsAdapter,
    CMSOpenPaymentsAdapter.source_id: CMSOpenPaymentsAdapter,
    MedicaidFMAPAdapter.source_id: MedicaidFMAPAdapter,
    CHIPAdapter.source_id: CHIPAdapter,
}

#: Entity-mode adapters keyed by their registry source_id.
ENTITY_ADAPTER_REGISTRY: dict[str, Type[EntityAdapter]] = {
    SAMEntitiesAdapter.source_id: SAMEntitiesAdapter,
    OFACSDNAdapter.source_id: OFACSDNAdapter,
    Sec13FCapitalControlAdapter.source_id: Sec13FCapitalControlAdapter,
}


def get_adapter(source_id: str, *, root: Path) -> SourceAdapter:
    """Return a concrete adapter for `source_id`, or the stub fallback."""
    cls = ADAPTER_REGISTRY.get(source_id)
    if cls is None:
        return NotImplementedAdapter(root=root, source_id=source_id)
    return cls(root=root)


def get_entity_adapter(source_id: str, *, root: Path) -> EntityAdapter:
    """Return a concrete entity adapter for ``source_id``."""
    return ENTITY_ADAPTER_REGISTRY[source_id](root=root)


__all__ = [
    "ADAPTER_REGISTRY",
    "ENTITY_ADAPTER_REGISTRY",
    "get_adapter",
    "get_entity_adapter",
    "SourceAdapter",
    "EntityAdapter",
    "NotImplementedAdapter",
]
