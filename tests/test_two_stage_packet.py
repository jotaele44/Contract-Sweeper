from __future__ import annotations

from pathlib import Path

from moneysweep.discovery.models import (
    Cardinality,
    CertificationState,
    Contradiction,
    ContradictionKind,
    DiscoveryStagePacket,
    EntityCandidate,
    IdentityState,
    RelationshipAssertion,
    SourceEvidence,
)
from moneysweep.discovery.packet import dump_packet, load_packet
from moneysweep.entity_resolution.keys import Identifier


def _evidence(ref: str) -> SourceEvidence:
    return SourceEvidence(
        evidence_ref=ref,
        source_id="fixture",
        source_record_id=ref,
        url="https://example.invalid/fixture",
        retrieved_at="2026-08-24T18:00:00-04:00",
    )


def test_stage2_excludes_candidate_not_identity_and_unresolved() -> None:
    candidates = (
        EntityCandidate(
            candidate_id="confirmed",
            entity_type="organization",
            raw_names=("Confirmed Raw",),
            normalized_names=("CONFIRMED RAW",),
            identifiers=(Identifier("uei", "UEI1"),),
            identity_state=IdentityState.CONFIRMED,
            certification_state=CertificationState.PASS,
            evidence_refs=("ev1",),
        ),
        EntityCandidate(
            candidate_id="judiciary-hit",
            entity_type="unknown",
            raw_names=("Name Hit",),
            normalized_names=("NAME HIT",),
            identifiers=(),
            identity_state=IdentityState.CANDIDATE,
            certification_state=CertificationState.CANDIDATE_NOT_IDENTITY,
            evidence_refs=("ev2",),
        ),
        EntityCandidate(
            candidate_id="tied",
            entity_type="organization",
            raw_names=("Tied",),
            normalized_names=("TIED",),
            identifiers=(),
            identity_state=IdentityState.UNRESOLVED,
            certification_state=CertificationState.UNRESOLVED,
            evidence_refs=("ev3",),
        ),
    )
    packet = DiscoveryStagePacket(
        case_id="case-1",
        created_at="2026-08-24T18:00:00-04:00",
        subject_seeds=("Confirmed Raw",),
        candidates=candidates,
        relationships=(),
        contradictions=(),
        explicit_exclusions=(),
        source_manifest=(_evidence("ev1"), _evidence("ev2"), _evidence("ev3")),
    )
    assert packet.stage2_subject_ids() == ("confirmed",)


def test_packet_roundtrip_preserves_cardinality_temporal_ids_and_contradictions(tmp_path: Path) -> None:
    candidates = (
        EntityCandidate(
            candidate_id="a",
            entity_type="organization",
            raw_names=("A, Inc.",),
            normalized_names=("A INC",),
            canonical_candidate="A Inc.",
            identifiers=(
                Identifier(
                    "duns",
                    "123",
                    valid_from="2005-01-01",
                    valid_to="2015-12-31",
                    issuer="Dun & Bradstreet",
                    source_record_id="r1",
                ),
            ),
            identity_state=IdentityState.PROBABLE,
            certification_state=CertificationState.PROVISIONAL,
            evidence_refs=("ev1",),
        ),
        EntityCandidate(
            candidate_id="b",
            entity_type="organization",
            raw_names=("B LLC",),
            normalized_names=("B LLC",),
            identifiers=(),
            identity_state=IdentityState.CANDIDATE,
            certification_state=CertificationState.CANDIDATE_NOT_IDENTITY,
            evidence_refs=("ev2",),
        ),
    )
    packet = DiscoveryStagePacket(
        case_id="case-roundtrip",
        created_at="2026-08-24T18:00:00-04:00",
        subject_seeds=("A, Inc.",),
        candidates=candidates,
        relationships=(
            RelationshipAssertion(
                left_candidate_id="a",
                predicate="AFFILIATED_WITH",
                right_candidate_id="b",
                cardinality=Cardinality.MANY_TO_MANY,
                evidence_refs=("ev1", "ev2"),
                valid_from="2010-01-01",
            ),
        ),
        contradictions=(
            Contradiction(
                kind=ContradictionKind.IDENTITY,
                candidate_ids=("a", "b"),
                evidence_refs=("ev1", "ev2"),
                state="OPEN",
                note="candidate relationship is not identity equivalence",
            ),
        ),
        explicit_exclusions=("name_only_auto_merge",),
        source_manifest=(_evidence("ev1"), _evidence("ev2")),
    )

    path = tmp_path / "packet.json"
    dump_packet(packet, path)
    first = path.read_bytes()
    loaded = load_packet(path)
    dump_packet(loaded, path)
    second = path.read_bytes()

    assert first == second
    assert loaded.relationships[0].cardinality is Cardinality.MANY_TO_MANY
    assert loaded.candidates[0].identifiers[0].valid_to == "2015-12-31"
    assert loaded.contradictions[0].kind is ContradictionKind.IDENTITY


def test_packet_rejects_duplicate_candidate_ids() -> None:
    candidate = EntityCandidate(
        candidate_id="dup",
        entity_type="organization",
        raw_names=("Raw",),
        normalized_names=("RAW",),
        identifiers=(),
        identity_state=IdentityState.CANDIDATE,
        certification_state=CertificationState.CANDIDATE_NOT_IDENTITY,
        evidence_refs=("ev",),
    )
    try:
        DiscoveryStagePacket(
            case_id="case",
            created_at="2026-08-24T18:00:00-04:00",
            subject_seeds=("Raw",),
            candidates=(candidate, candidate),
            relationships=(),
            contradictions=(),
            explicit_exclusions=(),
            source_manifest=(_evidence("ev"),),
        )
    except ValueError as exc:
        assert "duplicate candidate_id" in str(exc)
    else:
        raise AssertionError("duplicate candidate ids must fail closed")
