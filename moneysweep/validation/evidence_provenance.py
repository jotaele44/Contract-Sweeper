"""Evidence provenance certification for Canonical v1.

Source taxonomy is not source identity.  A row does not become T1 merely because
``source_type`` says ``registry``/``filing``/``court_docket``.  Certification
requires an explicit authoritative binding in
``data/manifests/evidence_source_bindings.json``.

The binding registry is deliberately separate from evidence rows so RAW source
strings remain immutable and provenance adjudication can evolve without
silently rewriting observations.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = Path("data/canonical_v1/evidence.csv")
BINDINGS_PATH = Path("data/manifests/evidence_source_bindings.json")
AUTHORITATIVE_STATUS = "authoritative"


@dataclass
class ProvenanceReport:
    row_count: int = 0
    tier_counts: dict[str, int] = field(default_factory=dict)
    authoritative_binding_count: int = 0
    unbound_t1_count: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.unbound_t1_count == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "row_count": self.row_count,
            "tier_counts": self.tier_counts,
            "authoritative_binding_count": self.authoritative_binding_count,
            "unbound_t1_count": self.unbound_t1_count,
            "issues": self.issues,
        }


def load_bindings(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return binding_key -> binding record. Missing registry means no bindings."""
    root = root or REPO_ROOT
    path = root / BINDINGS_PATH
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("bindings", []) if isinstance(payload, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("binding_key") or "").strip()
        if key:
            out[key] = row
    return out


def binding_key_for(row: dict[str, str]) -> str:
    """Stable source-manifestation key used for authority adjudication."""
    return (row.get("source_path_or_url") or "").strip()


def audit_evidence(root: Path | None = None) -> ProvenanceReport:
    root = root or REPO_ROOT
    bindings = load_bindings(root)
    report = ProvenanceReport()
    with (root / EVIDENCE_PATH).open(newline="", encoding="utf-8") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            report.row_count += 1
            tier = (row.get("evidence_tier") or "").strip()
            report.tier_counts[tier] = report.tier_counts.get(tier, 0) + 1
            if tier != "T1":
                continue
            key = binding_key_for(row)
            binding = bindings.get(key)
            if binding and binding.get("status") == AUTHORITATIVE_STATUS:
                # A local frozen manifestation needs a byte hash; a remote source
                # needs a stable authority identifier or explicit authority URL.
                local = key and not key.startswith(("http://", "https://"))
                has_identity = bool(
                    binding.get("stable_id")
                    or binding.get("authority_url")
                    or (local and binding.get("sha256"))
                )
                if has_identity:
                    report.authoritative_binding_count += 1
                    continue
            report.unbound_t1_count += 1
            report.issues.append(
                {
                    "classification": "SOURCE_TAXONOMY_NOT_IDENTITY",
                    "line": line_no,
                    "evidence_id": row.get("evidence_id"),
                    "source_type": row.get("source_type"),
                    "source_name": row.get("source_name"),
                    "source_path_or_url": key,
                    "evidence_tier": tier,
                    "state": "OPEN",
                    "reason": "T1 requires an explicit authoritative source binding",
                }
            )
    return report
