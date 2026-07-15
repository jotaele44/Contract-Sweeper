"""INF_CTRL — influence-analysis domain descriptor.

Lobbying registrations/clients/personnel, campaign and political-finance records,
appointments/boards/revolving-door roles, and declared organizational relationships.

Documented relationships only. This domain never asserts influence, capture, or
coordination; those are excluded predicates (see ``prohibited_predicates``).
"""

from __future__ import annotations

from moneysweep.domains._descriptor import DomainDescriptor

# Conclusory predicates this domain must never emit.
PROHIBITED_PREDICATES = (
    "INFLUENCED",
    "CAPTURED",
    "COORDINATED_WITH",
    "CONTROLLED_OUTCOME",
)

INF_CTRL = DomainDescriptor(
    domain="inf_ctrl",
    title="Influence Analysis Domain",
    record_families=(
        "lobby_registration",
        "lobby_client",
        "lobbyist",
        "quarterly_activity",
        "reported_expenditure",
        "appointment",
        "board_membership",
        "donation",
    ),
    access_class_default="public",
    edge_predicates=(
        "LOBBIED_FOR",
        "AUTHORIZED_PERSON_FOR",
        "EMPLOYED_BY",
        "BOARD_MEMBER_OF",
        "REGISTERED_AS",
        "AFFILIATED_WITH",
        "REPORTED_EXPENDITURE_FOR",
    ),
)
