"""Strict SEC Form 13F bulk ingestion for MoneySweep capital/control."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .models import HoldingObservation, InvestorIdentity

SOURCE_ID = "SRC_CAP_SEC_13F_BULK"
TABLES = ("SUBMISSION.tsv", "COVERPAGE.tsv", "SUMMARYPAGE.tsv", "INFOTABLE.tsv")
REQUIRED = {
    "SUBMISSION.tsv": {"ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"},
    "COVERPAGE.tsv": {
        "ACCESSION_NUMBER", "REPORTCALENDARORQUARTER", "ISAMENDMENT",
        "AMENDMENTTYPE", "FILINGMANAGER_NAME",
    },
    "SUMMARYPAGE.tsv": {"ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL"},
    "INFOTABLE.tsv": {
        "ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER", "TITLEOFCLASS",
        "CUSIP", "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL",
        "INVESTMENTDISCRETION", "OTHERMANAGER", "VOTING_AUTH_SOLE",
        "VOTING_AUTH_SHARED", "VOTING_AUTH_NONE",
    },
}
_RESTATEMENT = {"RESTATEMENT", "RESTATED"}
_ADDITION = {"NEW HOLDINGS", "NEW HOLDING", "ADDITION", "ADDITIONAL HOLDINGS"}
_SAFE = re.compile(r"[^A-Za-z0-9]+")


class Sec13FError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveMemberDigest:
    path: str
    uncompressed_size: int
    sha256: str


@dataclass(frozen=True)
class Sec13FArchiveAudit:
    archive_path: str
    raw_bytes_size: int
    raw_bytes_sha256: str
    member_digests: tuple[ArchiveMemberDigest, ...]
    schema_fingerprint: str
    source_row_counts: Mapping[str, int]
    retained_rows: int
    target_cusips: tuple[str, ...]


@dataclass(frozen=True)
class RestatementIssue:
    observation_id: str
    reason: str
    candidate_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class RestatementAdjudication:
    observations: tuple[HoldingObservation, ...]
    issues: tuple[RestatementIssue, ...]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date(raw: str):
    value = (raw or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise Sec13FError(f"unsupported SEC date: {raw!r}")


def _number(raw: str | None) -> float | None:
    value = (raw or "").strip().replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise Sec13FError(f"invalid SEC numeric value: {raw!r}") from exc


def _cusip(raw: str) -> str:
    return (raw or "").strip().upper()


def _rows(payload: bytes, table: str) -> tuple[dict[str, str], ...]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Sec13FError(f"{table}: not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if reader.fieldnames is None:
        raise Sec13FError(f"{table}: missing header")
    fields = {str(name).strip().upper() for name in reader.fieldnames}
    missing = REQUIRED[table] - fields
    if missing:
        raise Sec13FError(f"{table}: missing required fields {sorted(missing)}")
    return tuple(
        {str(key).strip().upper(): str(value or "") for key, value in row.items() if key}
        for row in reader
    )


def _unique(
    rows: Iterable[Mapping[str, str]], key: str, table: str
) -> dict[str, Mapping[str, str]]:
    out: dict[str, Mapping[str, str]] = {}
    for row in rows:
        value = (row.get(key) or "").strip()
        if not value:
            raise Sec13FError(f"{table}: empty {key}")
        if value in out:
            raise Sec13FError(f"{table}: duplicate {key}: {value}")
        out[value] = row
    return out


def _holder_id(cik: str) -> str:
    digits = "".join(ch for ch in cik if ch.isdigit())
    if not digits:
        raise Sec13FError("filing manager CIK is empty")
    return f"INV_CIK_{digits.zfill(10)}"


def _obs_id(accession: str, sk: str) -> str:
    return f"HOLD_SEC13F_{_SAFE.sub('_', accession).strip('_')}_{sk}"


def _amendment(
    cover: Mapping[str, str], submission: Mapping[str, str]
) -> tuple[str, str]:
    stype = (submission.get("SUBMISSIONTYPE") or "").strip().upper()
    is_amend = (cover.get("ISAMENDMENT") or "").strip().upper() in {
        "Y", "YES", "1", "TRUE"
    }
    if not is_amend and not stype.endswith("/A"):
        return "ORIGINAL", "ORIGINAL"
    raw = (cover.get("AMENDMENTTYPE") or "").strip()
    upper = raw.upper()
    if upper in _ADDITION:
        return "AMENDED_ADDITION", raw or "NEW HOLDINGS"
    if upper in _RESTATEMENT:
        return "UNKNOWN", raw or "RESTATEMENT"
    return "UNKNOWN", raw or "UNKNOWN"


class Sec13FBulkAdapter:
    """Capital/control adapter for one already-frozen SEC Form 13F ZIP."""

    def __init__(
        self,
        archive_path: Path | str,
        *,
        target_cusips: Iterable[str],
        issuer_bindings: Mapping[str, str] | None = None,
    ) -> None:
        self.archive_path = Path(archive_path)
        self.target_cusips = tuple(
            sorted({_cusip(value) for value in target_cusips if value})
        )
        if not self.target_cusips:
            raise Sec13FError("at least one target CUSIP is required")
        self.issuer_bindings = {
            _cusip(key): value for key, value in (issuer_bindings or {}).items()
        }
        self._records: tuple[dict[str, object], ...] | None = None
        self._investors: tuple[InvestorIdentity, ...] | None = None
        self._audit: Sec13FArchiveAudit | None = None
        self._retrieval_utc: datetime | None = None

    def _load(self) -> None:
        if self._records is not None:
            return
        if not self.archive_path.is_file() or not zipfile.is_zipfile(self.archive_path):
            raise Sec13FError(f"invalid SEC 13F ZIP: {self.archive_path}")

        outer_hash = _sha256_file(self.archive_path)
        outer_size = self.archive_path.stat().st_size
        self._retrieval_utc = datetime.fromtimestamp(
            self.archive_path.stat().st_mtime, tz=timezone.utc
        )
        table_rows: dict[str, tuple[dict[str, str], ...]] = {}
        headers: dict[str, tuple[str, ...]] = {}
        digests: list[ArchiveMemberDigest] = []

        with zipfile.ZipFile(self.archive_path) as zf:
            members: dict[str, zipfile.ZipInfo] = {}
            for info in zf.infolist():
                if info.is_dir():
                    continue
                base = Path(info.filename).name.upper()
                if base in members:
                    raise Sec13FError(f"duplicate archive member basename: {base}")
                members[base] = info
                payload = zf.read(info)
                digests.append(
                    ArchiveMemberDigest(
                        info.filename, len(payload), hashlib.sha256(payload).hexdigest()
                    )
                )
                for table in TABLES:
                    if base == table.upper():
                        parsed = _rows(payload, table)
                        table_rows[table] = parsed
                        if parsed:
                            headers[table] = tuple(parsed[0])
                        else:
                            first = payload.decode("utf-8-sig").splitlines()
                            headers[table] = tuple(first[0].split("\t")) if first else ()
            missing_tables = [table for table in TABLES if table not in table_rows]
            if missing_tables:
                raise Sec13FError(f"archive missing required members: {missing_tables}")

        submission = _unique(table_rows["SUBMISSION.tsv"], "ACCESSION_NUMBER", "SUBMISSION.tsv")
        cover = _unique(table_rows["COVERPAGE.tsv"], "ACCESSION_NUMBER", "COVERPAGE.tsv")
        summary = _unique(table_rows["SUMMARYPAGE.tsv"], "ACCESSION_NUMBER", "SUMMARYPAGE.tsv")

        records: list[dict[str, object]] = []
        investors: dict[str, InvestorIdentity] = {}
        seen_info: set[tuple[str, str]] = set()
        targets = set(self.target_cusips)

        for row in table_rows["INFOTABLE.tsv"]:
            accession = row["ACCESSION_NUMBER"].strip()
            sk = row["INFOTABLE_SK"].strip()
            key = (accession, sk)
            if not accession or not sk:
                raise Sec13FError("INFOTABLE.tsv: empty primary key")
            if key in seen_info:
                raise Sec13FError(f"INFOTABLE.tsv: duplicate key {key}")
            seen_info.add(key)

            security_cusip = _cusip(row["CUSIP"])
            if security_cusip not in targets:
                continue
            sub, cov, summ = submission.get(accession), cover.get(accession), summary.get(accession)
            if sub is None or cov is None or summ is None:
                raise Sec13FError(f"{accession}: missing submission/cover/summary join")

            cik = str(sub["CIK"]).strip()
            holder_id = _holder_id(cik)
            manager_raw = str(cov["FILINGMANAGER_NAME"]).strip()
            if not manager_raw:
                raise Sec13FError(f"{accession}: empty filing manager name")
            investors.setdefault(
                holder_id,
                InvestorIdentity(
                    investor_id=holder_id,
                    raw_name=manager_raw,
                    identity_level="LEGAL_ENTITY",
                    identity_status="PASS",
                    source_id=SOURCE_ID,
                    legal_entity_id=holder_id,
                    binding_basis="STABLE_ID",
                    notes=f"SEC Form 13F filer CIK {cik.zfill(10)}",
                ),
            )

            issuer_id = self.issuer_bindings.get(
                security_cusip, f"ISSUER_UNRESOLVED_CUSIP_{security_cusip}"
            )
            identity_status = (
                "PASS" if security_cusip in self.issuer_bindings else "UNRESOLVED"
            )
            amendment_status, raw_amendment = _amendment(cov, sub)
            amount = _number(row.get("SSHPRNAMT"))
            amount_type = row["SSHPRNAMTTYPE"].strip().upper()
            market_value = _number(row.get("VALUE"))
            table_value = _number(summ.get("TABLEVALUETOTAL"))
            pct_13f = (
                market_value / table_value * 100.0
                if market_value is not None and table_value not in (None, 0)
                else None
            )

            records.append(
                {
                    "observation_id": _obs_id(accession, sk),
                    "holder_id": holder_id,
                    "issuer_id": issuer_id,
                    "position_class": "INVESTMENT_DISCRETION",
                    "as_of_date": _date(str(sub["PERIODOFREPORT"])),
                    "report_date": _date(str(sub["FILING_DATE"])),
                    "source_id": SOURCE_ID,
                    "source_record_id": f"{accession}:{sk}",
                    "identity_status": identity_status,
                    "security_id": f"CUSIP:{security_cusip}",
                    "security_class_raw": row["TITLEOFCLASS"].strip() or None,
                    "shares": amount if amount_type == "SH" else None,
                    "principal_amount": amount if amount_type == "PRN" else None,
                    "market_value": market_value,
                    "currency": "USD",
                    "sole_voting_power": _number(row.get("VOTING_AUTH_SOLE")),
                    "shared_voting_power": _number(row.get("VOTING_AUTH_SHARED")),
                    "amendment_status": amendment_status,
                    "source_document_sha256": outer_hash,
                    "extra": {
                        "accession_number": accession,
                        "infotable_sk": sk,
                        "filer_cik": cik.zfill(10),
                        "filing_manager_name_raw": manager_raw,
                        "issuer_name_raw": row["NAMEOFISSUER"].strip(),
                        "figi": row.get("FIGI", "").strip() or None,
                        "put_call": row["PUTCALL"].strip() or None,
                        "investment_discretion": row["INVESTMENTDISCRETION"].strip(),
                        "other_manager_raw": row["OTHERMANAGER"].strip() or None,
                        "voting_authority_none": _number(row.get("VOTING_AUTH_NONE")),
                        "table_entry_total": _number(summ.get("TABLEENTRYTOTAL")),
                        "table_value_total": table_value,
                        "percent_13f_reportable_value": pct_13f,
                        "provider_percent_total_assets": None,
                        "provider_metric_equivalence": "OPEN",
                        "source_amendment_type": raw_amendment,
                        "source_archive": self.archive_path.name,
                    },
                }
            )

        schema_payload = {
            table: sorted({field.upper() for field in fields})
            for table, fields in sorted(headers.items())
        }
        fingerprint = hashlib.sha256(
            json.dumps(schema_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        counts = {table: len(rows) for table, rows in table_rows.items()}
        self._records = tuple(records)
        self._investors = tuple(sorted(investors.values(), key=lambda item: item.investor_id))
        self._audit = Sec13FArchiveAudit(
            str(self.archive_path),
            outer_size,
            outer_hash,
            tuple(sorted(digests, key=lambda item: item.path)),
            fingerprint,
            counts,
            len(records),
            self.target_cusips,
        )

    def iter_records(self):
        self._load()
        assert self._records is not None
        yield from self._records

    def iter_investors(self) -> tuple[InvestorIdentity, ...]:
        self._load()
        assert self._investors is not None
        return self._investors

    def audit(self) -> Sec13FArchiveAudit:
        self._load()
        assert self._audit is not None
        return self._audit

    def source_manifest(self) -> Mapping[str, object]:
        self._load()
        assert self._audit is not None and self._retrieval_utc is not None
        return {
            "source_id": SOURCE_ID,
            "source_family": "REGULATORY_HOLDINGS",
            "source_authority": "U.S. Securities and Exchange Commission",
            "retrieval_utc": self._retrieval_utc,
            "source_url_or_locator": str(self.archive_path),
            "byte_status": "FROZEN",
            "query_identity": "CUSIP:" + ",".join(self.target_cusips),
            "raw_bytes_sha256": self._audit.raw_bytes_sha256,
            "raw_bytes_size": self._audit.raw_bytes_size,
            "schema_fingerprint": self._audit.schema_fingerprint,
            "record_count": self._audit.retained_rows,
            "canonicality": "CANONICAL",
            "notes": "Frozen as-filed SEC 13F bulk source; issuer/provider semantics remain separately gated.",
        }


def _restatement_key(row: HoldingObservation) -> tuple[object, ...]:
    return (
        row.holder_id,
        row.issuer_id,
        row.security_id,
        row.security_class_raw,
        row.position_class,
        row.as_of_date,
        row.extra.get("put_call"),
        row.extra.get("investment_discretion"),
        row.extra.get("other_manager_raw"),
    )


def adjudicate_sec13f_restatements(
    observations: Iterable[HoldingObservation],
) -> RestatementAdjudication:
    """Bind a restatement only when exactly one prior structural row is proven."""
    rows = tuple(observations)
    by_key: dict[tuple[object, ...], list[HoldingObservation]] = {}
    for row in rows:
        by_key.setdefault(_restatement_key(row), []).append(row)

    replacements: dict[str, HoldingObservation] = {}
    issues: list[RestatementIssue] = []
    for row in rows:
        raw_type = str(row.extra.get("source_amendment_type") or "").strip().upper()
        if raw_type not in _RESTATEMENT:
            continue
        candidates = [
            candidate
            for candidate in by_key.get(_restatement_key(row), [])
            if candidate.observation_id != row.observation_id
            and candidate.report_date < row.report_date
        ]
        if candidates:
            latest = max(candidate.report_date for candidate in candidates)
            candidates = [candidate for candidate in candidates if candidate.report_date == latest]
        if len(candidates) != 1:
            issues.append(
                RestatementIssue(
                    row.observation_id,
                    "restatement target is not uniquely proven",
                    tuple(sorted(candidate.observation_id for candidate in candidates)),
                )
            )
            continue
        replacements[row.observation_id] = replace(
            row,
            amendment_status="AMENDED_RESTATEMENT",
            supersedes_observation_id=candidates[0].observation_id,
        )

    return RestatementAdjudication(
        tuple(replacements.get(row.observation_id, row) for row in rows),
        tuple(issues),
    )
