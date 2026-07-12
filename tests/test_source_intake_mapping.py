"""map_frame column-coalescing behavior for the Tranche B intake (pandas-backed).

Skipped when pandas is absent (offline dev shell); runs in CI where pandas is
installed. map_frame must coalesce per row across candidate columns
(amount_numeric -> amount_raw) instead of committing to one column and blanking
the rows the preferred column happened to miss.
"""

import pytest

pd = pytest.importorskip("pandas")

from scripts.source_intake_helpers import map_frame  # noqa: E402


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
