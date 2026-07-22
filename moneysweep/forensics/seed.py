from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .adapters import (
    ADAPTER_ENDPOINTS,
    ContractorListingAdapter,
    KeywordEvidenceAdapter,
    SamAdapter,
    SimpleEndpointAdapter,
    UsaSpendingRecipientAdapter,
)
from .core import ForensicsLedger, canonical_hash, entity_id, utcnow


def jacobs_subject() -> dict[str, Any]:
    eid = entity_id("DE", "JACOBS SOLUTIONS INC")
    return {
        "entity_id": eid,
        "legal_name": "JACOBS SOLUTIONS INC",
        "aliases": [
            "JACOBS",
            "JACOBS SOLUTIONS",
            "JACOBS ENGINEERING GROUP",
            "JACOBS ENGINEERING",
            "JACOBS TECHNOLOGY",
            "JACOBS FACILITIES",
            "JACOBS SVERDRUP",
            "SVERDRUP",
            "CH2M HILL",
            "CH2M",
            "HALCROW",
            "SINCLAIR KNIGHT MERZ",
            "LEIGHFISHER",
            "KLINGSTUBBINS",
            "JACOBS PUERTO RICO",
            "JACOBS SOLUTIONS PUERTO RICO",
            "AMENTUM",
        ],
    }


def seed_cluster(ledger: ForensicsLedger, root: Path) -> dict[str, Any]:
    now = utcnow()
    subject = jacobs_subject()
    root_id = subject["entity_id"]
    names = [
        ("JACOBS SOLUTIONS INC", "parent", "DE"),
        ("JACOBS ENGINEERING GROUP INC", "subsidiary", "DE"),
        ("JACOBS ENGINEERING INC", "subsidiary", "CA"),
        ("JACOBS PUERTO RICO INC", "subsidiary", "PR"),
        ("JACOBS SOLUTIONS PUERTO RICO INC", "subsidiary", "PR"),
        ("CH2M HILL COMPANIES LTD", "acquired_lineage", "DE"),
        ("CH2M HILL INC", "subsidiary", "OR"),
        ("HALCROW INC", "acquired_lineage", "DE"),
        ("SINCLAIR KNIGHT MERZ", "acquired_lineage", "AU"),
        ("SVERDRUP", "predecessor", "US"),
        ("JACOBS TECHNOLOGY INC", "historical_operating_entity", "TN"),
        ("JACOBS FACILITIES INC", "historical_operating_entity", "MO"),
        ("LEIGHFISHER INC", "subsidiary", "CA"),
        ("KLINGSTUBBINS INC", "subsidiary", "PA"),
        ("AMENTUM HOLDINGS INC", "successor_branch", "DE"),
    ]
    entities = []
    ids = {}
    for name, etype, juris in names:
        eid = entity_id(juris, name)
        ids[name] = eid
        entities.append(
            {
                "entity_id": eid,
                "legal_name": name,
                "normalized_name": name,
                "entity_type": etype,
                "jurisdiction": juris,
                "identity_status": "CONFIRMED" if name == "JACOBS SOLUTIONS INC" else "PROVISIONAL",
                "formed_date": None,
                "dissolved_date": None,
                "valid_from": None,
                "valid_to": None,
                "observed_at": now,
                "superseded_at": None,
                "source_id": "seed_jacobs_cluster",
                "source_run_id": "seed_jacobs_v1",
                "evidence_tier": "T4" if name != "JACOBS SOLUTIONS INC" else "T1",
                "confidence": 0.7,
                "review_status": "UNREVIEWED",
                "supersedes_record_id": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    ledger.upsert("entities", entities, ["entity_id"])
    aliases = []
    for alias in subject["aliases"]:
        aliases.append(
            {
                "alias_id": canonical_hash(root_id, alias, prefix="alias_"),
                "entity_id": root_id,
                "alias": alias,
                "normalized_alias": alias,
                "alias_type": "SEARCH_ALIAS",
                "valid_from": None,
                "valid_to": None,
                "observed_at": now,
                "superseded_at": None,
                "source_id": "seed_jacobs_cluster",
                "source_run_id": "seed_jacobs_v1",
                "evidence_tier": "T4",
                "confidence": 0.6,
                "review_status": "UNREVIEWED",
                "supersedes_record_id": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    ledger.upsert("entity_aliases", aliases, ["alias_id"])
    rels = []
    for name, eid in ids.items():
        if eid == root_id:
            continue
        rtype = "SUCCESSOR_OF" if name == "AMENTUM HOLDINGS INC" else "CORPORATE_FAMILY_MEMBER"
        rels.append(
            {
                "relationship_id": canonical_hash(root_id, eid, rtype, prefix="rel_"),
                "parent_entity_id": root_id,
                "child_entity_id": eid,
                "relationship_type": rtype,
                "ownership_percent": None,
                "transaction_type": "SEPARATION" if name == "AMENTUM HOLDINGS INC" else None,
                "valid_from": None,
                "valid_to": None,
                "observed_at": now,
                "superseded_at": None,
                "source_id": "seed_jacobs_cluster",
                "source_run_id": "seed_jacobs_v1",
                "evidence_tier": "T4",
                "confidence": 0.6,
                "review_status": "UNREVIEWED",
                "supersedes_record_id": None,
                "created_at": now,
                "updated_at": now,
            }
        )
    ledger.upsert("entity_relationships", rels, ["relationship_id"])
    return subject


def build_adapters(root: Path) -> list[Any]:
    data = Path("/mnt/data")
    adapters: list[Any] = [UsaSpendingRecipientAdapter(), SamAdapter()]
    for sid, (family, endpoint) in ADAPTER_ENDPOINTS.items():
        adapters.append(SimpleEndpointAdapter(sid, family, endpoint))
    local_specs = [
        (
            "dcaa_2007",
            "federal_contractor_registry",
            data / "FY_2007_Active_Contractor_Listing_Final.pdf",
            ContractorListingAdapter,
        ),
        (
            "dcaa_2012",
            "federal_contractor_registry",
            data / "FY_2012_All_Active_Contractor_Listing.pdf",
            ContractorListingAdapter,
        ),
        (
            "dcaa_2013",
            "federal_contractor_registry",
            data / "FY_2013_All_Active_Contractor_Listing.pdf",
            ContractorListingAdapter,
        ),
        (
            "subcontracting_directory",
            "subcontracting",
            data / "subcontractingdirectory.772857981.pdf",
            KeywordEvidenceAdapter,
        ),
        (
            "act_transition",
            "territorial_contracts",
            data / "Contratos Vigentes ACT.pdf",
            KeywordEvidenceAdapter,
        ),
        (
            "transition_2024",
            "territorial_contracts",
            next(
                data.glob("Informe Contratos Vigentes al Momento de Transici*n.pdf"),
                data / "Informe Contratos Vigentes al Momento de Transición.pdf",
            ),
            KeywordEvidenceAdapter,
        ),
        (
            "prasa_completed_projects",
            "territorial_projects",
            data / "completed_projects_AAA.pdf",
            KeywordEvidenceAdapter,
        ),
        (
            "prasa_cer_2024",
            "territorial_infrastructure",
            data / "FY2024 CER_Final.pdf",
            KeywordEvidenceAdapter,
        ),
        (
            "lobbying_pr_snapshot",
            "influence",
            data / "Registro de cabilderos Abril 18 2026.pdf",
            KeywordEvidenceAdapter,
        ),
        ("lda_federal_snapshot", "influence", data / "Registrants.pdf", KeywordEvidenceAdapter),
    ]
    for sid, fam, path, cls in local_specs:
        adapters.append(cls(sid, fam, path))
    return adapters


def populate(root: Path) -> dict[str, Any]:
    ledger = ForensicsLedger(
        root / "data" / "forensics" / "contract_forensics.duckdb", root / "migrations" / "forensics"
    )
    ledger.migrate()
    subject = seed_cluster(ledger, root)
    results = []
    for adapter in build_adapters(root):
        res = adapter.execute(ledger, subject["entity_id"], subject)
        results.append(
            {
                "source_id": adapter.source_id,
                "status": res.status,
                "records": len(res.records),
                "evidence": len(res.evidence),
                "failure_type": res.failure_type,
            }
        )
        # Convert contractor listing identifiers into canonical rows.
        for rec in res.records:
            name = rec.get("name")
            if not name:
                continue
            matched_id = entity_id("US", name)
            now = utcnow()
            ledger.upsert(
                "entities",
                [
                    {
                        "entity_id": matched_id,
                        "legal_name": name,
                        "normalized_name": name.upper(),
                        "entity_type": "historical_contractor_identity",
                        "jurisdiction": "US",
                        "identity_status": "PROVISIONAL",
                        "formed_date": None,
                        "dissolved_date": None,
                        "valid_from": None,
                        "valid_to": None,
                        "observed_at": now,
                        "superseded_at": None,
                        "source_id": adapter.source_id,
                        "source_run_id": None,
                        "evidence_tier": "T1",
                        "confidence": 0.8,
                        "review_status": "MACHINE_VALIDATED",
                        "supersedes_record_id": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                ],
                ["entity_id"],
            )
            identifiers = []
            for itype in ("cage", "duns"):
                val = rec.get(itype)
                if val:
                    identifiers.append(
                        {
                            "identifier_id": canonical_hash(matched_id, itype, val, prefix="id_"),
                            "entity_id": matched_id,
                            "identifier_type": itype.upper(),
                            "identifier_value": val,
                            "jurisdiction": "US",
                            "valid_from": None,
                            "valid_to": None,
                            "observed_at": now,
                            "superseded_at": None,
                            "source_id": adapter.source_id,
                            "source_run_id": None,
                            "evidence_tier": "T1",
                            "confidence": 0.9,
                            "review_status": "MACHINE_VALIDATED",
                            "supersedes_record_id": None,
                            "created_at": now,
                            "updated_at": now,
                        }
                    )
            if identifiers:
                ledger.upsert("entity_identifiers", identifiers, ["identifier_id"])
    coverage_domains: dict[str, list[dict[str, Any]]] = {
        "entity_graph": [
            {
                "weight": 0.8,
                "confidence": 0.75,
                "gap_status": None,
                "next_action": "verify SEC ownership edges",
            }
        ],
        "identifiers": [
            {
                "weight": 0.75,
                "confidence": 0.85,
                "gap_status": None,
                "next_action": "resolve UEIs and current CAGE records",
            }
        ],
        "puerto_rico_contracts": [
            {
                "weight": 0.2,
                "confidence": 0.5,
                "gap_status": "SOURCE_INACCESSIBLE",
                "next_action": "run OCPR bulk export adapter in network-enabled runtime",
            }
        ],
        "federal_awards": [
            {
                "weight": 0.15,
                "confidence": 0.4,
                "gap_status": "SOURCE_INACCESSIBLE",
                "next_action": "run USAspending award transaction pull",
            }
        ],
        "subawards": [
            {
                "weight": 0.05,
                "confidence": 0.3,
                "gap_status": "SOURCE_INACCESSIBLE",
                "next_action": "pull USAspending and FSRS subawards",
            }
        ],
        "projects": [
            {
                "weight": 0.25,
                "confidence": 0.6,
                "gap_status": None,
                "next_action": "bridge Jacobs mentions to PRASA project IDs",
            }
        ],
        "lobbying": [
            {
                "weight": 0.2,
                "confidence": 0.5,
                "gap_status": None,
                "next_action": "resolve exact client aliases in PR and LDA registries",
            }
        ],
        "successor_mapping": [
            {
                "weight": 0.65,
                "confidence": 0.7,
                "gap_status": None,
                "next_action": "attach award-level novations after 2024-09-27",
            }
        ],
    }
    cover = []
    for domain, items in coverage_domains.items():
        cover.append(ledger.calculate_coverage(subject["entity_id"], domain, items))
    weights = yaml.safe_load((root / "config" / "forensics" / "priority_weights.yaml").read_text())[
        "weights"
    ]
    metrics = {k: 70.0 for k in weights}
    metrics.update(
        {
            "coverage_deficit": 70,
            "estimated_recovery_gain": 85,
            "staleness": 20,
            "financial_materiality": 95,
            "infrastructure_criticality": 90,
            "ownership_complexity": 90,
            "successor_complexity": 100,
            "subcontract_opacity": 85,
        }
    )
    ledger.recalculate_priority(subject["entity_id"], metrics, weights)
    exported = ledger.export_parquet(root / "data" / "forensics" / "parquet")
    tables = {r[0]: ledger.table_count(r[0]) for r in ledger.conn.execute("SHOW TABLES").fetchall()}
    summary = {
        "cluster": subject,
        "adapter_results": results,
        "coverage": cover,
        "tables": tables,
        "parquet_exports": len(exported),
    }
    reports_dir = root / "reports" / "forensics"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "source_adapter_run.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    (reports_dir / "current_status.json").write_text(
        json.dumps(
            {
                "version": "3.1.0-local",
                "active_vector": "CONNECT_CONTRACT_FORENSICS_V3_SOURCE_ADAPTERS",
                "cluster": "JACOBS_CH2M_AMENTUM",
                "adapter_status": results,
                "table_counts": tables,
                "parquet_exports": len(exported),
                "promotion_mode": "manual",
                "last_updated": str(utcnow()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ledger.close()
    return summary
