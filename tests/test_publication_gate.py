"""Publication-gate and edge-builder safety tests."""

import pytest

from moneysweep.fusion.edge_builder import EdgeValidationError, build_edge
from moneysweep.fusion.models import AssertionType, PublicationStatus
from moneysweep.fusion.publication_gate import (
    PublicationGateError,
    check_publishable,
)


def _edge(**overrides):
    kwargs = dict(
        subject_entity_id="entity_a",
        predicate="LOBBIED_FOR",
        object_entity_id="entity_b",
        source_record_id="src_1",
        evidence_tier="T2",
        assertion_type=AssertionType.EXPLICIT,
    )
    kwargs.update(overrides)
    return build_edge(**kwargs)


@pytest.mark.unit
def test_edge_without_source_record_id_is_rejected():
    with pytest.raises(EdgeValidationError):
        _edge(source_record_id="")


@pytest.mark.unit
def test_conclusory_predicate_is_rejected():
    with pytest.raises(EdgeValidationError):
        _edge(predicate="INFLUENCED")


@pytest.mark.unit
def test_fact_checked_approved_edge_is_publishable():
    edge = _edge(publication_status=PublicationStatus.PUBLIC)
    decision = check_publishable(edge, fact_checked=True, publication_approved=True)
    assert decision.publishable is True
    assert decision.reasons == ()


@pytest.mark.unit
def test_public_edge_without_factcheck_is_blocked():
    edge = _edge(publication_status=PublicationStatus.PUBLIC)
    decision = check_publishable(edge, fact_checked=False, publication_approved=True)
    assert decision.publishable is False
    with pytest.raises(PublicationGateError):
        decision.raise_if_blocked()


@pytest.mark.unit
def test_inferred_edge_never_auto_published():
    edge = _edge(assertion_type=AssertionType.INFERRED)
    decision = check_publishable(edge, fact_checked=True, publication_approved=True)
    assert decision.publishable is False
    assert any("inferred" in r for r in decision.reasons)


@pytest.mark.unit
def test_guilt_by_association_edge_is_blocked():
    edge = _edge()
    decision = check_publishable(
        edge,
        fact_checked=True,
        publication_approved=True,
        guilt_by_association_only=True,
    )
    assert decision.publishable is False
    assert any("association" in r for r in decision.reasons)


@pytest.mark.unit
def test_non_minimized_pii_is_blocked():
    edge = _edge()
    decision = check_publishable(
        edge, fact_checked=True, publication_approved=True, pii_minimized=False
    )
    assert decision.publishable is False
    assert any("PII" in r for r in decision.reasons)
