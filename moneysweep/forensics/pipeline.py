from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .adapters import SourceAdapter
from .core import ForensicsLedger, utcnow


@dataclass
class PipelineDelta:
    source_id: str
    status: str
    records: int
    evidence: int
    gaps: int
    skipped: bool = False
    reason: str | None = None


class ForensicsPipeline:
    """Manifest-driven source execution with anti-retread and delta reporting."""

    def __init__(self, ledger: ForensicsLedger, adapters: Mapping[str, SourceAdapter]) -> None:
        self.ledger = ledger
        self.adapters = dict(adapters)

    def run(self, subject: Mapping[str, Any], source_ids: Iterable[str] | None = None) -> list[PipelineDelta]:
        selected = list(source_ids or self.adapters)
        deltas: list[PipelineDelta] = []
        for source_id in selected:
            adapter = self.adapters[source_id]
            parameters = adapter.parameters(subject)
            decision = self.ledger.preflight_query(
                source_id=source_id, subject_id=subject["entity_id"],
                query_type=adapter.query_type, parameters=parameters,
                aliases_changed=bool(subject.get("aliases_changed")),
                contradiction_open=bool(subject.get("contradiction_open")),
            )
            if decision.action == "SKIP":
                deltas.append(PipelineDelta(source_id, "SKIPPED", 0, 0, 0, True, decision.reason))
                continue
            result = adapter.execute(self.ledger, subject["entity_id"], subject)
            deltas.append(PipelineDelta(source_id, result.status, len(result.records), len(result.evidence), len(result.gaps)))
        return deltas

    @staticmethod
    def write_report(path: str | Path, subject: Mapping[str, Any], deltas: list[PipelineDelta]) -> Path:
        target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"generated_at": utcnow().isoformat(), "subject": dict(subject), "deltas": [asdict(d) for d in deltas]}
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        tmp.replace(target)
        return target


def load_manifest(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(source.read_text(encoding="utf-8"))
    return json.loads(source.read_text(encoding="utf-8"))
