"""Pandas-free path and dataset reconciliation for source-intake dropzones.

Split out of :mod:`scripts.source_intake_helpers` so dropzone discovery and the
shared-extract dataset partitioning can be unit-tested without importing the
pipeline's heavy tabular dependencies (pandas / openpyxl). Everything here is
stdlib-only.
"""

from __future__ import annotations

from pathlib import Path

SUPPORTED_TABULAR_SUFFIXES = {".csv", ".xlsx", ".xls"}

# Column that partitions a single combined operator extract into per-source
# rows. The ACT/ACUDEN transition-contracts extract
# (``data/raw/act_transition/transition_contracts_extracted.csv``) is one file
# that carries rows for both datasets, distinguished by this column.
DATASET_PARTITION_COLUMN = "source_dataset"

# ``SourceSpec.source_id`` -> the dataset token it owns inside a shared combined
# extract. ACT and ACUDEN share the ``data/raw/act_transition`` dropzone and the
# same committed extract file, so each must select only its own rows instead of
# ingesting (and mislabelling) the other's. Specs not listed here consume every
# row found in their dropzone.
SHARED_EXTRACT_DATASET_FILTERS: dict[str, str] = {
    "act_transition_contracts": "ACT_2020",
    "acuden_2024_transition": "ACUDEN_2024",
}


def discover_tabular_files(dropzone: Path) -> list[Path]:
    """Return the sorted tabular files directly inside ``dropzone``.

    Stdlib-only path-resolution primitive: the intake controllers use it to
    decide whether a dropzone actually holds data. A missing dropzone yields an
    empty list rather than raising.
    """

    dropzone = Path(dropzone)
    if not dropzone.exists():
        return []
    return [
        path
        for path in sorted(dropzone.iterdir())
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_TABULAR_SUFFIXES
        and not path.name.startswith("~")
    ]


def dropzone_has_tabular_data(dropzone: Path) -> bool:
    """True when the dropzone contains at least one readable tabular file."""

    return bool(discover_tabular_files(dropzone))
