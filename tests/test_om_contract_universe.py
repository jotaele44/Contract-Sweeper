from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = load_module("build_om_contract_universe", "scripts/build_om_contract_universe.py")
validator = load_module("validate_om_contract_universe", "scripts/validate_om_contract_universe.py")
resumable = load_module(
    "materialize_ocpr_contracts_resumable", "scripts/materialize_ocpr_contracts_resumable.py"
)


def taxonomy():
    return yaml.safe_load(
        (ROOT / "registries/om_contract_taxonomy.yaml").read_text(encoding="utf-8")
    )


def test_classifier_positive_review_and_negative_override():
    positive = pd.Series(
        {
            "service_description": "Operation and preventive maintenance of water treatment plant",
            "contract_type": "services",
            "source_file": "x",
            "agency": "AAA",
        }
    )
    review = pd.Series(
        {
            "service_description": "Software maintenance",
            "contract_type": "services",
            "source_file": "x",
            "agency": "agency",
        }
    )
    negative = pd.Series(
        {
            "service_description": "Design-build new construction with maintenance manuals",
            "contract_type": "construction",
            "source_file": "x",
            "agency": "agency",
        }
    )
    assert builder.classify(positive, taxonomy())[0] == "om"
    assert builder.classify(review, taxonomy())[0] == "om_review"
    assert builder.classify(negative, taxonomy())[0] == "non_om"


def test_fingerprint_is_deterministic():
    row = pd.Series(
        {
            "contract_number": "A-1",
            "contractor_name": "Vendor",
            "agency": "Agency",
            "contract_amount": "$10.00",
            "start_date": "2026-01-01",
            "service_description": "Maintenance",
        }
    )
    assert builder.fingerprint(row) == builder.fingerprint(row.copy())
    assert len(builder.fingerprint(row)) == 64


def test_checkpoint_rejects_tampered_work_file(tmp_path):
    checkpoint_path = tmp_path / "checkpoint.json"
    work_path = tmp_path / "pages.jsonl"
    work_path.write_text('{"contract_number":"A"}\n', encoding="utf-8")
    checkpoint = resumable.initial_checkpoint(100)
    checkpoint.update(
        written_rows=1, work_sha256=hashlib.sha256(work_path.read_bytes()).hexdigest()
    )
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    loaded = resumable.load_checkpoint(checkpoint_path, work_path, 100, False)
    assert loaded["written_rows"] == 1
    work_path.write_text('{"contract_number":"B"}\n', encoding="utf-8")
    try:
        resumable.load_checkpoint(checkpoint_path, work_path, 100, False)
    except RuntimeError as exc:
        assert "SHA-256 mismatch" in str(exc)
    else:
        raise AssertionError("tampered checkpoint work file was accepted")


def test_builder_emits_blockers_and_validator_passes_structure(tmp_path):
    root = tmp_path
    (root / "registries").mkdir()
    (root / "registries/om_contract_taxonomy.yaml").write_text(
        (ROOT / "registries/om_contract_taxonomy.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    source = root / "data/staging/processed/pr_ocpr_contracts.csv"
    source.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "contract_number": "A-1",
                "contractor_name": "Vendor",
                "agency": "Agency",
                "contract_amount": "100",
                "start_date": "2026-01-01",
                "end_date": "2027-01-01",
                "service_description": "operation and preventive maintenance",
                "contract_type": "services",
            }
        ]
    ).to_csv(source, index=False)
    out = root / "reports/om_contract_universe"
    summary = builder.run(root, out)
    assert summary["complete_claim_allowed"] is False
    gaps = pd.read_csv(out / "unresolved_gap_ledger.csv")
    assert "OCPR_FULL_MATERIALIZATION" in set(gaps.blocker_id)
    ok, errors = validator.validate(out)
    assert ok, errors
