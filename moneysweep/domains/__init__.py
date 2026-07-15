"""Bounded domain descriptors for the NP / FIN / INF architecture.

Each descriptor is pure data + logic (no network, no filesystem coupling). The
four domain identifiers mirror ``data_intake_record.schema.json`` and the
``config/domains/*.yml`` files.

    np_layer   Nonprofit / public-interest layer (intake, review, publication).
    fin_audit  Financial-audit records.
    inf_ctrl   Influence-analysis records.
    shared     Cross-cutting records that belong to more than one domain.
"""

from __future__ import annotations

from moneysweep.domains.fin_audit import FIN_AUDIT
from moneysweep.domains.inf_ctrl import INF_CTRL
from moneysweep.domains.np_layer import NP_LAYER

# The ``shared`` domain has no descriptor object; it is a routing marker only.
DOMAIN_IDS = ("np_layer", "fin_audit", "inf_ctrl", "shared")

DOMAINS = {
    NP_LAYER.domain: NP_LAYER,
    FIN_AUDIT.domain: FIN_AUDIT,
    INF_CTRL.domain: INF_CTRL,
}

__all__ = ["DOMAIN_IDS", "DOMAINS", "NP_LAYER", "FIN_AUDIT", "INF_CTRL"]
