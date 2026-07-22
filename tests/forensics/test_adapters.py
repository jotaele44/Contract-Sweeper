from pathlib import Path
from moneysweep.forensics.adapters import KeywordEvidenceAdapter
from moneysweep.forensics.core import ForensicsLedger
from moneysweep.forensics.seed import jacobs_subject

ROOT = Path(__file__).parents[2]


def test_prasa_cer_keyword_adapter_finds_jacobs():
    path = Path("/mnt/data/FY2024 CER_Final.pdf")
    if not path.exists():
        return
    result = KeywordEvidenceAdapter("test", "infra", path).fetch(jacobs_subject())
    assert result.status == "SUCCESS"
    assert any("Jacobs" in r["context"] for r in result.records)


def test_persisted_adapter_state_exists():
    ledger = ForensicsLedger(
        ROOT / "data" / "forensics" / "contract_forensics.duckdb", ROOT / "migrations" / "forensics"
    )
    ledger.migrate()
    tables = {r[0] for r in ledger.conn.execute("show tables").fetchall()}
    assert {"sources", "query_history", "source_runs"} <= tables
    ledger.close()
