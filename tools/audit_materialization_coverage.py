#!/usr/bin/env python3
"""Build a current-denominator materialization/lineage audit.

The historical coverage audit mixed an operator-local corpus with a clean-checkout
inventory and is therefore not safe to promote merely by changing its denominator.
This tool always records the corpus it actually measured. Production certification
may only treat the result as authoritative when --operator-corpus-authoritative is
explicitly supplied on the machine holding the complete operator corpus.
"""
from __future__ import annotations
import argparse, csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import yaml

def _row_count(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return max(sum(1 for _ in csv.reader(fh)) - 1, 0)
    except (OSError, UnicodeDecodeError, csv.Error):
        return None

def _sha256(path: Path) -> str | None:
    try: return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError: return None

def _as_paths(value: Any) -> list[str]:
    if not value: return []
    if isinstance(value, str): return [value]
    return [str(item) for item in value]

def build(root: Path, *, operator_corpus_authoritative: bool) -> dict[str, Any]:
    registry_path = root / "registries/source_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    sources = registry.get("sources") or []
    declared: dict[str, list[str]] = {}
    source_rows: list[dict[str, Any]] = []
    required_total = required_full = full = partial = missing = no_outputs = 0
    for source in sources:
        source_id = str(source.get("source_id", "")).strip()
        outputs = _as_paths(source.get("expected_outputs"))
        if source.get("required") is True: required_total += 1
        present = total_rows = unreadable = 0
        output_evidence = []
        for rel in outputs:
            declared.setdefault(rel, []).append(source_id)
            path = root / rel
            exists = path.exists()
            rows = _row_count(path) if exists and path.is_file() and path.suffix.lower() == ".csv" else None
            if exists: present += 1
            if rows is not None: total_rows += rows
            elif exists and path.is_file() and path.suffix.lower() == ".csv": unreadable += 1
            output_evidence.append({"path": rel, "exists": exists, "data_rows": rows, "sha256": _sha256(path) if exists and path.is_file() else None})
        if not outputs:
            status = "no_outputs_declared"; no_outputs += 1
        elif present == len(outputs):
            status = "fully_materialized"; full += 1
            if source.get("required") is True: required_full += 1
        elif present:
            status = "partially_materialized"; partial += 1
        else:
            status = "not_materialized"; missing += 1
        source_rows.append({"source_id": source_id, "family": source.get("family"), "required": bool(source.get("required")), "expected_output_count": len(outputs), "present_count": present, "local_rows": total_rows, "unreadable_csv_count": unreadable, "local_status": status, "outputs": output_evidence})
    processed = root / "data/staging/processed"
    inventory = []
    total_rows = accounted_rows = measured_orphan_rows = measured_orphan_files = 0
    if processed.exists():
        for path in sorted(processed.rglob("*.csv")):
            rel = path.relative_to(root).as_posix(); rows = _row_count(path); row_count = rows or 0
            owners = declared.get(rel, []); classification = "declared" if owners else "unclaimed"
            total_rows += row_count
            if owners: accounted_rows += row_count
            else: measured_orphan_rows += row_count; measured_orphan_files += 1
            inventory.append({"file": rel, "rows": rows, "claimed_by": owners, "classification": classification, "sha256": _sha256(path)})
    # Fail closed: checkout-visible orphan measurements are informative, but cannot
    # certify the authoritative operator corpus. The certifier's legacy G8 check
    # requires orphan_rows == 0; null deliberately keeps G8 blocked until an
    # operator explicitly runs this against the complete corpus.
    certifiable_orphan_rows = measured_orphan_rows if operator_corpus_authoritative else None
    certifiable_orphan_files = measured_orphan_files if operator_corpus_authoritative else None
    return {
        "schema_version": "coverage_audit_v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_scope": {"root": str(root), "registry_path": "registries/source_registry.yaml", "registry_schema_version": registry.get("schema_version"), "operator_corpus_authoritative": operator_corpus_authoritative, "corpus_class": "authoritative_operator_corpus" if operator_corpus_authoritative else "checkout_visible_files_only", "warning": None if operator_corpus_authoritative else "Checkout-visible files are not the authoritative operator corpus; G8 must remain blocked."},
        "local_truth_summary": {"total_sources": len(sources), "required_sources": required_total, "fully_materialized": full, "partially_materialized": partial, "not_materialized": missing, "no_outputs_declared": no_outputs, "required_fully_materialized": required_full},
        "processed_file_inventory": {"processed_dir": "data/staging/processed", "total_csv_files": len(inventory), "total_rows_on_disk": total_rows, "registry_accounted_rows": accounted_rows, "measured_orphan_rows": measured_orphan_rows, "measured_orphan_file_count": measured_orphan_files, "orphan_rows": certifiable_orphan_rows, "orphan_file_count": certifiable_orphan_files, "files": inventory},
        "sources": source_rows,
    }

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default="."); parser.add_argument("--output", default="reports/materialization_coverage_audit.current.json"); parser.add_argument("--operator-corpus-authoritative", action="store_true"); args = parser.parse_args()
    root = Path(args.root).resolve(); output = Path(args.output)
    if not output.is_absolute(): output = Path.cwd() / output
    report = build(root, operator_corpus_authoritative=args.operator_corpus_authoritative)
    output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["local_truth_summary"], sort_keys=True)); print(json.dumps({"operator_corpus_authoritative": report["audit_scope"]["operator_corpus_authoritative"], "measured_orphan_rows": report["processed_file_inventory"]["measured_orphan_rows"], "certifiable_orphan_rows": report["processed_file_inventory"]["orphan_rows"]}, sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
