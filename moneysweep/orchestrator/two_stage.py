"""Fail-closed Stage-1/Stage-2 orchestration control plane.

PR0 intentionally does not activate live discovery transports or production
promotion. It establishes the packet boundary, frozen source-role gate, and the
profile dispatcher while preserving legacy full/incremental execution unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moneysweep.discovery.models import DiscoveryStagePacket
from moneysweep.discovery.packet import dump_packet, load_packet
from moneysweep.discovery.source_roles import build_role_ledger, role_counts


@dataclass(frozen=True)
class TwoStageConfig:
    profile: str
    repo_root: Path
    output_root: Path
    discovery_packet: Path | None = None
    discovery_seeds: tuple[str, ...] = ()
    generated_at: str | None = None


def _timestamp(value: str | None) -> str:
    return value or datetime.now(timezone.utc).isoformat()


def _source_gate() -> dict[str, Any]:
    ledger = build_role_ledger()
    counts = role_counts(ledger)
    return {
        "classified": len(ledger),
        "unclassified": 0,
        "duplicates": 0,
        "role_counts": counts,
    }


def run_discovery(config: TwoStageConfig) -> dict[str, Any]:
    gate = _source_gate()
    if not config.discovery_seeds:
        raise ValueError("--discovery-seed is required for discovery profile")

    packet = DiscoveryStagePacket(
        case_id="discovery-" + str(abs(hash(tuple(config.discovery_seeds)))),
        created_at=_timestamp(config.generated_at),
        subject_seeds=config.discovery_seeds,
        candidates=(),
        relationships=(),
        contradictions=(),
        explicit_exclusions=(),
        source_manifest=(),
    )
    packet_path = config.output_root / "discovery_stage_packet.json"
    dump_packet(packet, packet_path)
    return {
        "profile": "discovery",
        "status": "PROVISIONAL",
        "production_promotion": "BLOCKED",
        "source_role_gate": gate,
        "packet": str(packet_path),
        "candidate_count": 0,
        "note": (
            "PR0 emits the governed Stage-1 packet boundary; live discovery transport "
            "activation remains blocked until an observed transport contract is pinned."
        ),
    }


def run_corpus(config: TwoStageConfig) -> dict[str, Any]:
    gate = _source_gate()
    if config.discovery_packet is None:
        raise ValueError("--discovery-packet is required for corpus profile")
    packet = load_packet(config.discovery_packet)
    eligible = packet.stage2_subject_ids()
    return {
        "profile": "corpus",
        "status": "PROVISIONAL",
        "production_promotion": "BLOCKED",
        "source_role_gate": gate,
        "packet": str(config.discovery_packet),
        "stage2_subject_ids": list(eligible),
        "stage2_subject_count": len(eligible),
        "candidate_scoped_unresolved_count": sum(
            1 for candidate in packet.candidates if candidate.candidate_id not in set(eligible)
        ),
        "note": "Corpus execution is gated by the DiscoveryStagePacket; corpus hits cannot promote identity.",
    }


def run_two_stage(config: TwoStageConfig) -> dict[str, Any]:
    if config.discovery_packet is None:
        discovery_result = run_discovery(config)
        return {
            "profile": "two-stage",
            "status": "PROVISIONAL_STAGE1_COMPLETE",
            "production_promotion": "BLOCKED",
            "discovery": discovery_result,
            "corpus": None,
        }
    corpus_result = run_corpus(config)
    return {
        "profile": "two-stage",
        "status": "PROVISIONAL_STAGE2_PACKET_VALIDATED",
        "production_promotion": "BLOCKED",
        "discovery": {"packet": str(config.discovery_packet)},
        "corpus": corpus_result,
    }


def run_profile(config: TwoStageConfig) -> dict[str, Any]:
    if config.profile == "discovery":
        return run_discovery(config)
    if config.profile == "corpus":
        return run_corpus(config)
    if config.profile == "two-stage":
        return run_two_stage(config)
    raise ValueError(f"unsupported two-stage profile: {config.profile}")
