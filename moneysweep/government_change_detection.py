"""Bounded discovery of government organizational-change candidates.

This is discovery only: lexical hits are never identity or binding evidence.
Callers must preserve the source assertion and adjudicate candidates through
``moneysweep.government_changes.evaluate_event`` before promotion.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

DETECTOR_VERSION = "government_change_phrase_scan_v1"
SCOPE_CLAIM = "BOUNDED_NOT_EXHAUSTIVE"

# English + Puerto Rico-relevant Spanish vocabulary. These patterns optimize
# recall for explicit change language; vocabulary omission remains a search
# false-negative and therefore cannot certify absence of organizational change.
PATTERNS = {
    "DISSOLUTION": (r"\bdissol(?:ve|ved|ution)\b", r"\bdisoluci[oó]n\b", r"\bdisolver\b"),
    "ABOLITION": (r"\babolish(?:ed|ment)?\b", r"\babolici[oó]n\b", r"\bsuprim(?:e|ida|ido)\b"),
    "MERGER": (r"\bmerg(?:e|ed|er)\b", r"\bfusi[oó]n\b", r"\bfusionar\b"),
    "CONSOLIDATION": (r"\bconsolidat(?:e|ed|ion)\b", r"\bconsolidaci[oó]n\b"),
    "SPLIT": (r"\bsplit\b", r"\bdivide?\b", r"\bdivisi[oó]n\b"),
    "REORGANIZATION": (r"\breorgani[sz](?:e|ed|ation)\b", r"\breorganizaci[oó]n\b"),
    "RENAMING": (r"\brenam(?:e|ed|ing)\b", r"\bcambio de nombre\b", r"\brenombr(?:a|ada|ado)\b"),
    "SUCCESSOR_CREATION": (r"\bsuccessor (?:agency|entity|organization)\b", r"\bentidad sucesora\b"),
    "PARENT_CHANGE": (r"\btransferred? (?:to|under) the (?:department|agency|office)\b", r"\badscrit[ao] a\b"),
    "TRANSFER_OF_FUNCTIONS": (r"\btransfer(?:red)? (?:its |the )?functions?\b", r"\btransferencia de funciones\b"),
    "TRANSFER_OF_ASSETS": (r"\btransfer(?:red)? (?:its |the )?assets?\b", r"\btransferencia de activos\b"),
    "TRANSFER_OF_LIABILITIES": (r"\btransfer(?:red)? (?:its |the )?liabilit(?:y|ies)\b", r"\btransferencia de (?:deudas|obligaciones|pasivos)\b"),
    "TRANSFER_OF_PERSONNEL": (r"\btransfer(?:red)? (?:its |the )?(?:staff|personnel|employees)\b", r"\btransferencia de personal\b"),
    "TRANSFER_OF_CONTRACTS": (r"\btransfer(?:red)? (?:its |the )?contracts?\b", r"\btransferencia de contratos\b"),
    "TRANSFER_OF_APPROPRIATIONS": (r"\btransfer(?:red)? (?:its |the )?appropriations?\b", r"\btransferencia de asignaciones\b"),
    "LOSS_OF_STATUTORY_POWER": (r"\b(?:remove|revoke|eliminate)(?:d)? (?:its |the )?(?:authority|power)\b", r"\b(?:elimina|revoca)(?:r|da|do)? (?:la )?(?:facultad|autoridad|poder)\b"),
    "GAIN_OF_STATUTORY_POWER": (r"\bgrant(?:ed)? (?:new |additional )?(?:authority|power)\b", r"\bconfiere? (?:nuevas? )?(?:facultades|poderes)\b"),
    "PROCUREMENT_AUTHORITY_CHANGE": (r"\bprocurement authority\b", r"\bautoridad de compras\b"),
    "BUDGET_AUTHORITY_CHANGE": (r"\bbudget authority\b", r"\bautoridad presupuestaria\b"),
    "REGULATORY_AUTHORITY_CHANGE": (r"\bregulatory authority\b", r"\bautoridad regulatoria\b"),
    "ENFORCEMENT_AUTHORITY_CHANGE": (r"\benforcement authority\b", r"\bfacultad de fiscalizaci[oó]n\b"),
    "LICENSING_AUTHORITY_CHANGE": (r"\blicensing authority\b", r"\bfacultad de licenciamiento\b"),
    "OVERSIGHT_CHANGE": (r"\boversight (?:transferred|changed|authority)\b", r"\bsupervisi[oó]n (?:transferida|cambiada)\b"),
    "RECEIVERSHIP": (r"\breceivership\b", r"\bsindicatura\b"),
    "FISCAL_CONTROL": (r"\bfiscal (?:control|oversight)\b", r"\bcontrol fiscal\b"),
    "PRIVATIZATION": (r"\bprivati[sz](?:e|ed|ation)\b", r"\bprivatizaci[oó]n\b"),
    "PPP_TRANSFER": (r"\bpublic[- ]private partnership\b", r"\balianza p[uú]blico[- ]privada\b"),
    "CONCESSION": (r"\bconcession(?:aire)?\b", r"\bconcesi[oó]n\b"),
    "MUNICIPALIZATION": (r"\bmunicipali[sz]ation\b", r"\bmunicipalizaci[oó]n\b"),
    "CENTRALIZATION": (r"\bcentrali[sz]ation\b", r"\bcentralizaci[oó]n\b"),
    "DECENTRALIZATION": (r"\bdecentrali[sz]ation\b", r"\bdescentralizaci[oó]n\b"),
    "TEMPORARY_EMERGENCY_AUTHORITY": (r"\bemergency authority\b", r"\bautoridad de emergencia\b"),
    "SUNSET_EXTENSION": (r"\bsunset (?:date )?(?:extended|extension)\b", r"\bpr[oó]rroga.*vigencia\b"),
    "SUNSET_EXPIRATION": (r"\bsunset (?:date )?(?:expired|expiration)\b", r"\bexpiraci[oó]n.*vigencia\b"),
    "OPERATIONAL_SUSPENSION": (r"\boperations? (?:suspended|suspension)\b", r"\bsuspensi[oó]n de operaciones\b"),
    "DEFUNDING": (r"\bdefund(?:ed|ing)?\b", r"\bsin asignaci[oó]n presupuestaria\b"),
    "MATERIAL_BUDGET_REDUCTION": (r"\b(?:major|material|significant) budget (?:cut|reduction)\b", r"\breducci[oó]n (?:material|sustancial|significativa) del presupuesto\b"),
    "MATERIAL_HEADCOUNT_REDUCTION": (r"\b(?:major|material|significant) (?:staff|headcount) reduction\b", r"\breducci[oó]n (?:material|sustancial|significativa) de personal\b"),
}


def detect_candidates(*, text: str, source_assertion_id: str, affected_entity_id: str) -> list[dict]:
    """Return deterministic lexical candidates; never promote them to events."""
    if not isinstance(text, str) or not text:
        return []
    if not source_assertion_id or not affected_entity_id:
        raise ValueError("source_assertion_id and affected_entity_id are required")
    found: list[dict] = []
    for event_type, patterns in PATTERNS.items():
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                raw = match.group(0)
                identity = f"{source_assertion_id}|{affected_entity_id}|{event_type}|{match.start()}|{match.end()}|{raw}"
                found.append({
                    "candidate_id": "GCHC_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
                    "affected_entity_id": affected_entity_id,
                    "candidate_event_type": event_type,
                    "source_assertion_id": source_assertion_id,
                    "raw_match": raw,
                    "start": match.start(),
                    "end": match.end(),
                    "detector_version": DETECTOR_VERSION,
                    "scope_claim": SCOPE_CLAIM,
                    "certification_state": "CANDIDATE_NOT_IDENTITY",
                })
    return sorted(found, key=lambda row: (row["start"], row["end"], row["candidate_event_type"]))


def candidate_types(rows: Iterable[dict]) -> set[str]:
    return {str(row["candidate_event_type"]) for row in rows}
