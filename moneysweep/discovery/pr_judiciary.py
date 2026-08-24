"""Puerto Rico Judicial Branch case-search discovery adapter.

The public ``Consulta de Casos`` surface is an orientation/search system, not the
canonical judicial record. Accordingly every hit emitted by this module is
``CANDIDATE_NOT_IDENTITY`` until independently adjudicated.

Transport is injected rather than guessing an undocumented iframe/private API.
The production transport must be pinned from an observed public request/response
contract before activation; fixture/offline use can exercise normalization now.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from moneysweep.discovery.models import (
    CertificationState,
    EntityCandidate,
    IdentityState,
    SourceEvidence,
)

SOURCE_ID = "pr_judiciary_case_search"
PUBLIC_SEARCH_URL = "https://poderjudicial.pr/consulta-de-casos/"
PUBLIC_RECORDS_GUIDANCE_URL = (
    "https://poderjudicial.pr/servicios-a-la-comunidad/"
    "examen-de-expedientes-judiciales-y-solicitud-de-copias-de-documentos/"
)

SearchTransport = Callable[[str, str], Iterable[Mapping[str, Any]]]


@dataclass(frozen=True)
class JudiciaryCaseHit:
    query: str
    query_type: str
    case_number: str | None
    court: str | None
    case_type: str | None
    judge: str | None
    party_names: tuple[str, ...]
    counsel_names: tuple[str, ...] = ()
    result_rank: int | None = None
    source_record_id: str | None = None

    @classmethod
    def from_mapping(
        cls, query: str, query_type: str, row: Mapping[str, Any], rank: int
    ) -> "JudiciaryCaseHit":
        def text(*keys: str) -> str | None:
            for key in keys:
                value = row.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
            return None

        def names(*keys: str) -> tuple[str, ...]:
            for key in keys:
                value = row.get(key)
                if isinstance(value, (list, tuple)):
                    return tuple(str(item) for item in value if str(item).strip())
                if value is not None and str(value).strip():
                    return tuple(part.strip() for part in str(value).split("|") if part.strip())
            return ()

        return cls(
            query=query,
            query_type=query_type,
            case_number=text("case_number", "numero_caso", "caseNumber"),
            court=text("court", "tribunal", "court_name"),
            case_type=text("case_type", "tipo_caso", "nature"),
            judge=text("judge", "juez", "judge_name"),
            party_names=names("party_names", "partes", "parties"),
            counsel_names=names("counsel_names", "abogados", "counsel"),
            result_rank=rank,
            source_record_id=text("source_record_id", "record_id", "id"),
        )


def search_cases(
    query: str,
    *,
    query_type: str = "party_or_entity",
    transport: SearchTransport,
) -> tuple[JudiciaryCaseHit, ...]:
    """Run a bounded search through an injected observed transport.

    Search rank is preserved for provenance/discovery only and MUST NOT be used
    as identity evidence.
    """
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    rows = transport(query, query_type)
    return tuple(
        JudiciaryCaseHit.from_mapping(query, query_type, row, rank)
        for rank, row in enumerate(rows, start=1)
    )


def hit_to_candidates(
    hit: JudiciaryCaseHit,
    *,
    retrieved_at: str,
) -> tuple[tuple[EntityCandidate, SourceEvidence], ...]:
    """Convert each published party string to an identity-neutral candidate."""
    candidates: list[tuple[EntityCandidate, SourceEvidence]] = []
    for party_index, raw_name in enumerate(hit.party_names, start=1):
        stable_material = "|".join(
            [
                SOURCE_ID,
                hit.case_number or "NO_CASE_NUMBER",
                hit.source_record_id or "NO_RECORD_ID",
                str(party_index),
                raw_name,
            ]
        )
        token = hashlib.sha256(stable_material.encode("utf-8")).hexdigest()[:24]
        evidence_ref = f"ev_judiciary_{token}"
        candidate_id = f"cand_judiciary_{token}"
        source_record_id = hit.source_record_id or hit.case_number
        evidence = SourceEvidence(
            evidence_ref=evidence_ref,
            source_id=SOURCE_ID,
            source_record_id=source_record_id,
            url=PUBLIC_SEARCH_URL,
            retrieved_at=retrieved_at,
            assertion_type="explicit",
        )
        candidate = EntityCandidate(
            candidate_id=candidate_id,
            entity_type="unknown",
            raw_names=(raw_name,),
            normalized_names=(),
            identifiers=(),
            identity_state=IdentityState.CANDIDATE,
            certification_state=CertificationState.CANDIDATE_NOT_IDENTITY,
            evidence_refs=(evidence_ref,),
        )
        candidates.append((candidate, evidence))
    return tuple(candidates)
