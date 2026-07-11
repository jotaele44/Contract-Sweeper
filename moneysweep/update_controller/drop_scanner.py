"""Operator file-drop scanner (spec §6 file_drop / §10 drop_scanner).

Scans only a source's declared ``watch_paths`` for files matching its
``filename_patterns``, computes a streaming SHA-256, and compares against a
consumed-file manifest. It never moves or deletes source files, rejects symlinks
that escape the repository root, and marks a file consumed only after a
successful ingestion.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moneysweep.update_controller.models import SourceUpdatePolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
# Consumed-hash manifest is a gitignored runtime artifact.
CONSUMED_REL = "reports/source_update_consumed.local.json"


@dataclass
class DropCandidate:
    source_id: str
    path: str  # repo-relative
    sha256: str
    size_bytes: int
    is_new: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "is_new": self.is_new,
        }


def _sha256_stream(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_within_root(root: Path, path: Path) -> bool:
    """Reject symlinks (or resolved targets) that escape the repository root."""
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except Exception:
        return False
    # Explicitly reject symlinked entries pointing outside the tree.
    if path.is_symlink():
        try:
            path.resolve().relative_to(root.resolve())
        except Exception:
            return False
    return True


def load_consumed(root: Path | None = None, path: str | Path | None = None) -> dict[str, list[str]]:
    root = root or REPO_ROOT
    p = _resolve(root, path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return {k: list(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def scan_source(
    policy: SourceUpdatePolicy,
    root: Path | None = None,
    consumed_path: str | Path | None = None,
) -> list[DropCandidate]:
    """Return drop candidates for one file-drop / on-drop source (no state change)."""
    root = root or REPO_ROOT
    if policy.trigger_type not in ("file_drop", "on_drop"):
        return []
    consumed = set(load_consumed(root, consumed_path).get(policy.source_id, []))
    patterns = policy.filename_patterns or ["*"]
    candidates: list[DropCandidate] = []
    seen_paths: set[str] = set()
    for watch in policy.watch_paths:
        base = (root / watch).resolve()
        if not base.exists() or not base.is_dir():
            continue
        for entry in sorted(base.rglob("*")):
            if not entry.is_file():
                continue
            if not any(fnmatch.fnmatch(entry.name, pat) for pat in patterns):
                continue
            if not _safe_within_root(root, entry):
                continue
            try:
                rel = str(entry.resolve().relative_to(root.resolve()))
            except Exception:
                continue
            if rel in seen_paths:
                continue
            seen_paths.add(rel)
            digest = _sha256_stream(entry)
            candidates.append(
                DropCandidate(
                    source_id=policy.source_id,
                    path=rel,
                    sha256=digest,
                    size_bytes=entry.stat().st_size,
                    is_new=digest not in consumed,
                )
            )
    return candidates


def scan_all(
    policies: dict[str, SourceUpdatePolicy],
    root: Path | None = None,
    consumed_path: str | Path | None = None,
) -> dict[str, list[DropCandidate]]:
    root = root or REPO_ROOT
    out: dict[str, list[DropCandidate]] = {}
    for sid, pol in policies.items():
        if pol.trigger_type in ("file_drop", "on_drop") and pol.enabled:
            cands = scan_source(pol, root, consumed_path)
            if cands:
                out[sid] = cands
    return out


def has_new_drop(
    policy: SourceUpdatePolicy,
    root: Path | None = None,
    consumed_path: str | Path | None = None,
) -> bool:
    return any(c.is_new for c in scan_source(policy, root, consumed_path))


def mark_consumed(
    source_id: str,
    sha256: str,
    root: Path | None = None,
    consumed_path: str | Path | None = None,
) -> Path:
    """Record a file hash as consumed (call only after successful ingestion)."""
    root = root or REPO_ROOT
    p = _resolve(root, consumed_path)
    consumed = load_consumed(root, consumed_path)
    lst = consumed.setdefault(source_id, [])
    if sha256 not in lst:
        lst.append(sha256)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(consumed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return p


def _resolve(root: Path, override: str | Path | None) -> Path:
    if override:
        p = Path(override)
        return p if p.is_absolute() else (root / p)
    return root / CONSUMED_REL
