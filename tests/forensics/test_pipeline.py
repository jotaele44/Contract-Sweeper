from pathlib import Path
from moneysweep.forensics.adapters import AdapterResult, SourceAdapter
from moneysweep.forensics.core import ForensicsLedger
from moneysweep.forensics.pipeline import ForensicsPipeline


class EmptyAdapter(SourceAdapter):
    source_id = "empty"
    family = "test"
    endpoint = "memory://empty"
    query_type = "test"
    freshness_days = 7

    def fetch(self, subject):
        return AdapterResult(self.source_id, "SUCCESS_NULL")


def test_pipeline_anti_retread(tmp_path):
    root = Path(__file__).parents[2]
    with ForensicsLedger(tmp_path / "f.duckdb", root / "migrations" / "forensics") as ledger:
        ledger.migrate()
        pipeline = ForensicsPipeline(ledger, {"empty": EmptyAdapter()})
        subject = {"entity_id": "ent_test", "aliases": ["TEST"]}
        first = pipeline.run(subject)
        second = pipeline.run(subject)
        assert first[0].status == "SUCCESS_NULL"
        assert second[0].skipped is True
