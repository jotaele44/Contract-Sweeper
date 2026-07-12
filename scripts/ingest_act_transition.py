"""Promote extracted ACT/ACUDEN transition contracts to canonical processed CSVs.

This is the registry ``producer_script`` for two manual-export sources:

  - ``act_transition_contracts`` → ``data/staging/processed/pr_act_transition_contracts.csv``
  - ``acuden_2024_transition``   → ``data/staging/processed/pr_acuden_transition.csv``

It closes the gap between the PDF extractor (``scripts/extract_act_acuden_pdfs.py``,
which writes per-PDF 6-column CSVs under ``data/staging/raw/``) and the canonical
``data/staging/processed/`` outputs the registry declares. The acquired source
PDFs are archived in ``data/raw/Vigentes al Momento de Transición/`` (per-source
globs); pass ``--from-pdf`` to re-extract from them — the default run stays on
the deterministic committed-extract path below.

Offline fallback: when no operator PDF (or pre-staged raw CSV) is available, the
producer materializes directly from the committed 18-column extract written by
``scripts/build_act_transition_extract.py`` at ``data/raw/act_transition/
transition_contracts_extracted.csv`` (one dataset per source key). That file is
git-tracked, so the declared output is reproducible end-to-end with no PDF and no
network — the offline path proven by tests/test_act_transition_materialization.py.

No network. With neither a PDF, a staged raw CSV, nor the committed extract
present, the producer is a clean no-op (writes nothing, reports ``EMPTY``).

Usage:
  python3 scripts/ingest_act_transition.py                 # both sources
  python3 scripts/ingest_act_transition.py --source act
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.config import PROJECT_ROOT, setup_logging

# Source metadata mirrored locally so this module imports WITHOUT pulling in
# pdfplumber (the readiness preflight imports every producer module — it must
# not require the heavy PDF stack). The extractor is imported lazily, only when
# we actually run an extraction. Keep these in sync with
# scripts/extract_act_acuden_pdfs.py::SOURCES.
SOURCE_META = {
    "act": {"label": "act_transition_contracts", "output_dir": "data/staging/raw/act_transition"},
    "acuden": {"label": "acuden_2024_transition", "output_dir": "data/staging/raw/acuden_2024"},
}

# source_key -> registry expected_output
PROCESSED_OUTPUTS = {
    "act": "data/staging/processed/pr_act_transition_contracts.csv",
    "acuden": "data/staging/processed/pr_acuden_transition.csv",
}

# Offline fallback input: the committed 18-column extract from
# scripts/build_act_transition_extract.py, one `source_dataset` per source key.
COMMITTED_EXTRACT = "data/raw/act_transition/transition_contracts_extracted.csv"
EXTRACT_DATASET = {"act": "ACT_2020", "acuden": "ACUDEN_2024"}

# Where the acquired source PDFs actually live (committed; spaces-in-name dir
# has a dedicated .gitignore carve-out). Per-source globs keep the shared
# archive dir split correctly. Mirrors scripts/extract_act_acuden_pdfs.py.
PDF_ARCHIVE_DIR = "data/raw/Vigentes al Momento de Transición"
PDF_NAME_GLOB = {"act": "ACT*.pdf", "acuden": "ACUDES*.pdf"}

# Canonical processed schema: extractor's 6 columns + a provenance tag.
CANONICAL_COLUMNS = [
    "source_dataset",
    "contractor_name",
    "contract_number",
    "start_date",
    "end_date",
    "amount",
    "service_type",
]


def promote_rows(rows: list[dict], source_key: str) -> list[dict]:
    """Map extractor rows to the canonical processed schema. Pure — no I/O.

    Drops rows with neither a contractor nor a contract number, tags each row
    with its source dataset, and deduplicates on (contract_number,
    contractor_name).
    """
    label = SOURCE_META[source_key]["label"]
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        contractor = (row.get("contractor_name") or "").strip()
        contract = (row.get("contract_number") or "").strip()
        if not contractor and not contract:
            continue
        key = (contract, contractor)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source_dataset": label,
                "contractor_name": contractor,
                "contract_number": contract,
                "start_date": (row.get("start_date") or "").strip(),
                "end_date": (row.get("end_date") or "").strip(),
                "amount": (row.get("amount") or "").strip(),
                "service_type": (row.get("service_type") or "").strip(),
            }
        )
    return out


def _read_staged_rows(root: Path, source_key: str) -> list[dict]:
    out_dir = root / SOURCE_META[source_key]["output_dir"]
    if not out_dir.exists():
        return []
    rows: list[dict] = []
    for csv_path in sorted(out_dir.glob("*.csv")):
        with csv_path.open(encoding="utf-8", newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def _write_processed(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _pdf_available(root: Path, source_key: str, input_dir: Path | None) -> bool:
    """True if this source's archived PDF is present (extractor worth importing)."""
    if input_dir is not None:
        return input_dir.exists() and any(p.suffix.lower() == ".pdf" for p in input_dir.iterdir())
    archive = root / PDF_ARCHIVE_DIR
    return archive.exists() and any(archive.glob(PDF_NAME_GLOB[source_key]))


def _read_committed_extract_rows(root: Path, source_key: str) -> list[dict]:
    """Offline fallback rows from the committed 18-column extract.

    Maps the extract's raw-date / numeric-amount columns onto the six fields
    ``promote_rows`` consumes, filtered to this source's ``source_dataset``. No
    PDF, no network — used only when no operator-supplied input has been staged.
    """
    path = root / COMMITTED_EXTRACT
    if not path.exists():
        return []
    dataset = EXTRACT_DATASET[source_key]
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("source_dataset") or "").strip() != dataset:
                continue
            rows.append(
                {
                    "contractor_name": r.get("contractor_name", ""),
                    "contract_number": r.get("contract_number", ""),
                    "start_date": r.get("start_date_raw", ""),
                    "end_date": r.get("end_date_raw", ""),
                    "amount": r.get("amount_numeric") or r.get("amount_raw", ""),
                    "service_type": r.get("service_type", ""),
                }
            )
    return rows


def materialize_source(
    root: Path, source_key: str, input_dir: Path | None, logger, *, from_pdf: bool = False
) -> dict:
    """Materialize one source to its processed CSV.

    Input tiers: (1) a fresh PDF extraction — only when ``from_pdf`` is set,
    since the archived source PDFs are always present in this repo and the
    default run must stay deterministic (committed-extract path) and free of
    the pdfplumber stack; (2) pre-staged raw CSVs; (3) the committed offline
    extract. ``pdfplumber`` is imported only when a PDF extraction actually
    runs, so the readiness preflight that imports this module never touches it.
    """
    if from_pdf and _pdf_available(root, source_key, input_dir):
        # Lazy import — keeps module import (and the readiness preflight) free of pdfplumber.
        from moneysweep.runtime.alias_overrides import load_overrides
        from scripts.extract_act_acuden_pdfs import extract_source

        overrides = load_overrides()
        extract_source(
            source_key, root, overrides, dry_run=False, input_override=input_dir, logger=logger
        )

    staged = _read_staged_rows(root, source_key)
    origin = "staged extract"
    if not staged:
        staged = _read_committed_extract_rows(root, source_key)
        origin = "committed extract (offline)"

    promoted = promote_rows(staged, source_key)
    out_path = root / PROCESSED_OUTPUTS[source_key]
    if not promoted:
        logger.info(f"  [{source_key}] no rows to promote (drop a PDF first) — EMPTY")
        return {"source": source_key, "status": "EMPTY", "rows": 0, "output": str(out_path)}
    _write_processed(promoted, out_path)
    logger.info(
        f"  [{source_key}] {len(promoted)} rows → {PROCESSED_OUTPUTS[source_key]} [{origin}]"
    )
    return {"source": source_key, "status": "OK", "rows": len(promoted), "output": str(out_path)}


def run(
    root: Path | None = None,
    source: str = "all",
    input_dir: Path | None = None,
    from_pdf: bool = False,
) -> dict:
    root = Path(root or PROJECT_ROOT)
    logger = setup_logging("ingest_act_transition")
    keys = list(PROCESSED_OUTPUTS) if source == "all" else [source]
    if input_dir is not None and source == "all":
        raise ValueError("--input-dir requires --source act or --source acuden")
    if input_dir is not None:
        from_pdf = True  # an explicit operator drop implies re-extraction
    results = [materialize_source(root, k, input_dir, logger, from_pdf=from_pdf) for k in keys]
    total = sum(r["rows"] for r in results)
    return {"status": "OK" if total else "EMPTY", "rows": total, "sources": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["act", "acuden", "all"], default="all")
    parser.add_argument("--input-dir", type=Path, default=None)
    parser.add_argument(
        "--from-pdf",
        action="store_true",
        help="re-extract from the archived source PDFs (needs pdfplumber); "
        "default is the deterministic committed-extract/staged path",
    )
    args = parser.parse_args(argv)
    result = run(source=args.source, input_dir=args.input_dir, from_pdf=args.from_pdf)
    return 0 if result["rows"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
