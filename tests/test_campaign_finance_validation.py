import pandas as pd
import pytest

from scripts import validate_campaign_finance_materialization as mod


@pytest.mark.unit
def test_strict_gate_reports_missing_required_files(tmp_path):
    report = mod.run(root=tmp_path, strict=True)
    assert report["ok"] is False
    assert any(item.startswith("fec_contributions:") for item in report["blocking"])
    assert (tmp_path / "data" / "manifests" / "campaign_finance" / "campaign_finance_validation.json").exists()
