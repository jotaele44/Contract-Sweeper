"""Deterministic DiscoveryStagePacket serialization and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
from moneysweep.entity_resolution.keys import Identifier


def packet_from_dict(payload: dict[str, Any]) -> DiscoveryStagePacket:
    if payload.get("schema_version") != "discovery_stage_packet_v1":
        raise ValueError("unsupported discovery packet schema_version")

    candidates = tuple(
        EntityCandidate(
            candidate_id=row["candidate_id"],
            entity_type=row["entity_type"],
            raw_names=tuple(row.get("raw_names", [])),
            normalized_names=tuple(row.get("normalized_names", [])),
            canonical_candidate=row.get("canonical_candidate"),
            identifiers=tuple(Identifier(**identifier) for identifier in row.get("identifiers", [])),
            identity_state=IdentityState(row["identity_state"]),
            certification_state=CertificationState(row["certification_state"]),
            evidence_refs=tuple(row.get("evidence_refs", [])),
            addresses=tuple(row.get("addresses", [])),
        )
        for row in payload.get("candidates", [])
    )
    relationships = tuple(
        RelationshipAssertion(
            left_candidate_id=row["left_candidate_id"],
            predicate=row["predicate"],
            right_candidate_id=row["right_candidate_id"],
            cardinality=Cardinality(row["cardinality"]),
            evidence_refs=tuple(row.get("evidence_refs", [])),
            valid_from=row.get("valid_from"),
            valid_to=row.get("valid_to"),
        )
        for row in payload.get("relationships", [])
    )
    contradictions = tuple(
        Contradiction(
            kind=ContradictionKind(row["kind"]),
            candidate_ids=tuple(row.get("candidate_ids", [])),
            evidence_refs=tuple(row.get("evidence_refs", [])),
            state=row.get("state", "OPEN"),
            note=row.get("note"),
        )
        for row in payload.get("contradictions", [])
    )
    manifest = tuple(SourceEvidence(**row) for row in payload.get("source_manifest", []))
    return DiscoveryStagePacket(
        case_id=payload["case_id"],
        created_at=payload["created_at"],
        subject_seeds=tuple(payload.get("subject_seeds", [])),
        candidates=candidates,
        relationships=relationships,
        contradictions=contradictions,
        explicit_exclusions=tuple(payload.get("explicit_exclusions", [])),
        source_manifest=manifest,
    )


def load_packet(path: Path) -> DiscoveryStagePacket:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("discovery packet must be a JSON object")
    return packet_from_dict(payload)


def dump_packet(packet: DiscoveryStagePacket, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(packet.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")
