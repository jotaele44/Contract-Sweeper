#!/usr/bin/env python3
"""Validate the MoneySweep federation spatial sidecar fail closed."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
HEX40 = re.compile(r"^[a-f0-9]{40}$")
REQUIRED = {"feature", "layer", "map_runtime", "offline_package", "impact_report"}
MANIFEST_SCHEMA = Path("schemas/federation_spatial_manifest_v1.schema.json")
IMPACT_REPORT = Path("reports/federation_spatial_impact_v1.json")


def _load_object(path: Path, label: str, problems: list[str]) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        problems.append(f"cannot read {label}: {exc}")
        return None
    if not isinstance(value, dict):
        problems.append(f"{label} root must be an object")
        return None
    return value


def _repo_path(root: Path, value: object, label: str, problems: list[str]) -> Path | None:
    if not isinstance(value, str) or not value:
        problems.append(f"{label} must be a non-empty relative path")
        return None
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        problems.append(f"{label} escapes repository root")
        return None
    return root / relative


def _validate_instance(instance: dict, schema: dict, label: str, problems: list[str]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(instance)
    except SchemaError as exc:
        problems.append(f"invalid JSON schema for {label}: {exc.message}")
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        problems.append(f"{label} schema violation at {location}: {exc.message}")


def validate(root: Path) -> list[str]:
    problems: list[str] = []
    manifest = _load_object(root / "federation.spatial.json", "spatial manifest", problems)
    if manifest is None:
        return problems

    manifest_schema = _load_object(root / MANIFEST_SCHEMA, "spatial manifest schema", problems)
    if manifest_schema is not None:
        _validate_instance(manifest, manifest_schema, "spatial manifest", problems)

    if manifest.get("producer_repo") != "moneysweep-pr":
        problems.append("producer_repo mismatch")
    cross_repo = manifest.get("cross_repo")
    if not isinstance(cross_repo, dict):
        problems.append("cross_repo must be an object")
        cross_repo = {}
    if cross_repo.get("identity_default") != "CANDIDATE_NOT_IDENTITY":
        problems.append("identity default must fail closed")
    if cross_repo.get("hub_correlation_authority") != "thehub-pr":
        problems.append("hub correlation authority drift")
    if cross_repo.get("consumer_contract") != "federation-spatial-contract/1.0":
        problems.append("consumer contract drift")
    if not HEX40.fullmatch(str(manifest.get("frozen_base_sha", ""))):
        problems.append("invalid frozen_base_sha")

    contracts = manifest.get("contracts")
    if not isinstance(contracts, dict) or set(contracts) != REQUIRED:
        problems.append("contract path set mismatch")
        contracts = {}
    schemas: dict[str, dict] = {}
    for label, value in contracts.items():
        path = _repo_path(root, value, f"contract {label}", problems)
        if path is None:
            continue
        schema = _load_object(path, f"contract {label}", problems)
        if schema is not None:
            schemas[label] = schema
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                problems.append(f"invalid JSON schema for contract {label}: {exc.message}")

    impact = _load_object(root / IMPACT_REPORT, "spatial impact report", problems)
    if impact is not None and "impact_report" in schemas:
        _validate_instance(impact, schemas["impact_report"], "spatial impact report", problems)

    storage = manifest.get("storage")
    if not isinstance(storage, dict):
        problems.append("storage must be an object")
        storage = {}
    for key in ("postgis_migration", "mvt_migration"):
        path = _repo_path(root, storage.get(key), f"storage {key}", problems)
        if path is not None and not path.is_file():
            problems.append(f"missing storage artifact: {key}")
    if storage.get("ownership") != "REPO_LOCAL":
        problems.append("storage ownership must be REPO_LOCAL")

    extensions = manifest.get("domain_extensions")
    if not isinstance(extensions, list):
        problems.append("domain_extensions must be an array")
        extensions = []
    for index, value in enumerate(extensions):
        path = _repo_path(root, value, f"domain_extensions[{index}]", problems)
        if path is not None and not path.is_file():
            problems.append(f"missing domain extension: {value}")
    return problems


def main() -> int:
    problems = validate(ROOT)
    print(
        json.dumps(
            {"ok": not problems, "producer_repo": "moneysweep-pr", "problems": problems}, indent=2
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
