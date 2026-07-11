"""Bridge Centinelas pre-official candidates into the Hub ``funding_awards`` stream.

``scripts/ingest_centinelas_signals.py`` writes geo-attributed pre-official
located-finance candidates to ``exports/centinelas_intake/funding_awards.jsonl``.
This maps each candidate into the federation funding_award contract
(``schemas/moneysweep_funding_award.schema.json`` — byte-identical to
thehub-pr's ``federation_funding_award``) plus the minimal supporting recipient /
funding-agency ``entities`` and a ``sources`` row, so the Hub's
aggregate → ingest lands them in the ``FundingAwards`` collection.

It is an **optional** stream: when the candidates file is absent (the normal
committed state — the file is gitignored), nothing is emitted and the committed
3-stream canonical package is unchanged. In the event-driven flow, the
``centinelas-intake`` workflow produces the candidates first, so the export then
carries the ``funding_awards`` stream through to the Hub.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneysweep.runtime.canonical_ids import fed_award_id, fed_entity_id, fed_source_id

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATES_REL = "exports/centinelas_intake/funding_awards.jsonl"
PRODUCER = "moneysweep/federation/centinelas_awards_bridge.py"
PHASE = "CENTINELAS_PRE_OFFICIAL_BRIDGE"
SOURCE_SEED = "centinelas-pr"
AWARD_TYPE = "pre_official_signal"

# Candidate location.attribution_confidence is a label; the funding_award schema
# wants a number in [0, 1].
_ATTR_CONF = {"exact_name": 0.95, "fuzzy_name": 0.7, "keyword": 0.5, "none": 0.0}
_DEFAULT_CONF = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num_conf(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return _ATTR_CONF.get(str(value or "").strip().lower(), _DEFAULT_CONF)


def _fiscal_year(award_date: str) -> int:
    try:
        return int(str(award_date)[:4])
    except (TypeError, ValueError):
        return 0


def _lineage(source_inputs: list[str] | None) -> dict[str, Any]:
    return {
        "producer_script": PRODUCER,
        "producer_phase": PHASE,
        "source_inputs": source_inputs or [CANDIDATES_REL],
        "extraction_method": "centinelas_pre_official_bridge",
    }


def _map_location(loc: Any) -> dict[str, Any] | None:
    if not isinstance(loc, dict):
        return None
    out: dict[str, Any] = {}
    for key in ("country", "municipality", "municipality_code", "municipality_name", "county_fips"):
        val = loc.get(key)
        if val:
            out[key] = str(val)
    if loc.get("attribution_source"):
        out["attribution_source"] = str(loc["attribution_source"])
    if loc.get("attribution_confidence") is not None:
        out["attribution_confidence"] = _num_conf(loc.get("attribution_confidence"))
    return out or None


def _load_candidates(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def build_centinelas_streams(root: Path | None = None, now: str | None = None) -> dict[str, list]:
    """Map ``exports/centinelas_intake/funding_awards.jsonl`` into federation
    ``sources`` / ``entities`` / ``funding_awards`` rows. Empty when absent."""
    root = Path(root or REPO_ROOT)
    now = now or _now()
    candidates = _load_candidates(root / CANDIDATES_REL)

    sources: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    awards: list[dict[str, Any]] = []
    if not candidates:
        return {"sources": sources, "entities": entities, "funding_awards": awards}

    src_id = fed_source_id(SOURCE_SEED)
    sources.append(
        {
            "source_id": src_id,
            "source_type": "other",
            "source_name": "Centinelas pre-official signals",
            "source_ref": SOURCE_SEED,
            "confidence": _DEFAULT_CONF,
            "lineage": _lineage([CANDIDATES_REL]),
            "synthetic": False,
            "created_at": now,
            "extracted_at": now,
        }
    )

    seen_ent: set[str] = set()
    for cand in candidates:
        item_id = str(cand.get("centinelas_item_id") or cand.get("award_id") or "")
        recipient_name = str(cand.get("recipient_entity_id") or "").strip()
        agency_name = str(cand.get("funding_agency_entity_id") or "").strip()
        recipient_eid = fed_entity_id("centinelas|recipient|" + recipient_name)
        agency_eid = fed_entity_id("centinelas|agency|" + agency_name)
        conf = (
            _num_conf(cand.get("confidence"))
            if cand.get("confidence") is not None
            else _DEFAULT_CONF
        )

        for eid, name, etype in (
            (recipient_eid, recipient_name, "recipient"),
            (agency_eid, agency_name, "funding_agency"),
        ):
            # Always emit the referenced entity so the award never carries a dangling
            # ent_ id. Signals may omit the agency/recipient name (intake allows it),
            # so synthesize a placeholder name in that case.
            if eid not in seen_ent:
                seen_ent.add(eid)
                display_name = name or f"Unknown {etype}"
                entities.append(
                    {
                        "entity_id": eid,
                        "source_id": src_id,
                        "name": display_name,
                        "normalized_name": display_name.upper(),
                        "entity_type": etype,
                        "jurisdiction": "PR",
                        "external_ids": {"centinelas_item_id": item_id},
                        "confidence": conf,
                        "lineage": _lineage([CANDIDATES_REL]),
                        "synthetic": False,
                        "created_at": now,
                        "extracted_at": now,
                    }
                )

        award_date = str(cand.get("award_date") or now[:10])
        cand_inputs = (cand.get("lineage") or {}).get("source_inputs")
        award = {
            "award_id": fed_award_id(str(cand.get("award_id") or item_id)),
            "source_id": src_id,
            "recipient_entity_id": recipient_eid,
            "funding_agency_entity_id": agency_eid,
            "amount": float(cand.get("amount") or 0.0),
            "currency": (str(cand.get("currency") or "USD")[:3] or "USD").upper(),
            "fiscal_year": _fiscal_year(award_date),
            "award_type": AWARD_TYPE,
            "award_date": award_date,
            "confidence": conf,
            "lineage": _lineage(cand_inputs if isinstance(cand_inputs, list) else None),
            "synthetic": bool(cand.get("synthetic", False)),
            "created_at": now,
            "extracted_at": now,
        }
        location = _map_location(cand.get("location"))
        if location:
            award["location"] = location
        awards.append(award)

    return {"sources": sources, "entities": entities, "funding_awards": awards}


COMMITTED_PACKAGE_REL = "data/exports/canonical_v1_federation"


def _dedup_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Keep the first row per ``key`` (new rows precede prior ones, so new wins)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        k = row.get(key)
        if k in seen:
            continue
        seen.add(k)
        out.append(row)
    return out


def _load_prior_centinelas(committed_dir: Path, src_id: str) -> dict[str, list]:
    """Load the Centinelas-origin rows already committed to the federation package
    (identified by source_id) so earlier candidates persist across rebuilds."""

    def _rows(name: str) -> list[dict[str, Any]]:
        rows = _load_candidates(committed_dir / name)
        return [r for r in rows if r.get("source_id") == src_id]

    return {
        "sources": _rows("sources.jsonl"),
        "entities": _rows("entities.jsonl"),
        "funding_awards": _rows("funding_awards.jsonl"),
    }


def merge_centinelas_awards(
    streams: dict[str, Any],
    root: Path | None = None,
    now: str | None = None,
    committed_dir: Path | None = None,
) -> int:
    """Fold Centinelas funding_awards (+ supporting entities/source) into ``streams``.

    Accumulates: the newly-ingested candidate is unioned with the Centinelas rows
    already committed to the federation package (``committed_dir``, default
    ``data/exports/canonical_v1_federation``), deduped by id (new wins). This keeps
    earlier candidates in the committed snapshot when a later signal rebuilds the
    package. Returns the total funding_award count (0 when there are none, so the
    caller keeps ``funding_awards`` out of the package entirely)."""
    root = Path(root or REPO_ROOT)
    built = build_centinelas_streams(root, now)
    src_id = fed_source_id(SOURCE_SEED)
    prior = _load_prior_centinelas(
        Path(committed_dir) if committed_dir else root / COMMITTED_PACKAGE_REL, src_id
    )

    awards = _dedup_by(built["funding_awards"] + prior["funding_awards"], "award_id")
    if not awards:
        return 0
    cent_sources = _dedup_by(built["sources"] + prior["sources"], "source_id")
    cent_entities = _dedup_by(built["entities"] + prior["entities"], "entity_id")

    existing_src = {s.get("source_id") for s in streams.get("sources", [])}
    existing_ent = {e.get("entity_id") for e in streams.get("entities", [])}
    streams.setdefault("sources", []).extend(
        s for s in cent_sources if s["source_id"] not in existing_src
    )
    streams.setdefault("entities", []).extend(
        e for e in cent_entities if e["entity_id"] not in existing_ent
    )
    streams["funding_awards"] = streams.get("funding_awards", []) + awards
    return len(awards)
