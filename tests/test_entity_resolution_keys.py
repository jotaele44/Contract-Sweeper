"""Identifier hierarchy, temporal validity, and deterministic-id behavior."""

import pytest

from moneysweep.entity_resolution.keys import (
    AUTHORITATIVE_KEYS,
    Identifier,
    best_identifier,
    has_unique_authoritative_id,
    identifier_priority,
    internal_canonical_id,
    is_authoritative,
)


@pytest.mark.unit
def test_authoritative_precedence_ordering():
    # UEI (priority 1) beats CAGE (2) beats lobby_reg_number (8).
    assert identifier_priority("uei") < identifier_priority("cage")
    assert identifier_priority("cage") < identifier_priority("lobby_reg_number")
    # Unknown keys sort last.
    assert identifier_priority("not_a_key") > identifier_priority("internal_canonical_id")


@pytest.mark.unit
def test_only_expected_keys_are_authoritative():
    assert "uei" in AUTHORITATIVE_KEYS
    assert "duns" in AUTHORITATIVE_KEYS
    # Contextual identifiers are not authoritative.
    assert not is_authoritative("lobby_reg_number")
    assert not is_authoritative("vendor_id")
    assert not is_authoritative("internal_canonical_id")


@pytest.mark.unit
def test_best_identifier_picks_strongest():
    ids = [
        Identifier("lobby_reg_number", "L-99"),
        Identifier("uei", "UEIABC123"),
        Identifier("vendor_id", "V-1"),
    ]
    assert best_identifier(ids).key == "uei"
    assert best_identifier([]) is None


@pytest.mark.unit
def test_temporal_validity_preserves_historical_ids():
    duns = Identifier("duns", "080000000", valid_from="2005-01-01", valid_to="2015-12-31")
    # Valid within window, invalid outside, and a null query date always matches
    # (historical ids are never dropped).
    assert duns.is_valid_on("2010-06-01")
    assert not duns.is_valid_on("2020-01-01")
    assert not duns.is_valid_on("2000-01-01")
    assert duns.is_valid_on(None)


@pytest.mark.unit
def test_unique_authoritative_id_match_and_conflict():
    left = [Identifier("uei", "UEISAME1")]
    right = [Identifier("uei", "UEISAME1")]
    assert has_unique_authoritative_id(left, right)

    # Same key, different value -> not a unique authoritative match.
    right_conflict = [Identifier("uei", "UEIDIFF2")]
    assert not has_unique_authoritative_id(left, right_conflict)

    # No shared authoritative key -> not a match.
    assert not has_unique_authoritative_id(
        [Identifier("uei", "UEISAME1")], [Identifier("cage", "1ABC2")]
    )
    # Contextual-only ids never satisfy the authoritative gate.
    assert not has_unique_authoritative_id(
        [Identifier("lobby_reg_number", "L-1")], [Identifier("lobby_reg_number", "L-1")]
    )


@pytest.mark.unit
def test_internal_canonical_id_is_deterministic():
    a = internal_canonical_id("Arcadis Caribe, PSC")
    b = internal_canonical_id("ARCADIS CARIBE PSC")
    # Normalization strips the PSC suffix and case/punctuation, so both variants
    # collapse to the same deterministic id.
    assert a == b
    assert a.startswith("entity_")
    # Person ids use a distinct prefix.
    assert internal_canonical_id("Jane Doe", person=True).startswith("person_")
