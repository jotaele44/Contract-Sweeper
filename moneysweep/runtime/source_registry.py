"""Source-registry loader.

Reads ``registries/source_registry.json`` (stable wire format), appends optional
source extensions, then applies narrowly scoped metadata overrides from
``registries/source_registry_overrides/*.json``. Overrides may not add sources or
change ``source_id`` / ``required``; therefore source counts and the required
source denominator remain stable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY_PATH = "registries/source_registry.json"
DEFAULT_EXTENSIONS_DIR = "registries/source_registry_extensions"
DEFAULT_OVERRIDES_DIR = "registries/source_registry_overrides"

REPO_ROOT = Path(__file__).resolve().parents[2]
_IMMUTABLE_OVERRIDE_FIELDS = frozenset({"source_id", "required"})


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_registry_extensions(root: Path) -> list[dict[str, Any]]:
    extensions_dir = root / DEFAULT_EXTENSIONS_DIR
    if not extensions_dir.exists():
        return []
    sources: list[dict[str, Any]] = []
    for path in sorted(extensions_dir.glob("*.json")):
        data = _load_json(path)
        sources.extend(data.get("sources", []))
    return sources


def _load_registry_overrides(root: Path) -> list[dict[str, Any]]:
    overrides_dir = root / DEFAULT_OVERRIDES_DIR
    if not overrides_dir.exists():
        return []
    overrides: list[dict[str, Any]] = []
    for path in sorted(overrides_dir.glob("*.json")):
        data = _load_json(path)
        overrides.extend(data.get("source_overrides", []))
    return overrides


def _apply_registry_overrides(
    sources: list[dict[str, Any]], overrides: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not overrides:
        return sources
    by_id = {source.get("source_id"): dict(source) for source in sources}
    seen_overrides: set[str] = set()
    for override in overrides:
        source_id = str(override.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source registry override missing source_id")
        if source_id in seen_overrides:
            raise ValueError(f"duplicate source registry override: {source_id}")
        seen_overrides.add(source_id)
        if source_id not in by_id:
            raise ValueError(f"source registry override targets unknown source: {source_id}")
        base = by_id[source_id]
        for field in _IMMUTABLE_OVERRIDE_FIELDS:
            if field in override and override[field] != base.get(field):
                raise ValueError(f"{source_id}: override may not change immutable field {field}")
        base.update({key: value for key, value in override.items() if key != "source_id"})
        by_id[source_id] = base
    return [by_id[source.get("source_id")] for source in sources]


def load_source_registry(root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    reg = _load_json(root / DEFAULT_REGISTRY_PATH)
    sources = list(reg.get("sources", []))
    sources.extend(_load_registry_extensions(root))
    sources = _apply_registry_overrides(sources, _load_registry_overrides(root))
    reg = dict(reg)
    reg["sources"] = sources
    return reg


def required_sources(root: Path | None = None) -> list[dict[str, Any]]:
    return [
        source for source in load_source_registry(root).get("sources", []) if source.get("required")
    ]


def all_sources(root: Path | None = None) -> list[dict[str, Any]]:
    return load_source_registry(root).get("sources", [])


def source_by_id(source_id: str, root: Path | None = None) -> dict[str, Any] | None:
    for source in all_sources(root):
        if source.get("source_id") == source_id:
            return source
    return None


def expected_outputs_for(source: dict[str, Any], root: Path | None = None) -> list[Path]:
    root = root or REPO_ROOT
    return [root / path for path in source.get("expected_outputs", [])]


def producer_script_for(source: dict[str, Any], root: Path | None = None) -> Path | None:
    root = root or REPO_ROOT
    script = source.get("producer_script")
    return (root / script) if script else None


def validate_registry(root: Path | None = None) -> dict[str, Any]:
    root = root or REPO_ROOT
    try:
        sources = load_source_registry(root).get("sources", [])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "source_count": 0,
            "required_count": 0,
            "errors": [str(exc)],
            "warnings": [],
            "ok": False,
        }
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for source in sources:
        source_id = source.get("source_id")
        if not source_id:
            errors.append(f"source missing source_id: {source!r}")
            continue
        if source_id in seen:
            errors.append(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        script = source.get("producer_script")
        if script:
            if ".." in Path(script).parts:
                errors.append(f"{source_id}: producer_script contains parent traversal")
            elif not (root / script).exists():
                errors.append(f"{source_id}: producer_script not found: {script}")
        outputs = source.get("expected_outputs") or []
        for output in outputs:
            if ".." in Path(output).parts:
                errors.append(f"{source_id}: expected_output contains parent traversal: {output}")
        if source.get("required") and not outputs:
            warnings.append(f"{source_id}: required source has no expected_outputs declared")
        if source.get("authentication") == "manual_export" and not source.get("manual_drop_dir"):
            warnings.append(f"{source_id}: manual_export source missing manual_drop_dir")
    return {
        "source_count": len(sources),
        "required_count": sum(1 for source in sources if source.get("required")),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--validate", action="store_true", help="Run validation checks")
    args = parser.parse_args(argv)
    from moneysweep.runtime.logging_config import configure_logging

    configure_logging()
    if args.validate:
        report = validate_registry(args.root)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    registry = load_source_registry(args.root)
    print(json.dumps({"source_count": len(registry.get("sources", []))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
