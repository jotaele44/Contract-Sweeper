"""Mapping/partition behavior for the Tranche B intake (pandas-backed).

Skipped when pandas is absent (offline dev shell); runs in CI where pandas is
installed. Covers two intake-correctness guarantees:

* map_frame coalesces per row across candidate columns (amount_numeric -> amount_raw)
  instead of committing to one column and blanking rows the preferred column missed;
* a spec with a dataset_filter refuses to ingest a file that lacks the partition
  column, instead of falling through and mapping another source's rows into it.
"""

from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

from scripts import source_intake_tranche_b as tb  # noqa: E402
from scripts.source_intake_helpers import LoadedTable, map_frame  # noqa: E402


def test_map_frame_coalesces_amount_numeric_then_raw():
    frame = pd.DataFrame(
        {
            "amount_numeric": ["100.00", "", "50.00"],
            "amount_raw": ["$100", "$ -", "$50"],
        }
    )
    out = map_frame(frame, {"amount": ["amount_numeric", "amount_raw"]}, ["amount"], "src", "f.csv")
    # Row 2's blank numeric parse falls back to the raw amount token rather than blanking.
    assert list(out["amount"]) == ["100.00", "$ -", "50.00"]


def test_single_candidate_mapping_is_unchanged():
    frame = pd.DataFrame({"Monto": ["1", "", "3"]})
    out = map_frame(frame, {"amount": ["amount", "Monto"]}, ["amount"], "src", "f.csv")
    assert list(out["amount"]) == ["1", "", "3"]


def test_dataset_filter_skips_unpartitioned_file(tmp_path, monkeypatch):
    spec = next(s for s in tb.SOURCE_SPECS.values() if s.dataset_filter)
    # An operator file for one source lacking the source_dataset partition column.
    frame = pd.DataFrame({"contract_number": ["C1", "C2"], "amount_raw": ["$1", "$2"]})
    monkeypatch.setattr(
        tb, "load_tabular_dropzone", lambda _dz: [LoadedTable(path=Path("op.csv"), frame=frame)]
    )
    result = tb.materialize_spec(tmp_path, spec, force=True)
    # Skipped (0 rows) rather than mislabeling foreign rows as this source's dataset.
    assert result["rows"] == 0
