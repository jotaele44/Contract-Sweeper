"""FIN_AUDIT — financial-audit domain descriptor.

Contracts and amendments, grants and transfers, expenditures and debt,
contractors/subcontractors, and infrastructure/project finance.
"""

from __future__ import annotations

from moneysweep.domains._descriptor import DomainDescriptor

FIN_AUDIT = DomainDescriptor(
    domain="fin_audit",
    title="Financial Audit Domain",
    record_families=(
        "contract",
        "amendment",
        "award",
        "subaward",
        "grant",
        "transfer",
        "invoice",
        "payment",
        "budget",
        "debt",
        "capital_project",
    ),
    access_class_default="public",
    edge_predicates=(
        "AWARDED_CONTRACT_TO",
        "AMENDS_CONTRACT",
        "TRANSFERRED_FUNDS_TO",
        "RECEIVED_GRANT_FROM",
        "SUBCONTRACTED_TO",
        "FUNDED_PROJECT",
        "OPERATES_PROJECT",
        "SERVES_MUNICIPALITY",
        "PREPARED_REPORT_FOR",
        "INSPECTED_ASSET",
        "REPORTED_EXPENDITURE_FOR",
    ),
)
