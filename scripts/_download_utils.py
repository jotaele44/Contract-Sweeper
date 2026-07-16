"""
Shared helpers used across download and ingest scripts.

Usage:
    from scripts._download_utils import file_has_data, derive_fiscal_year
"""

from pathlib import Path

import pandas as pd


def file_has_data(filepath: Path) -> bool:
    """Return True if file exists and has at least one data row."""
    if not filepath.exists():
        return False
    try:
        df = pd.read_csv(filepath, dtype=str, nrows=2, low_memory=False)
        return len(df) > 0
    except Exception:
        return False


def derive_fiscal_year(date_str) -> str:
    """Derive US federal fiscal year from a date string. Oct-Dec → year+1."""
    if not date_str or pd.isna(date_str):
        return ""
    try:
        d = pd.to_datetime(str(date_str), errors="coerce")
        if pd.isna(d):
            return ""
        return str(d.year + 1) if d.month >= 10 else str(d.year)
    except Exception:
        return ""
