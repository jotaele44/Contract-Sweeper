from __future__ import annotations

import hashlib
import http.client
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from .core import ForensicsLedger, canonical_hash, query_key, utcnow


@dataclass(frozen=True)
class AdapterResult:
    source_id: str
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)
    failure_type: str | None = None
    failure_packet: dict[str, Any] | None = None
    next_fallback: str | None = None


class SourceAdapter:
    source_id: str
    family: str
    endpoint: str
    source_tier: str = "T1"
    query_type: str = "source_fetch"
    freshness_days: int = 30

    def parameters(self, subject: Mapping[str, Any]) -> Mapping[str, Any]:
        return subject

    def fetch(self, subject: Mapping[str, Any]) -> AdapterResult:
        raise NotImplementedError

    def execute(
        self, ledger: ForensicsLedger, subject_id: str, subject: Mapping[str, Any]
    ) -> AdapterResult:
        now = utcnow()
        params = dict(self.parameters(subject))
        decision = ledger.preflight_query(
            source_id=self.source_id,
            subject_id=subject_id,
            query_type=self.query_type,
            parameters=params,
        )
        if decision.action == "SKIP":
            return AdapterResult(self.source_id, "SKIPPED_FRESH")

        source_run_id = canonical_hash(self.source_id, subject_id, now.isoformat(), prefix="run_")
        qkey = query_key(self.source_id, subject_id, self.query_type, params)
        qid = canonical_hash(qkey, now.isoformat(), prefix="qh_")
        base_query = {
            "query_id": qid,
            "query_key": qkey,
            "source_id": self.source_id,
            "entity_id": subject_id,
            "project_id": None,
            "query_type": self.query_type,
            "parameters_json": json.dumps(params, sort_keys=True),
            "parameters_hash": hashlib.sha256(
                json.dumps(params, sort_keys=True).encode()
            ).hexdigest(),
            "started_at": now,
            "finished_at": None,
            "status": "RUNNING",
            "result_count": 0,
            "new_record_count": 0,
            "updated_record_count": 0,
            "null_result": False,
            "failure_type": None,
            "fallback_route": decision.fallback_route,
            "retry_after": None,
            "fresh_until": None,
            "created_at": now,
            "updated_at": now,
        }
        ledger.record_query(base_query)
        ledger.upsert(
            "sources",
            [
                {
                    "source_id": self.source_id,
                    "family": self.family,
                    "endpoint": self.endpoint,
                    "source_tier": self.source_tier,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            ["source_id"],
        )
        ledger.upsert(
            "source_runs",
            [
                {
                    "source_run_id": source_run_id,
                    "source_id": self.source_id,
                    "status": "RUNNING",
                    "started_at": now,
                    "finished_at": None,
                    "result_count": 0,
                    "failure_type": None,
                    "failure_packet_json": None,
                    "created_at": now,
                    "updated_at": now,
                }
            ],
            ["source_run_id"],
        )

        result = self.fetch(subject)
        finished = utcnow()
        query_status = (
            result.status
            if result.status
            in {
                "SUCCESS",
                "SUCCESS_NULL",
                "FAILED_TRANSIENT",
                "FAILED_PERMANENT",
                "BLOCKED_AUTH",
                "BLOCKED_WAF",
                "BLOCKED_NETWORK",
                "RECORD_PURGED",
                "REQUIRES_BROWSER",
                "REQUIRES_FOIA",
            }
            else "FAILED_PERMANENT"
        )
        ledger.record_query(
            {
                **base_query,
                "finished_at": finished,
                "status": query_status,
                "result_count": len(result.records),
                "null_result": query_status == "SUCCESS_NULL",
                "failure_type": result.failure_type,
                "fallback_route": result.next_fallback,
                "retry_after": finished + timedelta(days=1)
                if query_status in {"FAILED_TRANSIENT", "BLOCKED_NETWORK"}
                else None,
                "fresh_until": finished + timedelta(days=self.freshness_days)
                if query_status in {"SUCCESS", "SUCCESS_NULL"}
                else None,
                "updated_at": finished,
            }
        )
        ledger.upsert(
            "source_runs",
            [
                {
                    "source_run_id": source_run_id,
                    "source_id": self.source_id,
                    "status": query_status,
                    "started_at": now,
                    "finished_at": finished,
                    "result_count": len(result.records),
                    "failure_type": result.failure_type,
                    "failure_packet_json": json.dumps(result.failure_packet)
                    if result.failure_packet
                    else None,
                    "created_at": now,
                    "updated_at": finished,
                }
            ],
            ["source_run_id"],
        )
        for rec in result.records:
            rec.setdefault("source_id", self.source_id)
            rec.setdefault("source_run_id", source_run_id)
        for ev in result.evidence:
            ev.setdefault("created_at", finished)
            ev.setdefault("updated_at", finished)
        for gap in result.gaps:
            gap.setdefault("created_at", finished)
            gap.setdefault("updated_at", finished)
        if result.evidence:
            ledger.upsert("evidence", result.evidence, ["evidence_key"])
        if result.gaps:
            ledger.upsert("gaps", result.gaps, ["gap_id"])
        return result


class HttpJsonAdapter(SourceAdapter):
    method = "GET"
    timeout = 20
    headers = {"User-Agent": "Contract-Forensics-V3/3.1"}

    def build_request(self, subject: Mapping[str, Any]) -> urllib.request.Request:
        return urllib.request.Request(self.endpoint, headers=self.headers, method=self.method)

    def parse(self, payload: Any, subject: Mapping[str, Any]) -> list[dict[str, Any]]:
        return []

    def fetch(self, subject: Mapping[str, Any]) -> AdapterResult:
        try:
            req = self.build_request(subject)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            records = self.parse(payload, subject)
            return AdapterResult(
                self.source_id, "SUCCESS" if records else "SUCCESS_NULL", records=records
            )
        except urllib.error.HTTPError as exc:
            status = "BLOCKED_AUTH" if exc.code in {401, 403} else "FAILED_TRANSIENT"
            return AdapterResult(
                self.source_id,
                status,
                failure_type=f"HTTP_{exc.code}",
                failure_packet={
                    "command": self.endpoint,
                    "exit_code": exc.code,
                    "last_40_lines": str(exc),
                    "files_recently_changed": [],
                    "suspected_area": "http_source",
                },
                next_fallback="OFFICIAL_BULK_EXPORT",
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return AdapterResult(
                self.source_id,
                "BLOCKED_NETWORK",
                failure_type=type(exc).__name__,
                failure_packet={
                    "command": self.endpoint,
                    "exit_code": 1,
                    "last_40_lines": str(exc),
                    "files_recently_changed": [],
                    "suspected_area": "network_or_dns",
                },
                next_fallback="OFFICIAL_BULK_EXPORT",
            )
        except Exception as exc:
            return AdapterResult(
                self.source_id,
                "FAILED_PERMANENT",
                failure_type=type(exc).__name__,
                failure_packet={
                    "command": self.endpoint,
                    "exit_code": 1,
                    "last_40_lines": str(exc),
                    "files_recently_changed": [],
                    "suspected_area": "adapter_parse",
                },
            )


class LocalTextAdapter(SourceAdapter):
    def __init__(
        self, source_id: str, family: str, path: str | Path, endpoint: str | None = None
    ) -> None:
        self.source_id = source_id
        self.family = family
        self.path = Path(path)
        self.endpoint = endpoint or str(self.path)

    def read_text(self) -> str:
        if self.path.suffix.lower() == ".pdf":
            import subprocess

            cache_dir = Path(__file__).resolve().parents[2] / "data" / "forensics" / "text_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache = cache_dir / (hashlib.sha256(str(self.path).encode()).hexdigest() + ".txt")
            if not cache.exists() or cache.stat().st_mtime < self.path.stat().st_mtime:
                subprocess.run(
                    ["pdftotext", "-layout", str(self.path), str(cache)],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            return cache.read_text(encoding="utf-8", errors="replace")
        return self.path.read_text(encoding="utf-8", errors="replace")

    def extract(
        self, text: str, subject: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return [], []

    def fetch(self, subject: Mapping[str, Any]) -> AdapterResult:
        if not self.path.exists():
            return AdapterResult(
                self.source_id,
                "FAILED_PERMANENT",
                failure_type="FileNotFoundError",
                failure_packet={
                    "command": str(self.path),
                    "exit_code": 2,
                    "last_40_lines": "file not found",
                    "files_recently_changed": [],
                    "suspected_area": "local_source_path",
                },
            )
        try:
            text = self.read_text()
            records, evidence = self.extract(text, subject)
            return AdapterResult(
                self.source_id,
                "SUCCESS" if records or evidence else "SUCCESS_NULL",
                records=records,
                evidence=evidence,
            )
        except Exception as exc:
            return AdapterResult(
                self.source_id,
                "FAILED_PERMANENT",
                failure_type=type(exc).__name__,
                failure_packet={
                    "command": str(self.path),
                    "exit_code": 1,
                    "last_40_lines": str(exc),
                    "files_recently_changed": [],
                    "suspected_area": "local_document_parse",
                },
            )


class ContractorListingAdapter(LocalTextAdapter):
    query_type = "contractor_listing_extract"
    LINE = re.compile(
        r"^(?P<cage>[A-Z0-9]{5})\s+\S+\s+(?P<name>.+?)\s{2,}.+?\s+(?P<duns>\d{9}|T\d{8,})\s*$"
    )

    def extract(
        self, text: str, subject: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        aliases = [a.upper() for a in subject.get("aliases", [])]
        records: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        source_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        for lineno, line in enumerate(text.splitlines(), 1):
            upper = line.upper()
            if not any(alias in upper for alias in aliases):
                continue
            m = self.LINE.match(line.strip())
            if m:
                name = " ".join(m.group("name").split())
                cage, duns = m.group("cage"), m.group("duns")
            else:
                name = " ".join(line.strip().split())
                cage = duns = None
            claim = f"Historical contractor listing entry: {name}"
            evk = canonical_hash(source_hash, lineno, claim, prefix="ev_")
            evidence.append(
                {
                    "evidence_key": evk,
                    "subject_id": subject["entity_id"],
                    "predicate": "historical_contractor_listing",
                    "object_json": json.dumps({"name": name, "cage": cage, "duns": duns}),
                    "source_hash": source_hash,
                    "source_locator": f"line:{lineno}",
                    "claim_text": claim,
                    "evidence_tier": "T1",
                    "confidence": 0.9,
                    "observed_at": utcnow(),
                    "review_status": "MACHINE_VALIDATED",
                    "contradiction_group": None,
                }
            )
            records.append({"name": name, "cage": cage, "duns": duns, "evidence_key": evk})
        return records, evidence


class KeywordEvidenceAdapter(LocalTextAdapter):
    query_type = "keyword_evidence_extract"

    def extract(
        self, text: str, subject: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        aliases = [a.upper() for a in subject.get("aliases", [])]
        records, evidence = [], []
        source_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        lines = text.splitlines()
        for lineno, line in enumerate(lines, 1):
            upper = line.upper()
            if not any(alias in upper for alias in aliases):
                continue
            context = " ".join(lines[max(0, lineno - 2) : min(len(lines), lineno + 1)]).strip()
            context = " ".join(context.split())[:1200]
            claim = f"Source mention: {context}"
            evk = canonical_hash(source_hash, lineno, claim, prefix="ev_")
            evidence.append(
                {
                    "evidence_key": evk,
                    "subject_id": subject["entity_id"],
                    "predicate": "source_mention",
                    "object_json": json.dumps({"context": context}),
                    "source_hash": source_hash,
                    "source_locator": f"line:{lineno}",
                    "claim_text": claim,
                    "evidence_tier": "T1",
                    "confidence": 0.75,
                    "observed_at": utcnow(),
                    "review_status": "UNREVIEWED",
                    "contradiction_group": None,
                }
            )
            records.append({"context": context, "evidence_key": evk})
        return records, evidence


class UsaSpendingRecipientAdapter(HttpJsonAdapter):
    source_id = "usaspending"
    family = "federal_awards"
    endpoint = "https://api.usaspending.gov/api/v2/recipient/"
    method = "POST"
    query_type = "recipient_search"
    freshness_days = 7

    def build_request(self, subject: Mapping[str, Any]) -> urllib.request.Request:
        payload = json.dumps({"keyword": subject.get("legal_name", "")}).encode("utf-8")
        headers = {**self.headers, "Content-Type": "application/json"}
        return urllib.request.Request(self.endpoint, data=payload, headers=headers, method="POST")

    def parse(self, payload: Any, subject: Mapping[str, Any]) -> list[dict[str, Any]]:
        return list(payload.get("results", [])) if isinstance(payload, dict) else []


class SamAdapter(HttpJsonAdapter):
    source_id = "sam"
    family = "entity_resolution"
    endpoint = "https://api.sam.gov/entity-information/v3/entities"
    query_type = "entity_search"
    freshness_days = 30

    def build_request(self, subject: Mapping[str, Any]) -> urllib.request.Request:
        api_key = subject.get("sam_api_key")
        if not api_key:
            raise urllib.error.HTTPError(
                self.endpoint, 401, "SAM_API_KEY missing", hdrs=http.client.HTTPMessage(), fp=None
            )
        qs = urllib.parse.urlencode(
            {"legalBusinessName": subject.get("legal_name", ""), "api_key": api_key}
        )
        return urllib.request.Request(f"{self.endpoint}?{qs}", headers=self.headers)


class SimpleEndpointAdapter(HttpJsonAdapter):
    def __init__(
        self, source_id: str, family: str, endpoint: str, freshness_days: int = 30
    ) -> None:
        self.source_id = source_id
        self.family = family
        self.endpoint = endpoint
        self.freshness_days = freshness_days


ADAPTER_ENDPOINTS = {
    "ocpr": ("territorial_contracts", "https://consultacontratos.ocpr.gov.pr/"),
    "pr_corporations": ("entity_resolution", "https://rceweb.estado.pr.gov/"),
    "contralor": ("oversight", "https://www.ocpr.gov.pr/"),
    "prasa": ("territorial_infrastructure", "https://www.acueductospr.com/"),
    "prepa_preb": ("territorial_energy", "https://energia.pr.gov/"),
    "act_dtop": ("territorial_transport", "https://act.dtop.pr.gov/"),
    "cor3_fema": ("disaster_recovery", "https://recovery.pr.gov/"),
    "lobbying_pr": ("influence", "https://registrodecabilderos.pr.gov/"),
    "lda_federal": ("influence", "https://lda.senate.gov/api/v1/"),
    "courts": ("litigation", "https://pacer.uscourts.gov/"),
}
