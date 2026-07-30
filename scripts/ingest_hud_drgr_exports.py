"""Load authorized local HUD DRGR exports without credential automation.

Inputs are operator-exported CSV/XLS/XLSX files under ``data/manual/hud_drgr/``
or documented legacy HUD raw directories.

Canonical registry outputs:
  data/staging/processed/hud_drgr_activities.csv
  data/staging/processed/hud_drgr_projects.csv

Normalized analytical outputs retained for downstream consumers:
  data/normalized/hud_drgr_activities.parquet
  data/normalized/hud_drgr_drawdowns.parquet
  data/normalized/hud_drgr_appropriations.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_unified_master import _normalize_name
from scripts.config import PROJECT_ROOT, setup_logging
from scripts.parquet_utils import pq_read, pq_write

RAW_RELATIVE_DIRS = (
    "data/manual/hud_drgr",
    "data/raw",
    "data/raw/HUD DRGR",
    "data/raw/HUD",
    "data/raw/hud_drgr",
    "data/raw/hud",
)
HUD_DRGR_FILENAME_KEYWORDS = ("hud", "drgr", "cdbg")

ACTIVITY_COLUMNS = [
    "activity_id", "grant_number", "project_id", "activity_name", "activity_type",
    "status", "responsible_org", "responsible_org_normalized", "address",
    "municipality", "county", "national_objective", "benefit_type", "total_budget",
    "amount_drawn", "amount_remaining", "start_date", "end_date", "source_file",
]
DRAWDOWN_COLUMNS = [
    "drawdown_id", "grant_number", "activity_id", "drawdown_date", "drawdown_amount",
    "cumulative_drawn", "remaining_budget", "source_file",
]
APPROPRIATION_COLUMNS = [
    "appropriation_id", "grant_number", "program_type", "appropriation_year",
    "appropriation_amount", "allocation_date", "grantee_name", "grantee_normalized",
    "cfda_number", "source_file",
]
PROJECT_COLUMNS = [
    "project_id", "grant_number", "project_name", "responsible_org",
    "responsible_org_normalized", "municipality", "status", "total_budget",
    "amount_drawn", "amount_remaining", "activity_count", "source_file",
]

ACTIVITY_COL_MAP = {
    "activity_id": ["Activity ID", "Activity Number", "Activity #", "activity_id", "id"],
    "grant_number": ["Grant Number", "Grant #", "CDBG Grant", "grant_number", "Grant"],
    "project_id": ["Project ID", "Project Number", "Project #", "project_id"],
    "activity_name": ["Activity Name", "Activity Description", "Name", "activity_name"],
    "activity_type": ["Activity Type", "Type", "Category", "activity_type"],
    "status": ["Status", "Activity Status", "Current Status", "status"],
    "responsible_org": ["Responsible Organization", "Responsible Org", "Organization", "Subrecipient", "responsible_org"],
    "address": ["Address", "Location", "Site Address", "address"],
    "municipality": ["Municipality", "City", "Locality", "municipality"],
    "county": ["County", "county"],
    "national_objective": ["National Objective", "HUD National Objective", "Objective"],
    "benefit_type": ["Benefit Type", "Benefit", "LMI"],
    "total_budget": ["Total Budget", "Budget Amount", "Allocation", "Approved Amount"],
    "amount_drawn": ["Amount Drawn", "Drawn", "Disbursed", "Expended"],
    "amount_remaining": ["Amount Remaining", "Balance", "Remaining"],
    "start_date": ["Start Date", "Begin Date"],
    "end_date": ["End Date", "Completion Date"],
}
DRAWDOWN_COL_MAP = {
    "drawdown_id": ["Drawdown ID", "Draw ID", "Transaction ID", "drawdown_id"],
    "grant_number": ["Grant Number", "Grant #", "grant_number"],
    "activity_id": ["Activity ID", "Activity Number", "activity_id"],
    "drawdown_date": ["Drawdown Date", "Date", "Transaction Date", "drawdown_date"],
    "drawdown_amount": ["Drawdown Amount", "Amount", "Draw Amount", "drawdown_amount"],
    "cumulative_drawn": ["Cumulative Drawn", "Cumulative", "Total Drawn"],
    "remaining_budget": ["Remaining Budget", "Balance"],
}
APPROPRIATION_COL_MAP = {
    "appropriation_id": ["Appropriation ID", "ID", "appropriation_id"],
    "grant_number": ["Grant Number", "Grant", "grant_number"],
    "program_type": ["Program Type", "Program", "Type"],
    "appropriation_year": ["Year", "Appropriation Year", "FY"],
    "appropriation_amount": ["Amount", "Appropriation Amount", "Total Amount"],
    "allocation_date": ["Date", "Allocation Date"],
    "grantee_name": ["Grantee Name", "Grantee", "Recipient"],
    "cfda_number": ["CFDA", "CFDA Number", "Assistance Listing"],
}
CLASSIFY_KEYWORDS = {
    "drawdowns": ["drawdown", "draw ", "disbursement", "payment", "transaction"],
    "activities": ["activit", "project_list", "projectlist"],
    "appropriations": ["appropriat", "allocation", " grant list", "grantlist"],
}


def _map_col(df_cols, candidates):
    cols_lower = {str(column).lower().strip(): column for column in df_cols}
    for candidate in candidates:
        if candidate in df_cols:
            return candidate
        actual = cols_lower.get(candidate.lower())
        if actual is not None:
            return actual
    return None


def _read_file(path: Path, logger) -> pd.DataFrame:
    try:
        if path.suffix.lower() in {".xlsx", ".xls"}:
            workbook = pd.ExcelFile(path)
            frames = []
            for sheet in workbook.sheet_names:
                try:
                    frame = pd.read_excel(workbook, sheet_name=sheet, dtype=str, na_filter=False)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"  Failed sheet {sheet!r} in {path.name}: {exc}")
                    continue
                if not frame.empty:
                    frames.append(frame)
            return max(frames, key=len) if frames else pd.DataFrame()
        if path.suffix.lower() == ".csv":
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    return pd.read_csv(path, dtype=str, na_filter=False, encoding=encoding, low_memory=False)
                except UnicodeDecodeError:
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"  Failed to read {path.name}: {exc}")
    return pd.DataFrame()


def _classify(path: Path, frame: pd.DataFrame) -> str:
    combined = path.stem.lower() + " " + " ".join(str(c).lower() for c in frame.columns)
    scores = {category: sum(keyword in combined for keyword in keywords) for category, keywords in CLASSIFY_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "activities"


def _map_to_schema(frame, column_map, columns, source_file):
    output = {}
    for output_column, candidates in column_map.items():
        source_column = _map_col(frame.columns.tolist(), candidates)
        output[output_column] = frame[source_column] if source_column else ""
    result = pd.DataFrame(output, index=frame.index)
    result["source_file"] = source_file
    for column in columns:
        if column not in result.columns:
            result[column] = ""
    return result[columns]


def _looks_like_hud_drgr(path: Path) -> bool:
    name = path.name.lower()
    parent = path.parent.name.lower()
    return any(keyword in name or keyword in parent for keyword in HUD_DRGR_FILENAME_KEYWORDS)


def _find_raw_files(root: Path, logger) -> list[Path]:
    candidates: set[Path] = set()
    for relative in RAW_RELATIVE_DIRS:
        raw_dir = root / relative
        if not raw_dir.exists():
            continue
        for pattern in ("*.xlsx", "*.xls", "*.csv"):
            candidates.update(path for path in raw_dir.glob(pattern) if not path.name.startswith("."))
        for child in raw_dir.iterdir():
            if child.is_dir():
                for pattern in ("*.xlsx", "*.xls", "*.csv"):
                    candidates.update(path for path in child.glob(pattern) if not path.name.startswith("."))
    relevant = sorted(path for path in candidates if _looks_like_hud_drgr(path))
    logger.info(f"  Found {len(relevant)} HUD DRGR export file(s)")
    return relevant


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.fillna("").astype(str).str.replace(r"[$,\s]", "", regex=True), errors="coerce").fillna(0)


def _build_projects(activities: pd.DataFrame) -> pd.DataFrame:
    if activities.empty or "project_id" not in activities:
        return pd.DataFrame(columns=PROJECT_COLUMNS)
    source = activities.copy()
    source["project_id"] = source["project_id"].fillna("").astype(str).str.strip()
    source = source[source["project_id"] != ""].copy()
    if source.empty:
        return pd.DataFrame(columns=PROJECT_COLUMNS)
    for column in ("total_budget", "amount_drawn", "amount_remaining"):
        source[column] = _numeric(source[column])
    projects = source.groupby("project_id", sort=True, dropna=False).agg(
        grant_number=("grant_number", "first"),
        project_name=("activity_name", "first"),
        responsible_org=("responsible_org", "first"),
        responsible_org_normalized=("responsible_org_normalized", "first"),
        municipality=("municipality", "first"),
        status=("status", "first"),
        total_budget=("total_budget", "sum"),
        amount_drawn=("amount_drawn", "sum"),
        amount_remaining=("amount_remaining", "sum"),
        activity_count=("activity_id", "count"),
        source_file=("source_file", lambda values: "|".join(sorted(set(values)))),
    ).reset_index()
    return projects[PROJECT_COLUMNS]


def _write_outputs(frame: pd.DataFrame, columns: list[str], parquet_path: Path, csv_path: Path | None = None) -> int:
    materialized = frame if not frame.empty else pd.DataFrame(columns=columns)
    pq_write(materialized, parquet_path)
    if csv_path is not None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        materialized.to_csv(csv_path, index=False, encoding="utf-8")
    return len(materialized)


def run(root=None, force=False):
    root = Path(root or PROJECT_ROOT)
    normalized_dir = root / "data" / "normalized"
    processed_dir = root / "data" / "staging" / "processed"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logging("ingest_hud_drgr_exports")

    activity_parquet = normalized_dir / "hud_drgr_activities.parquet"
    project_parquet = normalized_dir / "hud_drgr_projects.parquet"
    drawdown_parquet = normalized_dir / "hud_drgr_drawdowns.parquet"
    appropriation_parquet = normalized_dir / "hud_drgr_appropriations.parquet"
    activity_csv = processed_dir / "hud_drgr_activities.csv"
    project_csv = processed_dir / "hud_drgr_projects.csv"

    normalized_paths = [activity_parquet, project_parquet, drawdown_parquet, appropriation_parquet]
    if not force and all(path.exists() or path.with_suffix(".csv").exists() for path in normalized_paths):
        activities = pq_read(activity_parquet)
        projects = pq_read(project_parquet)
        drawdowns = pq_read(drawdown_parquet)
        appropriations = pq_read(appropriation_parquet)
        activities.to_csv(activity_csv, index=False, encoding="utf-8")
        projects.to_csv(project_csv, index=False, encoding="utf-8")
        return {
            "activity_rows": len(activities), "project_rows": len(projects),
            "drawdown_rows": len(drawdowns), "appropriation_rows": len(appropriations),
            "status": "CACHED",
        }

    files = _find_raw_files(root, logger)
    activity_frames = []
    drawdown_frames = []
    appropriation_frames = []
    for path in files:
        frame = _read_file(path, logger)
        if frame.empty:
            continue
        category = _classify(path, frame)
        if category == "drawdowns":
            drawdown_frames.append(_map_to_schema(frame, DRAWDOWN_COL_MAP, DRAWDOWN_COLUMNS, path.name))
        elif category == "appropriations":
            mapped = _map_to_schema(frame, APPROPRIATION_COL_MAP, APPROPRIATION_COLUMNS, path.name)
            mapped["grantee_normalized"] = mapped["grantee_name"].apply(_normalize_name)
            appropriation_frames.append(mapped)
        else:
            mapped = _map_to_schema(frame, ACTIVITY_COL_MAP, ACTIVITY_COLUMNS, path.name)
            mapped["responsible_org_normalized"] = mapped["responsible_org"].apply(_normalize_name)
            activity_frames.append(mapped)

    activities = pd.concat(activity_frames, ignore_index=True) if activity_frames else pd.DataFrame(columns=ACTIVITY_COLUMNS)
    drawdowns = pd.concat(drawdown_frames, ignore_index=True) if drawdown_frames else pd.DataFrame(columns=DRAWDOWN_COLUMNS)
    appropriations = pd.concat(appropriation_frames, ignore_index=True) if appropriation_frames else pd.DataFrame(columns=APPROPRIATION_COLUMNS)
    projects = _build_projects(activities)

    activity_rows = _write_outputs(activities, ACTIVITY_COLUMNS, activity_parquet, activity_csv)
    project_rows = _write_outputs(projects, PROJECT_COLUMNS, project_parquet, project_csv)
    drawdown_rows = _write_outputs(drawdowns, DRAWDOWN_COLUMNS, drawdown_parquet)
    appropriation_rows = _write_outputs(appropriations, APPROPRIATION_COLUMNS, appropriation_parquet)
    return {
        "activity_rows": activity_rows, "project_rows": project_rows,
        "drawdown_rows": drawdown_rows, "appropriation_rows": appropriation_rows,
        "status": "OK" if files else "manual_required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(force=args.force)
    print(
        "HUD DRGR exports: "
        f"{result['activity_rows']:,} activities, {result['project_rows']:,} projects, "
        f"{result['drawdown_rows']:,} drawdowns, {result['appropriation_rows']:,} appropriations"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
