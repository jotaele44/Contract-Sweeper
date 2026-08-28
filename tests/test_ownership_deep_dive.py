from __future__ import annotations

import pytest

from moneysweep.capital_control.deep_dive import OwnershipDeepDiveError, build_ownership_deep_dive


def _certification(**overrides):
    base = {
        "certification_id": "BPOP_SEC13F_8Q_v1",
        "state": "PASS",
        "scope": "bounded BPOP SEC 13F 2024Q2-2026Q1",
        "bounded_claim_only": True,
        "observed_bpop_periods": [
            "2024-06-30",
            "2024-09-30",
            "2024-12-31",
            "2025-03-31",
            "2025-06-30",
            "2025-09-30",
            "2025-12-31",
            "2026-03-31",
        ],
        "regression_counts": {"BPOP": 100, "OFG": 10, "EVTC": 12},
        "morningstar_percent_total_assets_equivalence": "OPEN",
    }
    base.update(overrides)
    return base


def _rows():
    periods = _certification()["observed_bpop_periods"]
    rows = []
    for index, period in enumerate(periods):
        rows.append(
            {
                "observation_id": f"OBS-{index}",
                "holder_id": "INV_CIK_0000000123",
                "issuer_id": "ISSUER_CIK_0000763901",
                "as_of_date": period,
                "report_date": period,
                "source_record_id": f"ACC-{index}:1",
                "security_cusip": "733174700",
                "amendment_status": "ORIGINAL",
                "is_active": "true",
                "provider_metric_equivalence": "OPEN",
                "shares": str(1000 + index),
                "market_value": str(10000 + index),
                "percent_issuer_shares_computed": "1.0",
                "issuer_share_denominator": "100000",
                "percent_13f_reportable_value": "0.5",
                "filing_manager_name_raw": "Manager One LLC",
                "accession_number": f"ACC-{index}",
            }
        )
    rows.append(
        {
            **rows[-1],
            "observation_id": "OBS-SUPERSEDED",
            "source_record_id": "ACC-OLD:1",
            "amendment_status": "SUPERSEDED",
            "is_active": "false",
            "shares": "900",
            "accession_number": "ACC-OLD",
        }
    )
    return rows


def test_deep_dive_requires_pass_certification() -> None:
    with pytest.raises(OwnershipDeepDiveError, match="not PASS"):
        build_ownership_deep_dive(
            _rows(), _certification(state="OPEN"), ticker="BPOP", cusip="733174700"
        )


def test_deep_dive_refuses_provider_equivalence_promotion() -> None:
    with pytest.raises(OwnershipDeepDiveError, match="must remain OPEN"):
        build_ownership_deep_dive(
            _rows(),
            _certification(morningstar_percent_total_assets_equivalence="PASS"),
            ticker="BPOP",
            cusip="733174700",
        )


def test_deep_dive_is_bounded_to_certified_bpop() -> None:
    with pytest.raises(OwnershipDeepDiveError, match="certified only for BPOP"):
        build_ownership_deep_dive(
            _rows(), _certification(), ticker="OFG", cusip="67103X102"
        )


def test_deep_dive_preserves_whole_rows_and_closes_states() -> None:
    result = build_ownership_deep_dive(
        _rows(), _certification(), ticker="BPOP", cusip="733174700"
    )
    assert result["certification"]["state"] == "PASS"
    assert result["providerEquivalence"] == "OPEN"
    assert result["aggregationPolicy"] == "WHOLE_SOURCE_OBSERVATIONS_ONLY_NO_CROSS_HOLDER_SUMMATION"
    assert result["observationCount"] == 9
    assert result["activeObservationCount"] == 8
    assert result["supersededObservationCount"] == 1
    assert len(result["periodLedger"]) == 8
    assert result["latestPeriod"] == "2026-03-31"
    assert len(result["latestObservations"]) == 1
    assert "totalShares" not in result


def test_deep_dive_requires_real_source_ofg_evtc_regressions() -> None:
    with pytest.raises(OwnershipDeepDiveError, match="OFG and EVTC"):
        build_ownership_deep_dive(
            _rows(),
            _certification(regression_counts={"BPOP": 100, "OFG": 0, "EVTC": 12}),
            ticker="BPOP",
            cusip="733174700",
        )


def test_deep_dive_requires_exact_eight_period_materialization() -> None:
    rows = _rows()
    rows = [row for row in rows if row["as_of_date"] != "2024-06-30"]
    with pytest.raises(OwnershipDeepDiveError, match="periods differ"):
        build_ownership_deep_dive(rows, _certification(), ticker="BPOP", cusip="733174700")
