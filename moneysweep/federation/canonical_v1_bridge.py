"""Bridge canonical_v1 -> the federation export model (WS-Q).

Maps the committed ``data/canonical_v1`` node/edge/evidence tables into the three
federation JSONL streams that validate against the stable schemas in
``schemas/moneysweep_{source,entity,relationship}.schema.json``:

* **sources.jsonl**       — one row per canonical_v1 evidence row (``src_<32hex>``).
* **entities.jsonl**      — canonical_v1 ``entities`` + ``people`` PLUS the promoted
                            non-entity nodes (municipalities, debt instruments,
                            projects, properties, funding sources, contracts), each
                            ``ent_<32hex>`` carrying its canonical_v1 id in
                            ``external_ids`` (PR B / WS-Q).
* **relationships.jsonl** — canonical_v1 ``edges`` whose both endpoints resolve to a
                            federation entity (``rel_<32hex>``).

PR A federated only Person/Entity↔Person/Entity edges; PR B promotes the remaining
node types to entities so **every** edge federates (``edges_federated_pct == 100``,
``not_yet_federated == []``). Non-entity node types are projected as entities with a
descriptive ``entity_type`` (municipality / debt_instrument / project / property /
funding_source / contract). Every row carries a ``lineage`` object and
``synthetic=false``. Stdlib only; deterministic and idempotent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneysweep.runtime.canonical_ids import (
    fed_entity_id,
    fed_relationship_id,
    fed_source_id,
)
from moneysweep.validation.canonical_v1_schema import load_all_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCER = "moneysweep/federation/canonical_v1_bridge.py"
PHASE = "CANONICAL_V1_FEDERATION_BRIDGE"

# canonical_v1 edge endpoint node types that become federation entities.
# PR B (WS-Q): non-entity nodes (municipalities, debt instruments, projects,
# properties, funding sources, contracts) are promoted to federation entities so
# the edges touching them federate as entity->entity relationships instead of
# being reported as not_yet_federated.
_ENTITY_NODE_TYPES = {
    "Person",
    "Entity",
    "Municipality",
    "DebtInstrument",
    "Project",
    "Property",
    "FundingSource",
    "Contract",
}

# canonical_v1 entity_type -> federation entity_type vocabulary.
_ENTITY_TYPE_MAP = {
    "agency": "funding_agency",
    "utility": "recipient",
    "firm": "recipient",
    "fund": "recipient",
    "nonprofit": "recipient",
    "other": "recipient",
}

# PR B: additional canonical_v1 node tables promoted to federation entities.
# (table_key, id_column, name_column | None, federation_entity_type, source_csv)
_NODE_TABLES = [
    (
        "municipalities",
        "municipality_id",
        "name",
        "municipality",
        "data/canonical_v1/municipalities.csv",
    ),
    ("projects", "project_id", "project_name", "project", "data/canonical_v1/projects.csv"),
    ("properties", "property_id", "property_name", "property", "data/canonical_v1/properties.csv"),
    (
        "funding_sources",
        "funding_source_id",
        "program",
        "funding_source",
        "data/canonical_v1/funding_sources.csv",
    ),
    ("contracts", "contract_id", "contract_number", "contract", "data/canonical_v1/contracts.csv"),
    (
        "debt_instruments",
        "debt_id",
        None,
        "debt_instrument",
        "data/canonical_v1/debt_instruments.csv",
    ),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lineage(source_csv: str) -> dict[str, Any]:
    return {
        "producer_script": PRODUCER,
        "producer_phase": PHASE,
        "source_inputs": [source_csv],
        "extraction_method": "canonical_v1_bridge",
    }


# How much to trust a municipality that came from a node's municipality_id. It
# is a real curated attribution, not a guess — but it names an administrative
# unit, not a surveyed point, and a spatial producer that later resolves actual
# geometry should outrank it.
_MUNICIPALITY_ATTRIBUTION_CONFIDENCE = 0.7

# Extents whose municipality describes the administrative seat rather than where
# the asset physically is. An island-wide grid concession is not "in" San Juan
# because its operator is headquartered there, so the municipality is withheld
# from the federated row rather than shipped as if it were a location.
_NON_SITE_EXTENTS = {"islandwide", "corridor"}


def _node_location(
    row: dict[str, Any], source_csv: str, muni_names: dict[str, str]
) -> dict[str, Any] | None:
    """Municipality-only location for a promoted node, or None.

    Coordinates are deliberately not produced here. moneysweep-pr resolves
    municipalities but carries no centroids, and synthesising one would both
    invent precision the source never had and duplicate the geometry authority
    that belongs to the spatial producer. Consumers that only need a
    municipality (thehub-pr's correlate_observations) can already join on this;
    consumers that need a point wait for spiderweb-pr to supply it.
    """
    muni_id = (row.get("municipality_id") or "").strip()
    if not muni_id:
        return None
    name = muni_names.get(muni_id)
    if not name:
        return None
    if (row.get("spatial_extent") or "").strip() in _NON_SITE_EXTENTS:
        return None
    return {
        "municipality": name,
        "attribution_source": f"{source_csv}#municipality_id",
        "attribution_confidence": _MUNICIPALITY_ATTRIBUTION_CONFIDENCE,
    }


def _norm_conf(value: str | None) -> float:
    if value is None:
        return 0.0
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def build_streams(root: Path | None = None, now: str | None = None) -> dict[str, Any]:
    """Return the three federation streams + a coverage report (no writing).

    ``now`` stamps every row's ``created_at``/``extracted_at``. It defaults to the
    current UTC time (``_now()``); pass a fixed ISO timestamp for a deterministic,
    byte-reproducible package (used by ``scripts/federation_export.py``)."""
    root = root or REPO_ROOT
    tables = load_all_tables(root)
    now = now or _now()

    # --- sources from evidence ---
    sources: list[dict[str, Any]] = []
    evidence_to_src: dict[str, str] = {}
    for ev in tables.get("evidence", []):
        ceid = (ev.get("evidence_id") or "").strip()
        if not ceid:
            continue
        sid = fed_source_id(ceid)
        evidence_to_src[ceid] = sid
        sources.append(
            {
                "source_id": sid,
                "source_type": (ev.get("source_type") or "other").strip() or "other",
                "source_name": (ev.get("source_name") or "").strip(),
                "source_ref": ceid,
                "confidence": _norm_conf(ev.get("confidence")),
                "lineage": _lineage("data/canonical_v1/evidence.csv"),
                "synthetic": False,
                "created_at": now,
                "extracted_at": now,
            }
        )

    # --- entities from canonical_v1 entities + people ---
    entities: list[dict[str, Any]] = []
    node_to_ent: dict[str, str] = {}

    def _emit_entity(
        cid: str,
        name: str,
        normalized: str,
        etype: str,
        jurisdiction: str,
        ev_id: str,
        conf: str | None,
        source_csv: str,
        location: dict[str, Any] | None = None,
    ) -> None:
        eid = fed_entity_id(cid)
        node_to_ent[cid] = eid
        row = {
            "entity_id": eid,
            "source_id": evidence_to_src.get(ev_id, fed_source_id(ev_id)),
            "name": name,
            "normalized_name": normalized or name.upper(),
            "entity_type": etype,
            "jurisdiction": jurisdiction or "PR",
            "external_ids": {"canonical_v1_id": cid},
            "confidence": _norm_conf(conf),
            "lineage": _lineage(source_csv),
            "synthetic": False,
            "created_at": now,
        }
        row["extracted_at"] = now
        if location:
            row["location"] = location
        entities.append(row)

    for ent in tables.get("entities", []):
        cid = (ent.get("entity_id") or "").strip()
        if not cid:
            continue
        _emit_entity(
            cid,
            (ent.get("name") or "").strip(),
            (ent.get("normalized_name") or "").strip(),
            _ENTITY_TYPE_MAP.get((ent.get("entity_type") or "").strip(), "recipient"),
            (ent.get("jurisdiction") or "").strip(),
            (ent.get("evidence_id") or "").strip(),
            ent.get("confidence"),
            "data/canonical_v1/entities.csv",
        )
    for per in tables.get("people", []):
        cid = (per.get("person_id") or "").strip()
        if not cid:
            continue
        _emit_entity(
            cid,
            (per.get("full_name") or "").strip(),
            (per.get("normalized_name") or "").strip(),
            "person",
            (per.get("jurisdiction") or "").strip(),
            (per.get("evidence_id") or "").strip(),
            per.get("confidence"),
            "data/canonical_v1/people.csv",
        )

    # --- PR B: promote non-entity canonical_v1 nodes to federation entities ---
    # municipality_id -> display name, so a node that names its municipality can
    # carry it across the federation boundary instead of dropping it.
    muni_names = {
        (m.get("municipality_id") or "").strip(): (m.get("name") or "").strip()
        for m in tables.get("municipalities", [])
        if (m.get("municipality_id") or "").strip()
    }

    for table_key, id_col, name_col, etype, source_csv in _NODE_TABLES:
        for row in tables.get(table_key, []):
            cid = (row.get(id_col) or "").strip()
            if not cid:
                continue
            if name_col:
                name = (row.get(name_col) or "").strip() or cid
            else:  # debt_instruments has no single name column — compose a label
                name = (
                    " ".join(
                        p
                        for p in (
                            (row.get("debt_class") or "").strip(),
                            (row.get("series") or "").strip(),
                            (row.get("issue_year") or "").strip(),
                        )
                        if p
                    )
                    or cid
                )
            _emit_entity(
                cid,
                name,
                "",
                etype,
                (row.get("jurisdiction") or "").strip(),
                (row.get("evidence_id") or "").strip(),
                row.get("confidence"),
                source_csv,
                location=_node_location(row, source_csv, muni_names),
            )

    # --- relationships from edges with entity endpoints ---
    relationships: list[dict[str, Any]] = []
    not_yet: list[dict[str, str]] = []
    for e in tables.get("edges", []):
        s_type = (e.get("source_node_type") or "").strip()
        t_type = (e.get("target_node_type") or "").strip()
        sid = (e.get("source_node_id") or "").strip()
        tid = (e.get("target_node_id") or "").strip()
        etype = (e.get("edge_type") or "").strip()
        ceid = (e.get("evidence_id") or "").strip()
        if (
            s_type in _ENTITY_NODE_TYPES
            and t_type in _ENTITY_NODE_TYPES
            and sid in node_to_ent
            and tid in node_to_ent
        ):
            relationships.append(
                {
                    "relationship_id": fed_relationship_id(sid, etype, tid),
                    "source_id": evidence_to_src.get(ceid, fed_source_id(ceid)),
                    "source_entity_id": node_to_ent[sid],
                    "target_entity_id": node_to_ent[tid],
                    "relationship_type": etype,
                    "evidence_source_id": evidence_to_src.get(ceid, fed_source_id(ceid)),
                    "confidence": _norm_conf(e.get("confidence")),
                    "lineage": _lineage("data/canonical_v1/edges.csv"),
                    "synthetic": False,
                    "created_at": now,
                    "extracted_at": now,
                }
            )
        else:
            not_yet.append(
                {
                    "edge_id": (e.get("edge_id") or "").strip(),
                    "edge_type": etype,
                    "reason": f"non-entity endpoint ({s_type}->{t_type})",
                }
            )

    return {
        "sources": sources,
        "entities": entities,
        "relationships": relationships,
        "not_yet_federated": not_yet,
    }
