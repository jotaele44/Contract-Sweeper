"""Shared normalization helpers for Puerto Rico campaign-finance feeds."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd

_HEADER_RE = re.compile(r"[^a-z0-9]+")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def normalize_header(value: object) -> str:
    """Return an accent-insensitive snake_case representation of a column label."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _HEADER_RE.sub("_", text.lower()).strip("_")


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lookup = {normalize_header(col): col for col in df.columns}
    for candidate in candidates:
        actual = lookup.get(normalize_header(candidate))
        if actual is not None:
            return actual
    return None


def text_series(df: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    col = find_column(df, candidates)
    if col is None:
        return pd.Series("", index=df.index, dtype="object")
    return df[col].fillna("").astype(str).str.strip().replace({"nan": "", "NaN": ""})


def clean_amount(value: object) -> str:
    """Normalize currency-like values to a plain decimal string."""
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    negative = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace(" ", "")
    text = text.strip("()")
    try:
        number = float(text)
    except ValueError:
        return str(value).strip()
    if negative:
        number = -number
    if number.is_integer():
        return str(int(number))
    return (f"{number:.10f}").rstrip("0").rstrip(".")


def clean_amount_series(series: pd.Series) -> pd.Series:
    return series.apply(clean_amount)


def clean_date(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    # ISO-like values should not be interpreted with day-first semantics.
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text):
        parsed = pd.to_datetime(text, errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return "" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def clean_date_series(series: pd.Series) -> pd.Series:
    return series.apply(clean_date)


def derive_cycle(event: object, date_value: object) -> str:
    for raw in (event, date_value):
        if raw is None or pd.isna(raw):
            continue
        match = _YEAR_RE.search(str(raw))
        if match:
            return match.group(0)
    return ""


def stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part or "").strip() for part in parts)
    return f"{prefix}_{hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]}"


def iter_tabular_frames(path: Path, chunksize: int = 100_000) -> Iterator[pd.DataFrame]:
    """Yield DataFrames from CSV/Excel with conservative encoding fallbacks."""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        yield pd.read_excel(path, dtype=str)
        return
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            reader = pd.read_csv(
                path, dtype=str, low_memory=False, encoding=encoding, chunksize=chunksize
            )
            yield from reader
            return
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
