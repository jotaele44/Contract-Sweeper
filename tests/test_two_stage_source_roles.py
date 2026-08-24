from __future__ import annotations

from moneysweep.discovery.source_roles import (
    FROZEN_SOURCE_COUNT,
    FROZEN_SOURCE_IDS_SHA256,
    SourceRole,
    build_role_ledger,
    role_counts,
)


def test_frozen_source_role_ledger_closes_exactly() -> None:
    ledger = build_role_ledger()
    assert FROZEN_SOURCE_COUNT == 158
    assert FROZEN_SOURCE_IDS_SHA256 == (
        "673659d9c53e8428e21052d95819ff35023e90142756686e73a9c9f1b326bbf2"
    )
    assert len(ledger) == FROZEN_SOURCE_COUNT
    assert len({record.source_id for record in ledger}) == FROZEN_SOURCE_COUNT
    assert all(record.justification for record in ledger)
    assert sum(role_counts(ledger).values()) == FROZEN_SOURCE_COUNT


def test_known_source_role_overrides_are_semantically_bounded() -> None:
    roles = {record.source_id: record.role for record in build_role_ledger()}
    assert roles["sam_entities"] is SourceRole.DISCOVERY
    assert roles["rdc_demandas_civiles"] is SourceRole.BOTH
    assert roles["nara_nextgen_catalog_v3"] is SourceRole.RECOVERY
    assert roles["usaspending_prime"] is SourceRole.CORPUS


def test_every_role_is_one_of_the_four_allowed_states() -> None:
    allowed = {SourceRole.DISCOVERY, SourceRole.CORPUS, SourceRole.BOTH, SourceRole.RECOVERY}
    assert all(record.role in allowed for record in build_role_ledger())
