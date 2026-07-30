"""Ingest Puerto Rico CEE/CEEPUR campaign-donation exports.

Accepts CSV and Excel exports in ``data/raw/Donaciones/`` and normalizes the
historical and recent donor-search layouts into one canonical table.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from scripts.campaign_finance_common import (
    clean_amount_series,
    clean_date_series,
    derive_cycle,
    iter_tabular_frames,
    text_series,
)
from scripts.config import PROJECT_ROOT, setup_logging

RAW_DIR_NAME = "data/raw/Donaciones"

OUTPUT_COLUMNS = [
    "cycle",
    "donor_name",
    "donor_city",
    "donor_zip_code",
    "donor_employer",
    "donor_occupation",
    "amount",
    "contribution_date",
    "candidate_or_committee",
    "party",
    "office_sought",
    "election_type",
    "report_type",
    "candidacy_type",
    "payment_method",
    "event_name",
    "source_file",
]

COL_MAP = {
    "cycle": ["ciclo", "cycle", "año_eleccion", "ano_eleccion", "election_year", "año electoral"],
    "donor_name": [
        "nombre_donante",
        "nombre donante",
        "donante",
        "donor_name",
        "nombre_contribuyente",
        "contribuyente",
        "nombre completo",
        "nombre",
    ],
    "donor_city": ["ciudad_donante", "ciudad", "city", "donor_city", "municipio", "pueblo"],
    "donor_zip_code": ["zip_donante", "zip", "zip code", "codigo_postal", "postal_code", "donor_zip"],
    "donor_employer": ["patrono", "empleador", "employer", "donor_employer", "empleo"],
    "donor_occupation": ["ocupacion", "ocupación", "occupation", "donor_occupation", "profesion", "profesión"],
    "amount": ["cantidad", "monto", "amount", "contribucion", "contribution_amount", "donativo", "donación"],
    "contribution_date": [
        "fecha_donacion",
        "fecha donacion",
        "fecha de donación",
        "fecha de donacion",
        "fecha",
        "date",
        "contribution_date",
        "fecha_contribucion",
    ],
    "candidate_or_committee": [
        "candidato_comite",
        "candidato",
        "comite",
        "comité",
        "candidate",
        "committee",
        "candidato_o_comite",
        "nombre_comite",
    ],
    "party": [
        "partido",
        "party",
        "partido_politico",
        "partido político",
        "partido de afiliación",
        "partido de afiliacion",
        "siglas",
    ],
    "office_sought": ["cargo", "puesto", "office", "office_sought", "posicion", "posición"],
    "election_type": ["tipo_eleccion", "tipo eleccion", "election_type", "tipo", "eleccion", "elección"],
    "report_type": ["tipo_informe", "informe", "report_type", "report", "tipo_reporte"],
    "candidacy_type": ["candidatura", "candidacy_type", "tipo_candidatura"],
    "payment_method": [
        "metodo",
        "método",
        "payment_method",
        "metodo_pago",
        "método de cobro",
        "metodo de cobro",
    ],
    "event_name": ["evento", "event", "event_name", "evento electoral"],
}


def _parse_df(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    out = {target: text_series(df, candidates) for target, candidates in COL_MAP.items()}
    out_df = pd.DataFrame(out)
    out_df["source_file"] = source_file
    out_df["amount"] = clean_amount_series(out_df["amount"])
    out_df["contribution_date"] = clean_date_series(out_df["contribution_date"])
    missing_cycle = out_df["cycle"].eq("")
    out_df.loc[missing_cycle, "cycle"] = [
        derive_cycle(event, date)
        for event, date in zip(
            out_df.loc[missing_cycle, "event_name"],
            out_df.loc[missing_cycle, "contribution_date"],
        )
    ]
    for col in OUTPUT_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = ""
    donor = out_df["donor_name"].fillna("").astype(str).str.strip()
    amount = out_df["amount"].fillna("").astype(str).str.strip()
    out_df = out_df[(donor != "") & (donor.str.lower() != "nan") & (amount != "")]
    return out_df[OUTPUT_COLUMNS]


def run(root: Path | None = None, force: bool = False) -> dict:
    root = Path(root) if root is not None else PROJECT_ROOT
    raw_dir = root / RAW_DIR_NAME
    out_path = root / "data" / "staging" / "processed" / "pr_donaciones.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    logger = setup_logging("ingest_donaciones")

    if not force and out_path.exists():
        existing = pd.read_csv(out_path, dtype=str, low_memory=False)
        if len(existing) > 0:
            logger.info(f"  Cached — {len(existing):,} rows in {out_path.name}")
            return {"rows": len(existing), "path": str(out_path), "status": "CACHED"}

    files = [] if not raw_dir.exists() else sorted(
        f for f in raw_dir.iterdir()
        if f.suffix.lower() in {".csv", ".xlsx", ".xls"} and not f.name.startswith("~")
    )
    if not files:
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {"rows": 0, "path": str(out_path), "status": "NO_FILES"}

    frames: list[pd.DataFrame] = []
    file_rows: dict[str, int] = {}
    for path in files:
        logger.info(f"  Reading {path.name}...")
        count = 0
        try:
            for frame in iter_tabular_frames(path):
                parsed = _parse_df(frame, path.name)
                count += len(parsed)
                frames.append(parsed)
            file_rows[path.name] = count
            logger.info(f"    → {count:,} donation rows after mapping")
        except Exception as exc:
            logger.warning(f"  Could not parse {path.name}: {exc}")

    if not frames:
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(out_path, index=False, encoding="utf-8")
        return {"rows": 0, "path": str(out_path), "status": "EMPTY", "files": file_rows}

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(
        subset=["donor_name", "candidate_or_committee", "contribution_date", "amount", "party"],
        keep="first",
    )
    combined.to_csv(out_path, index=False, encoding="utf-8")
    return {
        "rows": len(combined),
        "deduplicated_rows": before - len(combined),
        "path": str(out_path),
        "status": "OK" if len(combined) else "EMPTY",
        "files": file_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force)
    print(f"\nCEE donations: {result['rows']:,} rows — {result['status']}")
    return 0 if result["status"] not in {"EMPTY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
