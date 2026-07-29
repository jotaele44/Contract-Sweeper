"""Affiliation, transfer, temporal-correlation, and accounting extensions."""
from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Iterable

import pandas as pd

from .flow_graph import EDGE_COLUMNS, normalize_name

AFFILIATION_TYPES = {
    "P": "AUTHORIZED_COMMITTEE_OF",
    "A": "AUTHORIZED_COMMITTEE_OF",
    "J": "AFFILIATED_WITH",
}


def _id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(p or "").strip().upper() for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def build_affiliation_edges(candidates: pd.DataFrame, committees: pd.DataFrame) -> pd.DataFrame:
    """Build candidate authorization and committee-affiliation edges."""
    rows: list[dict] = []
    if candidates is not None and not candidates.empty:
        for i, row in enumerate(candidates.fillna("").to_dict("records")):
            candidate_id = str(row.get("candidate_id", ""))
            committee_id = str(row.get("principal_campaign_committee_id", ""))
            if not candidate_id or not committee_id:
                continue
            source = f"fec_committee:{committee_id}"
            target = f"fec_candidate:{candidate_id}"
            record_id = str(row.get("record_id") or candidate_id)
            rows.append(_edge(source, target, "AUTHORIZED_COMMITTEE_OF", "fec_candidates", record_id, row))
    if committees is not None and not committees.empty:
        for row in committees.fillna("").to_dict("records"):
            source_id = str(row.get("committee_id", ""))
            target_id = str(row.get("affiliated_committee_id", ""))
            if not source_id or not target_id or source_id == target_id:
                continue
            record_id = str(row.get("record_id") or f"{source_id}:{target_id}")
            rows.append(_edge(f"fec_committee:{source_id}", f"fec_committee:{target_id}", "AFFILIATED_WITH", "fec_committees", record_id, row, confidence=0.95))
    return _dedup(rows)


def build_transfer_edges(disbursements: pd.DataFrame, committee_ids: Iterable[str]) -> pd.DataFrame:
    """Classify Schedule B committee-to-committee transfers using recipient IDs."""
    if disbursements is None or disbursements.empty:
        return pd.DataFrame(columns=EDGE_COLUMNS)
    known = {str(value) for value in committee_ids if str(value)}
    rows: list[dict] = []
    for i, row in enumerate(disbursements.fillna("").to_dict("records")):
        source_id = str(row.get("committee_id", ""))
        target_id = str(row.get("recipient_committee_id") or row.get("recipient_id") or "")
        if not source_id or not target_id or target_id not in known:
            continue
        record_id = str(row.get("sub_id") or row.get("transaction_id") or i)
        rows.append(_edge(f"fec_committee:{source_id}", f"fec_committee:{target_id}", "TRANSFERRED_TO", "fec_schedule_b", record_id, row, "disbursement_amount", "disbursement_date"))
    return _dedup(rows)


def correlate_temporal_activity(
    political_edges: pd.DataFrame,
    entities: pd.DataFrame,
    awards: pd.DataFrame | None,
    lobbying: pd.DataFrame | None,
    window_days: int = 730,
) -> pd.DataFrame:
    """Produce conservative name-and-time correlations, not causal claims."""
    columns = ["political_entity_id", "external_entity_id", "external_dataset", "relationship_type", "match_method", "confidence", "evidence"]
    if political_edges.empty or entities.empty:
        return pd.DataFrame(columns=columns)
    names = {str(r.entity_id): normalize_name(r.canonical_name) for r in entities[["entity_id", "canonical_name"]].itertuples(index=False)}
    activity = political_edges.copy()
    activity["transaction_date"] = pd.to_datetime(activity["transaction_date"], errors="coerce", utc=True)
    result: list[dict] = []
    specs = [
        ("contracts", awards, ("awardee_id", "recipient_id", "entity_id"), ("awardee_name", "recipient_name", "canonical_name"), ("award_date", "start_date", "action_date"), "POLITICAL_ACTIVITY_PRECEDES_AWARD"),
        ("lobbying", lobbying, ("client_id", "entity_id", "registrant_id"), ("client_name", "name", "canonical_name"), ("filing_date", "period_end", "date"), "POLITICAL_ACTIVITY_NEAR_LOBBYING"),
    ]
    for dataset, frame, id_candidates, name_candidates, date_candidates, relation in specs:
        if frame is None or frame.empty:
            continue
        id_col = next((c for c in id_candidates if c in frame), None)
        name_col = next((c for c in name_candidates if c in frame), None)
        date_col = next((c for c in date_candidates if c in frame), None)
        if not id_col or not name_col:
            continue
        ext = frame.copy()
        ext["_name"] = ext[name_col].map(normalize_name)
        ext["_date"] = pd.to_datetime(ext[date_col], errors="coerce", utc=True) if date_col else pd.NaT
        for entity_id, canonical in names.items():
            if not canonical:
                continue
            matched = ext.loc[ext["_name"] == canonical]
            if matched.empty:
                continue
            edge_dates = activity.loc[(activity["source_entity_id"] == entity_id) | (activity["target_entity_id"] == entity_id), "transaction_date"].dropna()
            for row in matched.to_dict("records"):
                external_date = row.get("_date")
                temporal = False
                days = None
                if pd.notna(external_date) and not edge_dates.empty:
                    deltas = [(external_date - d).days for d in edge_dates if external_date >= d]
                    if deltas:
                        days = min(deltas)
                        temporal = days <= window_days
                confidence = 0.90 if temporal else 0.72
                evidence = f"exact_normalized_name={canonical}; temporal_window_days={days if days is not None else 'unavailable'}"
                result.append({"political_entity_id": entity_id, "external_entity_id": f"{dataset}:{row[id_col]}", "external_dataset": dataset, "relationship_type": relation, "match_method": "exact_normalized_name+temporal" if temporal else "exact_normalized_name", "confidence": confidence, "evidence": evidence})
    return pd.DataFrame(result, columns=columns).drop_duplicates() if result else pd.DataFrame(columns=columns)


def materialization_accounting(inputs: dict[str, pd.DataFrame], outputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Record nonzero or explicitly accounted-zero row counts."""
    rows = []
    for kind, frames in (("input", inputs), ("output", outputs)):
        for name, frame in frames.items():
            count = 0 if frame is None else len(frame)
            rows.append({"kind": kind, "dataset": name, "row_count": count, "status": "nonzero" if count else "accounted_zero", "reason": "materialized" if count else "source absent, filtered empty, or no qualifying records"})
    return pd.DataFrame(rows)


def _edge(source: str, target: str, edge_type: str, source_id: str, record_id: str, row: dict, amount_key: str = "", date_key: str = "", confidence: float = 1.0) -> dict:
    return {"edge_id": _id("pfe", source_id, record_id, source, target, edge_type), "source_entity_id": source, "target_entity_id": target, "edge_type": edge_type, "amount": row.get(amount_key, "") if amount_key else "", "transaction_date": row.get(date_key, "") if date_key else "", "cycle": row.get("cycle", ""), "support_oppose": "", "source_id": source_id, "source_record_id": record_id, "confidence": confidence, "provenance": f"{source_id}:{record_id}"}


def _dedup(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=EDGE_COLUMNS).drop_duplicates("edge_id") if rows else pd.DataFrame(columns=EDGE_COLUMNS)
