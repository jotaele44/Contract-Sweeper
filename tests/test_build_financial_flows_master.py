"""Tests for scripts/build_financial_flows_master.py.

Covers the cached-parquet fast path: when the normalized artifact already
exists and ``--force`` is not used, ``run()`` must read the cached frame and
return the REAL row count and total amount (the bug was it returned amount 0).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts import build_financial_flows_master as bffm

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHED_PARQUET = REPO_ROOT / "data" / "normalized" / "financial_flows_master.parquet"

# The committed/materialized cache metrics this patch pins.
EXPECTED_ROWS = 90598
EXPECTED_TOTAL = 63797332465.08


def _cache_present() -> bool:
    return CACHED_PARQUET.exists()


@pytest.mark.integration
@pytest.mark.skipif(not _cache_present(), reason="cached financial_flows_master.parquet absent")
def test_cached_run_reports_real_total_over_expected_rows():
    """Cached read returns the real total (not 0) over the expected row count."""
    result = bffm.run(root=REPO_ROOT, force=False)

    assert result["status"] == "CACHED"
    assert result["rows"] == EXPECTED_ROWS
    # Real total, not the old silent 0; tolerate float summation noise.
    assert result["total_amount"] == pytest.approx(EXPECTED_TOTAL, abs=0.01)


@pytest.mark.integration
@pytest.mark.skipif(not _cache_present(), reason="cached financial_flows_master.parquet absent")
def test_cached_total_matches_direct_dataframe_computation():
    """run()'s cached total equals a direct recompute from the same parquet."""
    df = pd.read_parquet(CACHED_PARQUET)
    direct_total = pd.to_numeric(df["amount"], errors="coerce").fillna(0).sum()

    result = bffm.run(root=REPO_ROOT, force=False)

    assert len(df) == EXPECTED_ROWS
    assert result["total_amount"] == pytest.approx(direct_total, abs=0.01)
    assert result["total_amount"] == pytest.approx(EXPECTED_TOTAL, abs=0.01)


@pytest.mark.unit
def test_cached_branch_returns_total_amount_key(tmp_path):
    """Even a synthetic cached parquet yields a total_amount key (contract parity).

    Guards against regressing to the old ``{"rows": ..., "status": "CACHED"}``
    shape that omitted total_amount and made main() print $0.
    """
    norm_dir = tmp_path / "data" / "normalized"
    norm_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {col: [""] * 3 for col in bffm.FLOW_COLUMNS}
    )
    df["amount"] = ["100.50", "200", "not_a_number"]
    from scripts.parquet_utils import pq_write

    pq_write(df, norm_dir / "financial_flows_master.parquet")

    result = bffm.run(root=tmp_path, force=False)

    assert result["status"] == "CACHED"
    assert result["rows"] == 3
    # 100.50 + 200 + (coerced-to-0) == 300.50
    assert result["total_amount"] == pytest.approx(300.50, abs=0.001)
