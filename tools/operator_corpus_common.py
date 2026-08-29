from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

RECEIPT_SCHEMA_VERSION = "moneysweep.operator_evidence/v1"
CORPUS_SCHEMA_VERSION = "moneysweep.operator_corpus/v1"
VERIFICATION_SCHEMA_VERSION = "moneysweep.operator_corpus_verification/v1"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_rows(path: Path) -> int | None:
    if path.suffix.lower() != ".csv":
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return max(sum(1 for _ in csv.reader(fh)) - 1, 0)
    except (OSError, UnicodeDecodeError, csv.Error):
        return None


def safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {value!r}")
    normalized = Path(*[part for part in path.parts if part not in {"", "."}])
    if not normalized.parts:
        raise ValueError(f"empty relative path: {value!r}")
    return normalized


def load_sources(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    registry_path = root / "registries" / "source_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    sources = list(registry.get("sources") or [])
    registry_paths = ["registries/source_registry.yaml"]

    extension_dir = root / "registries" / "source_registry_extensions"
    if extension_dir.exists():
        for path in sorted(extension_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            extension_sources = payload.get("sources")
            if extension_sources is None:
                continue
            if not isinstance(extension_sources, list):
                raise RuntimeError(f"source registry extension must contain sources list: {path}")
            sources.extend(extension_sources)
            registry_paths.append(path.relative_to(root).as_posix())

    source_ids = [str(source.get("source_id", "")).strip() for source in sources]
    if any(not source_id for source_id in source_ids):
        raise RuntimeError("source registry contains an empty source_id")
    counts = {source_id: source_ids.count(source_id) for source_id in source_ids}
    duplicates = sorted(source_id for source_id, count in counts.items() if count > 1)
    if duplicates:
        raise RuntimeError("duplicate source IDs: " + ", ".join(duplicates))
    return sources, registry_paths


def source_ids_digest(sources: list[dict[str, Any]]) -> str:
    source_ids = sorted(str(source["source_id"]).strip() for source in sources)
    return sha256_bytes(canonical_json(source_ids))


def source_definition_digest(source: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(source))


def expected_outputs(source: dict[str, Any]) -> list[str]:
    value = source.get("expected_outputs")
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def manifest_digest(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("corpus_id", None)
    return sha256_bytes(canonical_json(payload))
