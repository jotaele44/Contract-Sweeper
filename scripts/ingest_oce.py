"""Ingest OCE campaign-finance donation and report exports.

Files in ``data/raw/OCE/`` may be CSV or Excel. Donation rows are normalized to
exactly the same schema as ``pr_donaciones.csv``. Report-search exports are
written separately to ``pr_oce_reports.csv``.
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
    find_column,
    iter_tabular_frames,
    text_series,
)
from scripts.config import PROJECT_ROOT, setup_logging

RAW_DIR_NAME = "data/raw/OCE"

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

REPORT_COLUMNS = [
    "committee_name",
    "report_number",
    "report_type",
    "election_event",
    "reporting_period",
    "filed_at",
    "source_file",
]

COL_MAP = {
    "cycle": ["ciclo", "cycle", "anio_electoral", "año_electoral", "election_year"],
    "donor_name": [
        "nombre_donante",
        "nombre donante",
        "donante",
        "donor_name",
        "contribuyente",
        "nombre_contribuyente",
        "nombre_completo",
        "nombre completo",
        "nombre",
    ],
    "donor_city": [
        "ciudad",
        "ciudad_donante",
        "municipio",
        "city",
        "donor_city",
        "donante_pueblo",
        "pueblo",
    ],
    "donor_zip_code": [
        "zip",
        "zip code",
        "zip_code",
        "codigo_postal",
        "código_postal",
        "donor_zip",
    ],
    "donor_employer": ["patrono", "empleador", "empleo", "employer", "donor_employer"],
    "donor_occupation": ["ocupacion", "ocupación", "profesion", "profesión", "occupation"],
    "amount": [
        "cantidad",
        "cantidad_donacion",
        "monto",
        "amount",
        "contribucion",
        "contribución",
        "donativo",
    ],
    "contribution_date": [
        "fecha",
        "fecha_donacion",
        "fecha_contribucion",
        "fecha_donación",
        "fecha_contribución",
        "date",
        "contribution_date",
    ],
    "candidate_or_committee": [
        "candidato",
        "candidato_comite",
        "candidato_comité",
        "candidate",
        "committee",
        "candidate_or_committee",
        "nombre_comite",
        "nombre_comité",
        "comite",
        "comité",
    ],
    "party": [
        "siglas",
        "partido",
        "partido_politico",
        "partido_político",
        "partido de afiliación",
        "partido de afiliacion",
        "party",
    ],
    "office_sought": ["cargo", "puesto", "posicion", "posición", "office", "office_sought"],
    "election_type": [
        "tipo_eleccion",
        "tipo_elección",
        "tipo",
        "eleccion",
        "elección",
        "election_type",
    ],
    "report_type": ["tipo_informe", "informe", "tipo_reporte", "report_type", "report"],
    "candidacy_type": ["candidatura", "candidacy_type", "tipo_candidatura"],
    "payment_method": [
        "metodo",
        "método",
        "metodo_donacion",
        "método de cobro",
        "metodo de cobro",
        "payment_method",
    ],
    "event_name": ["evento", "descripcion_evento", "descripción_evento", "event", "event_name"],
}

REPORT_MAP = {
    "committee_name": ["comite", "comité", "committee"],
    "report_number": ["numero de informe", "número de informe", "report_number"],
    "report_type": ["tipo de informe", "tipo_informe", "report_type"],
    "election_event": ["evento electoral", "evento_electoral", "election_event"],
    "reporting_period": ["periodo del informe", "período del informe", "reporting_period"],
    "filed_at": ["fecha de radicacion", "fecha de radicación", "filed_at", "filing_date"],
}


def _is_report_frame(df: pd.DataFrame) -> bool:
    return find_column(df, REPORT_MAP["report_number"]) is not None


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
    donor = out_df["donor_name"].fillna("").astype(str).str.strip()
    amount = out_df["amount"].fillna("").astype(str).str.strip()
    evidence_fields = [
        "amount",
        "contribution_date",
        "candidate_or_committee",
        "party",
        "event_name",
    ]
    has_evidence = pd.Series(False, index=out_df.index)
    for field in evidence_fields:
        values = out_df[field].fillna("").astype(str).str.strip()
        has_evidence = has_evidence | ((values != "") & (values.str.lower() != "nan"))
    out_df = out_df[(donor != "") & (donor.str.lower() != "nan") & has_evidence]
    for col in OUTPUT_COLUMNS:
        if col not in out_df.columns:
            out_df[col] = ""
    return out_df[OUTPUT_COLUMNS]


def _parse_report_df(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    out = {target: text_series(df, candidates) for target, candidates in REPORT_MAP.items()}
    out_df = pd.DataFrame(out)
    out_df["filed_at"] = clean_date_series(out_df["filed_at"])
    out_df["source_file"] = source_file
    committee = out_df["committee_name"].fillna("").astype(str).str.strip()
    report_no = out_df["report_number"].fillna("").astype(str).str.strip()
    out_df = out_df[(committee != "") | (report_no != "")]
    return out_df[REPORT_COLUMNS]


def run(root: Path | None = None, force: bool = False) -> dict:
    root = Path(root) if root is not None else PROJECT_ROOT
    raw_dir = root / RAW_DIR_NAME
    processed = root / "data" / "staging" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    donations_path = processed / "pr_oce_donations.csv"
    reports_path = processed / "pr_oce_reports.csv"
    logger = setup_logging("ingest_oce")

    if not force and donations_path.exists():
        existing = pd.read_csv(donations_path, dtype=str, low_memory=False)
        if len(existing) > 0:
            report_rows = len(pd.read_csv(reports_path, dtype=str)) if reports_path.exists() else 0
            return {
                "rows": len(existing),
                "report_rows": report_rows,
                "path": str(donations_path),
                "reports_path": str(reports_path),
                "status": "CACHED",
            }

    files = (
        []
        if not raw_dir.exists()
        else sorted(
            f
            for f in raw_dir.iterdir()
            if f.suffix.lower() in {".csv", ".xlsx", ".xls"} and not f.name.startswith("~")
        )
    )
    if not files:
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(donations_path, index=False, encoding="utf-8")
        pd.DataFrame(columns=REPORT_COLUMNS).to_csv(reports_path, index=False, encoding="utf-8")
        return {
            "rows": 0,
            "report_rows": 0,
            "path": str(donations_path),
            "reports_path": str(reports_path),
            "status": "NO_FILES",
        }

    donation_frames: list[pd.DataFrame] = []
    report_frames: list[pd.DataFrame] = []
    file_rows: dict[str, dict[str, int]] = {}
    for path in files:
        donation_count = 0
        report_count = 0
        try:
            for frame in iter_tabular_frames(path):
                if _is_report_frame(frame):
                    parsed_reports = _parse_report_df(frame, path.name)
                    report_count += len(parsed_reports)
                    report_frames.append(parsed_reports)
                else:
                    parsed = _parse_df(frame, path.name)
                    donation_count += len(parsed)
                    donation_frames.append(parsed)
            file_rows[path.name] = {"donations": donation_count, "reports": report_count}
        except Exception as exc:
            logger.warning(f"  Could not parse {path.name}: {exc}")

    donations = (
        pd.concat(donation_frames, ignore_index=True)
        if donation_frames
        else pd.DataFrame(columns=OUTPUT_COLUMNS)
    )
    donation_before = len(donations)
    if not donations.empty:
        donations = donations.drop_duplicates(
            subset=["donor_name", "candidate_or_committee", "contribution_date", "amount", "party"],
            keep="first",
        )
    donations.to_csv(donations_path, index=False, encoding="utf-8")

    reports = (
        pd.concat(report_frames, ignore_index=True)
        if report_frames
        else pd.DataFrame(columns=REPORT_COLUMNS)
    )
    report_before = len(reports)
    if not reports.empty:
        reports = reports.drop_duplicates(
            subset=["committee_name", "report_number", "report_type", "filed_at"],
            keep="first",
        )
    reports.to_csv(reports_path, index=False, encoding="utf-8")

    return {
        "rows": len(donations),
        "report_rows": len(reports),
        "deduplicated_rows": donation_before - len(donations),
        "deduplicated_report_rows": report_before - len(reports),
        "path": str(donations_path),
        "reports_path": str(reports_path),
        "status": "OK" if len(donations) or len(reports) else "EMPTY",
        "files": file_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force)
    print(
        f"\nOCE ingest: {result['rows']:,} donations · "
        f"{result['report_rows']:,} reports — {result['status']}"
    )
    return 0 if result["status"] != "EMPTY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
