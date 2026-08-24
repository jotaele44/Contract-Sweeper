from __future__ import annotations

from moneysweep.discovery.models import CertificationState, IdentityState
from moneysweep.discovery.pr_judiciary import JudiciaryCaseHit, hit_to_candidates
from moneysweep.entity_resolution.keys import Identifier, has_unique_authoritative_id


def test_matching_authoritative_identifier_requires_temporal_overlap() -> None:
    left = [Identifier("duns", "123", valid_from="2005-01-01", valid_to="2010-12-31")]
    right = [Identifier("duns", "123", valid_from="2018-01-01", valid_to="2022-12-31")]
    assert has_unique_authoritative_id(left, right) is False


def test_matching_authoritative_identifier_with_overlap_can_anchor() -> None:
    left = [Identifier("duns", "123", valid_from="2005-01-01", valid_to="2015-12-31")]
    right = [Identifier("duns", "123", valid_from="2008-01-01", valid_to="2014-12-31")]
    assert has_unique_authoritative_id(left, right) is True


def test_overlapping_authoritative_conflict_fails_closed_even_with_other_match() -> None:
    left = [
        Identifier("uei", "MATCH", valid_from="2020-01-01"),
        Identifier("cage", "LEFT", valid_from="2020-01-01"),
    ]
    right = [
        Identifier("uei", "MATCH", valid_from="2020-01-01"),
        Identifier("cage", "RIGHT", valid_from="2020-01-01"),
    ]
    assert has_unique_authoritative_id(left, right) is False


def test_nonoverlapping_historical_succession_is_preserved_without_false_conflict() -> None:
    left = [
        Identifier("duns", "OLD", valid_from="2000-01-01", valid_to="2010-12-31"),
        Identifier("duns", "NEW", valid_from="2011-01-01"),
    ]
    right = [Identifier("duns", "NEW", valid_from="2015-01-01")]
    assert has_unique_authoritative_id(left, right) is True


def test_judiciary_party_name_is_candidate_not_identity() -> None:
    hit = JudiciaryCaseHit(
        query="ACME CORP",
        query_type="party_or_entity",
        case_number="SJ2026CV00001",
        court="San Juan",
        case_type="Civil",
        judge=None,
        party_names=("ACME CORP",),
        source_record_id="SJ2026CV00001",
    )
    pairs = hit_to_candidates(hit, retrieved_at="2026-08-24T18:00:00-04:00")
    candidate, evidence = pairs[0]

    assert candidate.identity_state is IdentityState.CANDIDATE
    assert candidate.certification_state is CertificationState.CANDIDATE_NOT_IDENTITY
    assert candidate.identifiers == ()
    assert candidate.raw_names == ("ACME CORP",)
    assert evidence.source_id == "pr_judiciary_case_search"
