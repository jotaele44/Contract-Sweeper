from pathlib import Path
import yaml

ROOT = Path(__file__).parents[2]


def test_manual_promotion_only():
    p = yaml.safe_load((ROOT / "config" / "forensics" / "manual_promotion_policy.yaml").read_text())
    assert p["allow_automatic_promotion"] is False and p["require_user_approval"] is True


def test_five_cases():
    for n in ["jacobs", "aes_pr", "ecoval_soria", "dick_corporation", "grant_thornton"]:
        d = yaml.safe_load(
            (
                ROOT / "moneysweep" / "forensics" / "skill" / "validation_cases" / f"{n}.yaml"
            ).read_text()
        )
        assert "agency_scoped_contract_key" in d["required_controls"]
