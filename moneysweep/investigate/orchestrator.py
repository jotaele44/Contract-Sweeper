"""Generalized 1:N entity investigation orchestrator."""

from __future__ import annotations

import csv
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from moneysweep.query import EntityIdentifier, EntityQuery, Query, query, query_entities
from moneysweep.query.adapters import ADAPTER_REGISTRY, ENTITY_ADAPTER_REGISTRY
from moneysweep.runtime.name_normalization import normalize_name

from .models import InvestigationLimits, InvestigationResult, InvestigationTarget, ResolutionState
from .resolver import CanonicalEntityIndex

SUPPORTED_MODES = frozenset(
    {"PROFILE", "LINEAGE", "CORRELATION", "RELATIONSHIP", "CONVERGENCE", "FULL"}
)
PARENT_MAP = Path("data/reference/entity_parent_map.csv")
LOCAL_PRODUCTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "data/staging/processed/enrichment/entity_hierarchy.csv",
        ("vendor_name", "parent_name"),
    ),
    (
        "data/staging/processed/pr_entity_profiles.csv",
        ("recipient_name", "np_name", "med_provider_name", "bank_name"),
    ),
    (
        "data/staging/processed/pr_all_awards_master.csv",
        ("recipient_name", "vendor_name", "parent_name"),
    ),
)
UEI_FIELDS = ("recipient_uei", "uei", "known_uei")
DEFAULT_UEI_GENERAL_SOURCES = ("usaspending_prime", "grants_gov")


def _coerce_modes(modes: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(mode).upper() for mode in modes)) or ("PROFILE",)
    unknown = sorted(set(normalized) - SUPPORTED_MODES)
    if unknown:
        raise ValueError(f"unsupported investigation modes: {', '.join(unknown)}")
    if "FULL" in normalized:
        return ("PROFILE", "LINEAGE", "CORRELATION", "RELATIONSHIP", "CONVERGENCE")
    return normalized


def _attach_external_identifiers(
    target: InvestigationTarget,
    identifiers: dict[str, tuple[EntityIdentifier, ...]] | None,
) -> InvestigationTarget:
    if not target.resolved or not target.canonical_entity_id or not identifiers:
        return target
    attached = identifiers.get(target.canonical_entity_id, ())
    return replace(target, external_identifiers=tuple(attached)) if attached else target


def _load_parent_edges(root: Path) -> list[dict[str, str]]:
    path = root / PARENT_MAP
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _lineage(
    root: Path,
    targets: list[InvestigationTarget],
    limits: InvestigationLimits,
) -> list[dict[str, str]]:
    edges = _load_parent_edges(root)
    seeds = {t.canonical_entity_id for t in targets if t.resolved and t.canonical_entity_id}
    if not seeds or limits.max_depth == 0:
        return []
    selected: list[dict[str, str]] = []
    seen_edge_ids: set[str] = set()
    seen_nodes = set(seeds)
    queue = deque((seed, 0) for seed in sorted(seeds))
    while queue and len(selected) < limits.max_edges:
        node, depth = queue.popleft()
        if depth >= limits.max_depth:
            continue
        for edge in edges:
            parent = edge.get("parent_entity_id", "")
            child = edge.get("child_entity_id", "")
            if node not in (parent, child):
                continue
            edge_id = edge.get("relation_id", "")
            if edge_id in seen_edge_ids:
                continue
            selected.append(dict(edge))
            seen_edge_ids.add(edge_id)
            neighbor = child if node == parent else parent
            if neighbor and neighbor not in seen_nodes and len(seen_nodes) < limits.max_nodes:
                seen_nodes.add(neighbor)
                queue.append((neighbor, depth + 1))
            if len(selected) >= limits.max_edges:
                break
    return selected


def _target_names(target: InvestigationTarget) -> set[str]:
    if not target.resolved:
        return set()
    values = [target.canonical_name or "", *target.aliases]
    return {normalize_name(value) for value in values if value}


def _target_ueis(target: InvestigationTarget) -> set[str]:
    return {
        ident.value.strip()
        for ident in target.external_identifiers
        if ident.kind == "uei" and ident.value.strip()
    }


def _local_correlations(
    root: Path,
    targets: list[InvestigationTarget],
    *,
    max_matches: int,
) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for rel_path, name_fields in LOCAL_PRODUCTS:
        path = root / rel_path
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for source_row, row in enumerate(reader, start=2):
                for target in targets:
                    if not target.resolved or not target.canonical_entity_id:
                        continue
                    ueis = _target_ueis(target)
                    row_ueis = {str(row.get(field) or "").strip() for field in UEI_FIELDS}
                    stable_match = bool(ueis & {value for value in row_ueis if value})
                    names = _target_names(target)
                    matched_field = None
                    matched_value = None
                    for field in name_fields:
                        raw = str(row.get(field) or "").strip()
                        if raw and normalize_name(raw) in names:
                            matched_field, matched_value = field, raw
                            break
                    if not stable_match and matched_field is None:
                        continue
                    matches.append(
                        {
                            "canonical_entity_id": target.canonical_entity_id,
                            "source_path": rel_path,
                            "source_row": source_row,
                            "match_status": "LINKED" if stable_match else "CANDIDATE_NOT_IDENTITY",
                            "match_method": "uei"
                            if stable_match
                            else "canonical_or_alias_name_discovery",
                            "matched_field": matched_field,
                            "matched_value": matched_value,
                            "record": dict(row),
                        }
                    )
                    if len(matches) >= max_matches:
                        return matches
    return matches


def _remote_queries(
    root: Path,
    targets: list[InvestigationTarget],
    source_ids: list[str] | None,
    *,
    force_refresh: bool,
) -> dict[str, object]:
    selected = source_ids or sorted(ENTITY_ADAPTER_REGISTRY)
    entity_ids = [sid for sid in selected if sid in ENTITY_ADAPTER_REGISTRY]
    identifiers: list[EntityIdentifier] = []
    for target in targets:
        identifiers.extend(target.query_identifiers(include_names=True))

    ueis = sorted({uei for target in targets for uei in _target_ueis(target)})
    if source_ids is None:
        general_ids = [sid for sid in DEFAULT_UEI_GENERAL_SOURCES if sid in ADAPTER_REGISTRY]
    else:
        general_ids = [sid for sid in source_ids if sid in ADAPTER_REGISTRY]

    summary: dict[str, object] = {}
    if identifiers and entity_ids:
        result = query_entities(
            EntityQuery(identifiers=tuple(identifiers)),
            source_ids=entity_ids,
            root=root,
            force_refresh=force_refresh,
        )
        summary["entity_sources"] = {
            "summary": result.summary(),
            "outcomes": {
                sid: {
                    "status": out.status,
                    "rows": out.rows,
                    "fetched_at": out.fetched_at,
                    "error": out.error,
                    "reason": out.reason,
                }
                for sid, out in result.outcomes.items()
            },
            "identity_warning": (
                "Remote name results are discovery candidates unless independently bound "
                "by authoritative identifiers."
            ),
        }
    if ueis and general_ids:
        result = query(
            Query(recipient_ueis=tuple(ueis)),
            source_ids=general_ids,
            root=root,
            force_refresh=force_refresh,
        )
        summary["general_sources"] = {
            "summary": result.summary(),
            "outcomes": {
                sid: {
                    "status": out.status,
                    "rows": out.rows,
                    "fetched_at": out.fetched_at,
                    "error": out.error,
                    "reason": out.reason,
                }
                for sid, out in result.outcomes.items()
            },
            "routing_basis": "attached_uei",
        }
    return summary


def investigate(
    target_values: Iterable[str],
    *,
    root: Path | str = ".",
    modes: Iterable[str] = ("PROFILE",),
    limits: InvestigationLimits | None = None,
    external_identifiers: dict[str, tuple[EntityIdentifier, ...]] | None = None,
    remote: bool = False,
    source_ids: list[str] | None = None,
    force_refresh: bool = False,
    max_local_matches: int = 500,
) -> InvestigationResult:
    """Investigate one or more canonical entities without silently inventing identity.

    Unresolved or ambiguous targets are preserved in the result and never used
    to generate relationship edges. Local normalized-name correlations are
    explicitly labeled ``CANDIDATE_NOT_IDENTITY``; a shared UEI may produce a
    ``LINKED`` correlation.
    """
    root = Path(root).resolve()
    mode_tuple = _coerce_modes(modes)
    limits = limits or InvestigationLimits()
    index = CanonicalEntityIndex(root=root)
    targets = [
        _attach_external_identifiers(index.resolve(value), external_identifiers)
        for value in target_values
    ]
    result = InvestigationResult(targets=targets, modes=mode_tuple)

    for collision in index.identity_collisions():
        result.review_items.append(
            {
                "object_type": "canonical_identity_index",
                "raw_value": collision["normalized_key"],
                "issue_type": collision["issue_type"],
                "candidates": collision["candidate_entity_ids"],
                "status": "OPEN",
            }
        )
    for issue in index.integrity_issues:
        result.review_items.append(
            {
                "object_type": "canonical_identity_index",
                "raw_value": issue.get("entity_id") or issue.get("alias") or "",
                "issue_type": issue["issue_type"],
                "candidates": [],
                "status": "OPEN",
                "source_path": issue.get("source_path"),
                "source_row": issue.get("source_row"),
            }
        )

    for target in targets:
        if target.resolution_state is ResolutionState.REVIEW:
            result.review_items.append(
                {
                    "object_type": "investigation_target",
                    "raw_value": target.requested_value,
                    "issue_type": target.match_method,
                    "candidates": list(target.candidates),
                    "status": "OPEN",
                }
            )
        elif target.resolution_state is ResolutionState.UNRESOLVED:
            result.review_items.append(
                {
                    "object_type": "investigation_target",
                    "raw_value": target.requested_value,
                    "issue_type": "unresolved_identity",
                    "candidates": [],
                    "status": "OPEN",
                }
            )
    if "LINEAGE" in mode_tuple or "RELATIONSHIP" in mode_tuple or "CONVERGENCE" in mode_tuple:
        result.lineage_edges = _lineage(root, targets, limits)
    if "CORRELATION" in mode_tuple or "RELATIONSHIP" in mode_tuple or "CONVERGENCE" in mode_tuple:
        result.local_correlations = _local_correlations(
            root, targets, max_matches=max_local_matches
        )
    if remote:
        result.remote_source_summaries = _remote_queries(
            root, targets, source_ids, force_refresh=force_refresh
        )
    if "RELATIONSHIP" in mode_tuple or "CONVERGENCE" in mode_tuple:
        result.notes.append(
            "Relationship/convergence v1 is bounded to canonical parent-map edges plus "
            "preserved local correlation candidates; it does not promote name-only "
            "overlaps to graph identity."
        )
    return result
