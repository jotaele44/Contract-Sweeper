"""Read-only FastAPI routes for the MoneySweep capital-and-control graph."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Query

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "staging" / "processed"
HOLDINGS_FILE = "capital_control_holdings.csv"
HOLDINGS_PATH = PROCESSED / HOLDINGS_FILE

router = APIRouter(prefix="/capital-control", tags=["capital-control"])
_CACHE: tuple[float, pd.DataFrame] | None = None

REQUIRED_COLUMNS = {
    "observation_id",
    "issuer_id",
    "issuer_name",
    "security_id",
    "holder_legal_entity_id",
    "holder_reported_name_raw",
    "as_of_date",
    "report_date",
    "position_class",
    "relation_type",
    "identity_status",
    "source_id",
    "source_document_id",
}


def _data() -> pd.DataFrame:
    global _CACHE
    if not HOLDINGS_PATH.exists():
        return pd.DataFrame()
    mtime = HOLDINGS_PATH.stat().st_mtime
    if _CACHE and _CACHE[0] == mtime:
        return _CACHE[1]
    frame = pd.read_csv(HOLDINGS_PATH, dtype=str, low_memory=False, keep_default_na=False)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise RuntimeError(f"{HOLDINGS_FILE} missing required columns: {missing}")
    _CACHE = (mtime, frame)
    return frame


def _num(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _int(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _effective(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Apply amendment supersession and fail closed on tied top observations."""
    if frame.empty:
        return frame.copy(), 0
    working = frame.copy()
    for col in ("investor_family_id", "ultimate_parent_id", "amendment_sequence"):
        if col not in working.columns:
            working[col] = ""
    working["_seq"] = working["amendment_sequence"].map(_int)
    key = [
        "issuer_id",
        "security_id",
        "holder_legal_entity_id",
        "as_of_date",
        "position_class",
        "relation_type",
    ]
    effective_rows: list[pd.Series] = []
    unresolved = 0
    for _, group in working.groupby(key, sort=True, dropna=False):
        max_seq = group["_seq"].max()
        top = group[group["_seq"] == max_seq]
        if top["observation_id"].nunique(dropna=False) != 1:
            unresolved += 1
            continue
        effective_rows.append(top.sort_values("observation_id", kind="stable").iloc[0])
    if not effective_rows:
        return working.iloc[0:0].drop(columns=["_seq"]), unresolved
    return pd.DataFrame(effective_rows).drop(columns=["_seq"]), unresolved


def _record(row: pd.Series) -> dict:
    return {
        "observationId": row.get("observation_id") or None,
        "issuerId": row.get("issuer_id") or None,
        "issuerName": row.get("issuer_name") or None,
        "securityId": row.get("security_id") or None,
        "securityName": row.get("security_name") or None,
        "holderLegalEntityId": row.get("holder_legal_entity_id") or None,
        "holderReportedNameRaw": row.get("holder_reported_name_raw") or None,
        "investorFamilyId": row.get("investor_family_id") or None,
        "investorFamilyName": row.get("investor_family_name") or None,
        "ultimateParentId": row.get("ultimate_parent_id") or None,
        "ultimateParentName": row.get("ultimate_parent_name") or None,
        "asOfDate": row.get("as_of_date") or None,
        "reportDate": row.get("report_date") or None,
        "shares": _num(row.get("shares")),
        "marketValue": _num(row.get("market_value")),
        "percentClass": _num(row.get("percent_class")),
        "percentIssuer": _num(row.get("percent_issuer")),
        "votingPercent": _num(row.get("voting_percent")),
        "positionClass": row.get("position_class") or None,
        "relationType": row.get("relation_type") or None,
        "identityStatus": row.get("identity_status") or None,
        "sourceId": row.get("source_id") or None,
        "sourceDocumentId": row.get("source_document_id") or None,
        "sourceUrl": row.get("source_url") or None,
        "retrievalUtc": row.get("retrieval_utc") or None,
        "amendmentSequence": _int(row.get("amendment_sequence")),
    }


@router.get("/summary")
def capital_control_summary():
    frame = _data()
    effective, unresolved_ties = _effective(frame)
    return {
        "file": HOLDINGS_FILE,
        "present": HOLDINGS_PATH.exists(),
        "rawObservations": int(len(frame)),
        "effectiveObservations": int(len(effective)),
        "unresolvedAmendmentTies": unresolved_ties,
        "issuers": int(effective["issuer_id"].nunique()) if not effective.empty else 0,
        "legalHolders": int(effective["holder_legal_entity_id"].nunique()) if not effective.empty else 0,
        "investorFamilies": int(effective["investor_family_id"].replace("", pd.NA).nunique()) if not effective.empty and "investor_family_id" in effective else 0,
        "ultimateParents": int(effective["ultimate_parent_id"].replace("", pd.NA).nunique()) if not effective.empty and "ultimate_parent_id" in effective else 0,
    }


@router.get("/holdings")
def capital_control_holdings(
    issuer_id: str | None = None,
    q: str | None = None,
    identity_status: str | None = None,
    position_class: str | None = None,
    as_of_date: str | None = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    frame, _ = _effective(_data())
    if frame.empty:
        return []
    if issuer_id:
        frame = frame[frame["issuer_id"] == issuer_id]
    if identity_status:
        frame = frame[frame["identity_status"] == identity_status]
    if position_class:
        frame = frame[frame["position_class"] == position_class]
    if as_of_date:
        frame = frame[frame["as_of_date"] == as_of_date]
    if q:
        cols = [c for c in ("issuer_name", "holder_reported_name_raw", "investor_family_name", "ultimate_parent_name") if c in frame]
        if cols:
            mask = pd.Series(False, index=frame.index)
            for col in cols:
                mask |= frame[col].astype(str).str.contains(q, case=False, na=False, regex=False)
            frame = frame[mask]
    sort_cols = [c for c in ("as_of_date", "percent_issuer", "market_value") if c in frame]
    if sort_cols:
        frame = frame.sort_values(sort_cols, ascending=False, kind="stable")
    return [_record(row) for _, row in frame.head(limit).iterrows()]


@router.get("/compare")
def compare_issuers(
    issuer_a: str,
    issuer_b: str,
    identity_level: Literal["legal_holder", "investor_family", "ultimate_parent"] = "legal_holder",
):
    frame, unresolved_ties = _effective(_data())
    field = {
        "legal_holder": "holder_legal_entity_id",
        "investor_family": "investor_family_id",
        "ultimate_parent": "ultimate_parent_id",
    }[identity_level]
    if frame.empty or field not in frame:
        a: set[str] = set()
        b: set[str] = set()
    else:
        a = {str(v) for v in frame.loc[frame["issuer_id"] == issuer_a, field] if str(v).strip()}
        b = {str(v) for v in frame.loc[frame["issuer_id"] == issuer_b, field] if str(v).strip()}
    return {
        "issuerA": issuer_a,
        "issuerB": issuer_b,
        "identityLevel": identity_level,
        "intersection": sorted(a & b),
        "aOnly": sorted(a - b),
        "bOnly": sorted(b - a),
        "union": sorted(a | b),
        "symmetricDifference": sorted(a ^ b),
        "counts": {
            "intersection": len(a & b),
            "aOnly": len(a - b),
            "bOnly": len(b - a),
            "union": len(a | b),
            "symmetricDifference": len(a ^ b),
        },
        "unresolvedAmendmentTies": unresolved_ties,
    }
