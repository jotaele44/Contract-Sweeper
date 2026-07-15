"""Contradictions are preserved side-by-side, never overwritten."""

import pytest

from moneysweep.fusion.contradictions import ContradictionStore
from moneysweep.fusion.models import ContradictionStatus


@pytest.mark.unit
def test_conflicting_claims_both_retained():
    store = ContradictionStore()
    store.add_claim("entity_x", "REPORTED_EXPENDITURE_FOR", 100000, "src_a", "T2")
    entry = store.add_claim("entity_x", "REPORTED_EXPENDITURE_FOR", 250000, "src_b", "T2")

    # Both source claims are kept; neither overwrites the other.
    assert len(entry.claims) == 2
    assert set(entry.distinct_values()) == {100000, 250000}
    assert entry.is_conflicting
    assert entry.status is ContradictionStatus.UNRESOLVED
    assert entry in store.conflicts()


@pytest.mark.unit
def test_agreeing_claims_are_not_a_conflict():
    store = ContradictionStore()
    store.add_claim("entity_y", "SERVES_MUNICIPALITY", "Ponce", "src_a")
    entry = store.add_claim("entity_y", "SERVES_MUNICIPALITY", "Ponce", "src_b")
    assert not entry.is_conflicting
    assert entry.status is ContradictionStatus.NONE
    assert store.conflicts() == []


@pytest.mark.unit
def test_resolving_keeps_claims_for_provenance():
    store = ContradictionStore()
    store.add_claim("entity_z", "OWNS", "A", "src_a")
    store.add_claim("entity_z", "OWNS", "B", "src_b")
    store.resolve("entity_z", "OWNS")
    entry = store.get("entity_z", "OWNS")
    assert entry.status is ContradictionStatus.RESOLVED
    # Provenance preserved even after resolution.
    assert len(entry.claims) == 2
