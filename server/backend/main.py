"""
moneysweep-pr dashboard API
==============================
Thin FastAPI read layer over the frozen canonical_v1 CSVs (Tranche A). It does
NOT import the legacy pipeline — it reads data/canonical_v1/*.csv with pandas and
serves joined, dashboard-friendly JSON.

Start (from repo root):
    uvicorn server.backend.main:app --reload --port 8000

Schema reality (verified):
  * contracts reference awarding/contractor as entity_id FKs → join entities.csv
  * a contract's municipality comes from edges.csv (Entity LOCATED_IN Municipality)
  * award_amount is frequently blank → exposed as null; aggregates are null-safe
  * optional capital/control holdings are exposed as a typed /edges graph view
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]
CANON = ROOT / "data" / "canonical_v1"
PROCESSED = ROOT / "data" / "staging" / "processed"
CAPITAL_CONTROL_PATH = PROCESSED / "capital_control_holdings.csv"

EXPECTED = {
    "contracts": [
        "contract_id",
        "awarding_entity_id",
        "contractor_entity_id",
        "award_amount",
        "status",
        "start_date",
    ],
    "entities": ["entity_id", "name", "entity_type"],
    "edges": ["edge_id", "source_node_id", "edge_type", "target_node_id"],
    "municipalities": ["municipality_id", "name", "region"],
}

CAPITAL_REQUIRED = {
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

app = FastAPI(title="moneysweep-pr API", version="0.3.0")

# Dev CORS. Defaults to the Vite dev origins; override with a comma-separated
# MONEYSWEEP_CORS_ORIGINS when the frontend runs on a different port/host.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = [
    o.strip()
    for o in os.environ.get("MONEYSWEEP_CORS_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA: dict[str, pd.DataFrame] = {}
_CAPITAL_CACHE: tuple[float, pd.DataFrame] | None = None


def _load() -> None:
    """Load canonical CSVs into cached DataFrames; fail loud on header drift."""
    for name in ["contracts", "entities", "edges", "municipalities"]:
        path = CANON / f"{name}.csv"
        if not path.exists():
            raise RuntimeError(f"missing canonical file: {path}")
        df = pd.read_csv(path, dtype=str).fillna("")
        missing = [c for c in EXPECTED[name] if c not in df.columns]
        if missing:
            raise RuntimeError(
                f"{name}.csv missing expected columns {missing}; got {list(df.columns)}"
            )
        DATA[name] = df


_load()  # eager load at import → fail fast on missing files / header drift


def _num(v):
    """Parse a possibly-blank money string → float or None (never NaN)."""
    if v is None or v == "":
        return None
    try:
        f = float(str(v).replace("$", "").replace(",", "").strip())
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _int(v, default: int = 0) -> int:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return default


def _entity_name_map() -> dict[str, str]:
    e = DATA["entities"]
    return dict(zip(e["entity_id"], e["name"]))


def _muni_name_map() -> dict[str, str]:
    m = DATA["municipalities"]
    return dict(zip(m["municipality_id"], m["name"]))


def _located_in_map() -> dict[str, str]:
    """entity_id → municipality_id, from edges (Entity LOCATED_IN Municipality)."""
    e = DATA["edges"]
    li = e[e["edge_type"] == "LOCATED_IN"]
    return dict(zip(li["source_node_id"], li["target_node_id"]))


def _capital_data() -> pd.DataFrame:
    """Lazy-load the optional holdings ledger and fail loud on schema drift."""
    global _CAPITAL_CACHE
    if not CAPITAL_CONTROL_PATH.exists():
        return pd.DataFrame()
    mtime = CAPITAL_CONTROL_PATH.stat().st_mtime
    if _CAPITAL_CACHE and _CAPITAL_CACHE[0] == mtime:
        return _CAPITAL_CACHE[1]
    frame = pd.read_csv(
        CAPITAL_CONTROL_PATH,
        dtype=str,
        low_memory=False,
        keep_default_na=False,
    )
    missing = sorted(CAPITAL_REQUIRED - set(frame.columns))
    if missing:
        raise RuntimeError(
            f"{CAPITAL_CONTROL_PATH.name} missing required columns: {missing}"
        )
    _CAPITAL_CACHE = (mtime, frame)
    return frame


def _capital_effective(frame: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Whole-row amendment supersession; tied top observations fail closed."""
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
    rows: list[pd.Series] = []
    unresolved = 0
    for _, group in working.groupby(key, sort=True, dropna=False):
        max_seq = group["_seq"].max()
        top = group[group["_seq"] == max_seq]
        if top["observation_id"].nunique(dropna=False) != 1:
            unresolved += 1
            continue
        rows.append(top.sort_values("observation_id", kind="stable").iloc[0])
    if not rows:
        return working.iloc[0:0].drop(columns=["_seq"]), unresolved
    return pd.DataFrame(rows).drop(columns=["_seq"]), unresolved


def _capital_record(row: pd.Series) -> dict:
    """Preserve the reported legal-holder string while exposing roll-up levels."""
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


def _capital_summary() -> dict:
    raw = _capital_data()
    effective, unresolved = _capital_effective(raw)
    return {
        "file": CAPITAL_CONTROL_PATH.name,
        "present": CAPITAL_CONTROL_PATH.exists(),
        "rawObservations": int(len(raw)),
        "effectiveObservations": int(len(effective)),
        "unresolvedAmendmentTies": unresolved,
        "issuers": int(effective["issuer_id"].nunique()) if not effective.empty else 0,
        "legalHolders": int(effective["holder_legal_entity_id"].nunique()) if not effective.empty else 0,
        "investorFamilies": int(effective["investor_family_id"].replace("", pd.NA).nunique()) if not effective.empty and "investor_family_id" in effective else 0,
        "ultimateParents": int(effective["ultimate_parent_id"].replace("", pd.NA).nunique()) if not effective.empty and "ultimate_parent_id" in effective else 0,
    }


def _capital_compare(frame: pd.DataFrame, issuer_a: str, issuer_b: str, identity_level: str) -> dict:
    fields = {
        "legal_holder": "holder_legal_entity_id",
        "investor_family": "investor_family_id",
        "ultimate_parent": "ultimate_parent_id",
    }
    if identity_level not in fields:
        raise ValueError(f"unsupported identity_level: {identity_level}")
    effective, unresolved = _capital_effective(frame)
    field = fields[identity_level]
    if effective.empty or field not in effective:
        a: set[str] = set()
        b: set[str] = set()
    else:
        a = {str(v) for v in effective.loc[effective["issuer_id"] == issuer_a, field] if str(v).strip()}
        b = {str(v) for v in effective.loc[effective["issuer_id"] == issuer_b, field] if str(v).strip()}
    return {
        "intersection": sorted(a & b),
        "aOnly": sorted(a - b),
        "bOnly": sorted(b - a),
        "union": sorted(a | b),
        "symmetricDifference": sorted(a ^ b),
        "unresolvedAmendmentTies": unresolved,
    }


@app.get("/health")
def health():
    try:
        return {"status": "ok", "rows": {k: int(len(v)) for k, v in DATA.items()}}
    except Exception as exc:  # pragma: no cover
        raise HTTPException(500, str(exc))


@app.get("/contracts")
def contracts(
    municipality: str | None = None,
    agency: str | None = None,
    status: str | None = None,
    fiscal_year: int | None = None,
):
    names = _entity_name_map()
    munis = _muni_name_map()
    located = _located_in_map()
    out = []
    for _, r in DATA["contracts"].iterrows():
        awarding = names.get(r["awarding_entity_id"], r["awarding_entity_id"])
        contractor = names.get(r["contractor_entity_id"], r["contractor_entity_id"])
        muni_id = located.get(r["contractor_entity_id"]) or located.get(r["awarding_entity_id"])
        muni_name = munis.get(muni_id) if muni_id else None
        start = r.get("start_date") or ""
        fy = int(start[:4]) if start[:4].isdigit() else None
        row = {
            "contractId": r["contract_id"],
            "contractNumber": r.get("contract_number") or None,
            "awardingName": awarding or None,
            "contractorName": contractor or None,
            "municipality": muni_name,
            "serviceType": r.get("service_type") or None,
            "awardAmount": _num(r.get("award_amount")),
            "currency": r.get("currency") or None,
            "startDate": start or None,
            "endDate": r.get("end_date") or None,
            "status": r.get("status") or None,
            "confidence": _num(r.get("confidence")),
            "fiscalYear": fy,
        }
        if municipality and (row["municipality"] or "").lower() != municipality.lower():
            continue
        if agency and agency.lower() not in (row["awardingName"] or "").lower():
            continue
        if status and (row["status"] or "") != status:
            continue
        if fiscal_year and row["fiscalYear"] != fiscal_year:
            continue
        out.append(row)
    return out


@app.get("/entities")
def entities(type: str | None = None, q: str | None = None):
    df = DATA["entities"]
    out = []
    for _, r in df.iterrows():
        if type and r.get("entity_type") != type:
            continue
        if q and q.lower() not in (r.get("name") or "").lower():
            continue
        out.append(
            {
                "entityId": r["entity_id"],
                "name": r.get("name") or None,
                "entityType": r.get("entity_type") or None,
                "jurisdiction": r.get("jurisdiction") or None,
                "parentEntityId": r.get("parent_entity_id") or None,
                "confidence": _num(r.get("confidence")),
                "notes": r.get("notes") or None,
            }
        )
    return out


@app.get("/edges")
def edges(
    edge_type: str | None = None,
    source_id: str | None = None,
    view: str | None = None,
    issuer_id: str | None = None,
    q: str | None = None,
    identity_status: str | None = None,
    position_class: str | None = None,
    as_of_date: str | None = None,
    limit: int = 1000,
):
    """Return canonical relationship edges or the optional capital/control edge view."""
    if view == "capital_control":
        frame, _ = _capital_effective(_capital_data())
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
            cols = [
                c
                for c in (
                    "issuer_name",
                    "holder_reported_name_raw",
                    "investor_family_name",
                    "ultimate_parent_name",
                )
                if c in frame
            ]
            if cols:
                mask = pd.Series(False, index=frame.index)
                for col in cols:
                    mask |= frame[col].astype(str).str.contains(
                        q, case=False, na=False, regex=False
                    )
                frame = frame[mask]
        if "as_of_date" in frame:
            frame = frame.sort_values("as_of_date", ascending=False, kind="stable")
        return [_capital_record(row) for _, row in frame.head(max(1, min(limit, 5000))).iterrows()]

    names = _entity_name_map()
    munis = _muni_name_map()

    def label(node_type, node_id):
        if node_type == "Municipality":
            return munis.get(node_id, node_id)
        return names.get(node_id, node_id)

    out = []
    for _, r in DATA["edges"].iterrows():
        if edge_type and r.get("edge_type") != edge_type:
            continue
        if source_id and r.get("source_node_id") != source_id:
            continue
        out.append(
            {
                "edgeId": r["edge_id"],
                "sourceType": r.get("source_node_type"),
                "sourceId": r.get("source_node_id"),
                "sourceLabel": label(r.get("source_node_type"), r.get("source_node_id")),
                "edgeType": r.get("edge_type"),
                "targetType": r.get("target_node_type"),
                "targetId": r.get("target_node_id"),
                "targetLabel": label(r.get("target_node_type"), r.get("target_node_id")),
                "amount": _num(r.get("amount")),
                "confidence": _num(r.get("confidence")),
            }
        )
    return out


@app.get("/municipalities")
def municipalities():
    """Per-municipality contract count + null-safe summed award amount."""
    munis = _muni_name_map()
    located = _located_in_map()
    agg: dict[str, dict] = {}
    for _, r in DATA["contracts"].iterrows():
        muni_id = located.get(r["contractor_entity_id"]) or located.get(r["awarding_entity_id"])
        key = muni_id or "_unknown"
        a = agg.setdefault(
            key,
            {
                "municipalityId": muni_id,
                "name": munis.get(muni_id, "Unknown"),
                "contracts": 0,
                "total": 0.0,
                "hasAmount": False,
            },
        )
        a["contracts"] += 1
        amt = _num(r.get("award_amount"))
        if amt is not None:
            a["total"] += amt
            a["hasAmount"] = True
    rows = []
    for a in agg.values():
        rows.append({**a, "total": a["total"] if a["hasAmount"] else None})
    rows.sort(key=lambda x: x["contracts"], reverse=True)
    return rows


@app.get("/stats")
def stats():
    c = DATA["contracts"]
    by_status: dict[str, int] = {}
    by_service: dict[str, int] = {}
    amounts = 0
    for _, r in c.iterrows():
        by_status[r.get("status") or "unknown"] = by_status.get(r.get("status") or "unknown", 0) + 1
        st = r.get("service_type") or "unspecified"
        by_service[st] = by_service.get(st, 0) + 1
        if _num(r.get("award_amount")) is not None:
            amounts += 1
    ent_types: dict[str, int] = {}
    for _, r in DATA["entities"].iterrows():
        t = r.get("entity_type") or "unknown"
        ent_types[t] = ent_types.get(t, 0) + 1
    return {
        "contracts": int(len(c)),
        "entities": int(len(DATA["entities"])),
        "edges": int(len(DATA["edges"])),
        "municipalities": int(len(DATA["municipalities"])),
        "contractsWithAmount": amounts,
        "byStatus": by_status,
        "byServiceType": by_service,
        "byEntityType": ent_types,
        "capitalControl": _capital_summary(),
    }


# Optional analytical datasets are lazy-loaded by their routers so the core
# dashboard still boots when their staging artifacts are absent.
from server.backend.campaign_finance import router as campaign_finance_router  # noqa: E402
from server.backend.government_changes import router as government_changes_router  # noqa: E402

app.include_router(campaign_finance_router)
app.include_router(government_changes_router)
