"""Two-stage workflow classification for the frozen source registry.

The classification is intentionally independent from materialization path. A
manual export can still be CORPUS; RECOVERY is reserved for acquisition routes
whose output is evidence to be ingested/adjudicated later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_REGISTRY = PROJECT_ROOT / "registries" / "source_registry.yaml"
CURRENT_STATUS = PROJECT_ROOT / "reports" / "current_status.json"

# Frozen at PR0 branch base (main, 2026-08-24). The previous requested 157-source
# denominator was superseded by rdc_demandas_civiles, which moved 157 -> 158.
FROZEN_SOURCE_COUNT = 158
FROZEN_SOURCE_IDS_SHA256 = "673659d9c53e8428e21052d95819ff35023e90142756686e73a9c9f1b326bbf2"


class SourceRole(str, Enum):
    DISCOVERY = "DISCOVERY"
    CORPUS = "CORPUS"
    BOTH = "BOTH"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class SourceRoleRecord:
    source_id: str
    role: SourceRole
    justification: str
    family: str
    producer_script: str


_BOTH_IDS = frozenset(
    {
        # Registries/filings where the same record establishes identity or a
        # relationship and also carries a substantive event/transaction.
        "lda",
        "pr_cabilderos",
        "fec",
        "fec_committees",
        "donaciones_pr",
        "contralor_electoral",
        "oce_socrata_live",
        "campaign_finance_entities",
        "ngo_integration_layer",
        "nonprofits_irs990",
        "sec_edgar",
        "sec_officers",
        "gleif_lei",
        "ofac_sdn",
        "sam_exclusions",
        "rdc_demandas_civiles",
        "pr_act_60_decrees",
        "gaming_commission",
    }
)

_DISCOVERY_IDS = frozenset(
    {
        "sam_entities",
        "asg_suppliers",
        "dcaa_active_contractors",
        "pr_corporate_registry",
        "financialdata_net",
        "legislapr_discovery",
        "legislapr_sessions",
        "legislative_canonical_sources",
        "osl_sutra_crosswalk",
        "legislative_fiscal_link_candidates",
        "roadwatch_corridor_join",
        "centinelas_pre_official_signals",
    }
)


def _load_registry(path: Path = SOURCE_REGISTRY) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("source registry sources must be a list")
    return sources


def _classify(source: dict[str, Any]) -> SourceRoleRecord:
    source_id = str(source.get("source_id", "")).strip()
    family = str(source.get("family", "")).strip()
    producer = str(source.get("producer_script", "")).strip()
    notes = " ".join(str(source.get("notes", "")).split())

    if not source_id:
        raise ValueError("source without source_id")

    if source_id in _BOTH_IDS:
        role = SourceRole.BOTH
        reason = "record supplies identity/relationship evidence and substantive corpus facts"
    elif source_id in _DISCOVERY_IDS:
        role = SourceRole.DISCOVERY
        reason = "source is identity/candidate/crosswalk discovery and does not by itself prove a money flow"
    elif family == "entity_resolution":
        role = SourceRole.DISCOVERY
        reason = "entity_resolution family is identity-first; substantive screening exceptions are explicit BOTH overrides"
    elif family in {"lobbying", "political_finance"}:
        role = SourceRole.BOTH
        reason = "registry/filing records identify actors while also recording lobbying or political-finance events"
    elif family == "provenance_archival":
        role = SourceRole.RECOVERY
        reason = "archival locator is an evidence-acquisition route, not a positive identity or corpus assertion"
    else:
        role = SourceRole.CORPUS
        reason = "source primarily supplies substantive financial, governmental, infrastructure, oversight, or program records"

    context = notes[:180] if notes else "no registry note"
    justification = (
        f"{source_id}: {reason}; family={family or 'UNKNOWN'}; "
        f"producer={producer or 'NONE'}; registry_context={context}"
    )
    return SourceRoleRecord(source_id, role, justification, family, producer)


def build_role_ledger(
    registry_path: Path = SOURCE_REGISTRY,
    status_path: Path = CURRENT_STATUS,
    *,
    enforce_frozen: bool = True,
) -> tuple[SourceRoleRecord, ...]:
    """Classify every current source and enforce row conservation/freeze gates."""
    sources = _load_registry(registry_path)
    source_ids = [str(source.get("source_id", "")) for source in sources]
    duplicates = sorted({source_id for source_id in source_ids if source_ids.count(source_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate source_id values: {duplicates}")

    ledger = tuple(_classify(source) for source in sources)
    if len(ledger) != len(source_ids):
        raise AssertionError("source-role row conservation failure")
    if any(not record.justification for record in ledger):
        raise AssertionError("every source requires a source-specific justification")

    if enforce_frozen:
        if len(source_ids) != FROZEN_SOURCE_COUNT:
            raise ValueError(
                f"source denominator drift: expected {FROZEN_SOURCE_COUNT}, got {len(source_ids)}"
            )
        status = json.loads(status_path.read_text(encoding="utf-8"))
        frozen = status.get("source_registry_current", {})
        if frozen.get("total_sources") != FROZEN_SOURCE_COUNT:
            raise ValueError("current_status source count no longer matches PR0 freeze")
        if frozen.get("source_ids_sha256") != FROZEN_SOURCE_IDS_SHA256:
            raise ValueError("current_status source-id digest no longer matches PR0 freeze")

    if {record.source_id for record in ledger} != set(source_ids):
        raise AssertionError("classified source set differs from registry source set")
    return ledger


def role_counts(ledger: tuple[SourceRoleRecord, ...]) -> dict[str, int]:
    counts = {role.value: 0 for role in SourceRole}
    for record in ledger:
        counts[record.role.value] += 1
    return counts
