from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Protocol
from xml.etree import ElementTree as ET


class SourceAdapter(Protocol):
    """Adapter contract: acquisition is source-specific; canonicalization is not."""

    def iter_records(self) -> Iterable[Mapping[str, Any]]:
        raise NotImplementedError

    def source_manifest(self) -> Mapping[str, Any]:
        raise NotImplementedError


def stable_observation_fingerprint(payload: Mapping[str, Any]) -> str:
    """Hash only identity-defining observation fields using canonical JSON serialization."""
    canonical = {
        key: payload.get(key)
        for key in (
            "holder_id",
            "issuer_id",
            "security_id",
            "security_class_raw",
            "position_class",
            "as_of_date",
            "report_date",
            "source_id",
            "source_record_id",
        )
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _CapitalSourceDefinition:
    source_key: str
    authority: str
    source_family: str
    form_types: frozenset[str]
    canonicality: str
    acquisition_mode: str
    official_locator: str
    technical_spec_locator: str
    denominator_rule: str
    update_cadence: str
    semantic_limit: str


_SEC_SOURCE_DEFINITIONS: tuple[_CapitalSourceDefinition, ...] = (
    _CapitalSourceDefinition(
        source_key="SEC_13F",
        authority="U.S. Securities and Exchange Commission",
        source_family="REGULATORY_HOLDINGS",
        form_types=frozenset({"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}),
        canonicality="CANONICAL",
        acquisition_mode="EDGAR_FILING_AND_QUARTERLY_BULK_DATASET",
        official_locator="https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets",
        technical_spec_locator="https://www.sec.gov/submit-filings/technical-specifications",
        denominator_rule=(
            "Enumerate authoritative EDGAR filings or SEC quarterly 13F bulk data; "
            "do not treat web search results as a denominator. Preserve amendments as separate filings."
        ),
        update_cadence="QUARTERLY_BULK_PLUS_LIVE_EDGAR",
        semantic_limit=(
            "13F reports institutional investment discretion over reportable securities; "
            "it is not automatic beneficial-ownership proof."
        ),
    ),
    _CapitalSourceDefinition(
        source_key="SEC_13D_G",
        authority="U.S. Securities and Exchange Commission",
        source_family="BENEFICIAL_OWNERSHIP",
        form_types=frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}),
        canonicality="CANONICAL",
        acquisition_mode="EDGAR_FILING",
        official_locator="https://www.sec.gov/edgar/search/",
        technical_spec_locator="https://www.sec.gov/submit-filings/technical-specifications",
        denominator_rule=(
            "Enumerate authoritative EDGAR submission records for the exact schedule types and scope; "
            "retain amendments and filing dates."
        ),
        update_cadence="LIVE_EDGAR",
        semantic_limit=(
            "Schedule 13D/G reports beneficial-ownership information under its filing rules; "
            "reported persons and group relationships remain distinct until explicitly bound."
        ),
    ),
    _CapitalSourceDefinition(
        source_key="SEC_FORMS_3_4_5",
        authority="U.S. Securities and Exchange Commission",
        source_family="INSIDER_FILING",
        form_types=frozenset({"3", "3/A", "4", "4/A", "5", "5/A"}),
        canonicality="CANONICAL",
        acquisition_mode="EDGAR_FILING",
        official_locator="https://www.sec.gov/edgar/search/",
        technical_spec_locator="https://www.sec.gov/submit-filings/technical-specifications",
        denominator_rule=(
            "Enumerate authoritative EDGAR ownership submissions for exact issuer/reporting-owner scope; "
            "retain derivative and non-derivative tables separately."
        ),
        update_cadence="LIVE_EDGAR",
        semantic_limit=(
            "Section 16 reporting-owner status and transaction reporting do not by themselves establish "
            "ultimate-parent or investor-family identity."
        ),
    ),
    _CapitalSourceDefinition(
        source_key="SEC_NPORT",
        authority="U.S. Securities and Exchange Commission",
        source_family="FUND_HOLDINGS",
        form_types=frozenset({"NPORT-P", "NPORT-P/A", "NPORT-NP", "NPORT-NP/A"}),
        canonicality="CANONICAL",
        acquisition_mode="EDGAR_FILING",
        official_locator="https://www.sec.gov/edgar/search/",
        technical_spec_locator="https://www.sec.gov/submit-filings/technical-specifications",
        denominator_rule=(
            "Enumerate authoritative EDGAR N-PORT submissions for the registered-fund scope; "
            "respect public/non-public filing treatment and amendments."
        ),
        update_cadence="MONTHLY_OR_AS_REQUIRED_BY_FORM_RULES",
        semantic_limit=(
            "N-PORT describes fund portfolio holdings; fund, adviser, sponsor, beneficial owner, and ultimate "
            "parent identities must remain separate."
        ),
    ),
)

_SOURCE_BY_KEY = {item.source_key: item for item in _SEC_SOURCE_DEFINITIONS}


def _source_definition(source_key: str) -> _CapitalSourceDefinition:
    try:
        return _SOURCE_BY_KEY[source_key]
    except KeyError as exc:
        raise ValueError(f"unknown capital source definition: {source_key}") from exc


def _source_for_form_type(form_type: str) -> _CapitalSourceDefinition:
    matches = [item for item in _SEC_SOURCE_DEFINITIONS if form_type in item.form_types]
    if len(matches) != 1:
        raise ValueError(f"form type must resolve to exactly one source definition: {form_type!r}")
    return matches[0]


def _assert_source_registry_invariants(items: Iterable[_CapitalSourceDefinition]) -> None:
    rows = tuple(items)
    keys = [row.source_key for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate source_key")
    claimed_forms: set[str] = set()
    for row in rows:
        if not row.form_types:
            raise ValueError(f"source definition has no form types: {row.source_key}")
        overlap = claimed_forms & set(row.form_types)
        if overlap:
            raise ValueError(f"form types mapped to multiple source definitions: {sorted(overlap)}")
        claimed_forms.update(row.form_types)
        if row.canonicality != "CANONICAL":
            raise ValueError("authoritative SEC registry entries must be canonical")
        if not row.official_locator.startswith("https://www.sec.gov/"):
            raise ValueError("SEC official locator must use sec.gov")
        if not row.technical_spec_locator.startswith("https://www.sec.gov/"):
            raise ValueError("SEC technical specification locator must use sec.gov")


_assert_source_registry_invariants(_SEC_SOURCE_DEFINITIONS)


@dataclass(frozen=True)
class _FilingIndexRecord:
    accession_number: str
    cik: str
    form_type: str
    filing_date: date
    report_date: date | None
    source_url: str


@dataclass(frozen=True)
class _DenominatorResult:
    source_key: str
    input_count: int
    retained: tuple[_FilingIndexRecord, ...]
    excluded: tuple[_FilingIndexRecord, ...]
    exclusion_counts: tuple[tuple[str, int], ...]

    @property
    def retained_count(self) -> int:
        return len(self.retained)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)


def _validate_filing_index_record(row: _FilingIndexRecord) -> None:
    if not row.accession_number or not row.cik or not row.form_type:
        raise ValueError("accession_number, cik, and form_type are required")
    if not row.source_url.startswith("https://www.sec.gov/"):
        raise ValueError("SEC filing index record must bind to sec.gov")
    if row.report_date is not None and row.filing_date < row.report_date:
        raise ValueError("filing_date cannot precede report_date")


def _build_filing_denominator(
    records: Iterable[_FilingIndexRecord],
    definition: _CapitalSourceDefinition,
) -> _DenominatorResult:
    """Classify a supplied authoritative index universe; discovery search is not a denominator."""
    rows = tuple(records)
    seen: set[str] = set()
    retained: list[_FilingIndexRecord] = []
    excluded: list[_FilingIndexRecord] = []
    reasons: Counter[str] = Counter()

    for row in rows:
        _validate_filing_index_record(row)
        if row.accession_number in seen:
            raise ValueError(f"duplicate accession_number: {row.accession_number}")
        seen.add(row.accession_number)
        if row.form_type in definition.form_types:
            retained.append(row)
        else:
            excluded.append(row)
            reasons["FORM_TYPE_OUT_OF_SCOPE"] += 1

    if len(rows) != len(retained) + len(excluded):
        raise AssertionError("denominator arithmetic does not close")

    key = lambda row: (row.filing_date, row.accession_number)
    return _DenominatorResult(
        source_key=definition.source_key,
        input_count=len(rows),
        retained=tuple(sorted(retained, key=key)),
        excluded=tuple(sorted(excluded, key=key)),
        exclusion_counts=tuple(sorted(reasons.items())),
    )


@dataclass(frozen=True)
class _SEC13FFilingMetadata:
    accession_number: str
    filer_cik: str
    filing_date: date
    period_of_report: date
    source_url: str
    retrieval_utc: datetime
    value_scale: float
    is_amendment: bool = False
    canonicality: str = "CANONICAL"
    supersedes_by_source_record_id: Mapping[str, str] | None = None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children_by_local(element: ET.Element) -> dict[str, ET.Element]:
    return {_local_name(child.tag): child for child in list(element)}


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip()


def _descendant_text(element: ET.Element, *path: str) -> str | None:
    cursor = element
    for name in path:
        child = _children_by_local(cursor).get(name)
        if child is None:
            return None
        cursor = child
    return _text(cursor)


def _number(raw: str | None, field: str) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"invalid numeric {field}: {raw!r}") from exc


def _validate_13f_metadata(metadata: _SEC13FFilingMetadata) -> None:
    if not metadata.accession_number:
        raise ValueError("accession_number is required")
    if not metadata.filer_cik.isdigit():
        raise ValueError("filer_cik must contain digits only")
    if metadata.filing_date < metadata.period_of_report:
        raise ValueError("filing_date cannot precede period_of_report")
    if not metadata.source_url.startswith("https://www.sec.gov/Archives/edgar/data/"):
        raise ValueError("13F source_url must be an SEC EDGAR archive URL")
    offset = metadata.retrieval_utc.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("retrieval_utc must be timezone-aware UTC")
    if metadata.value_scale <= 0:
        raise ValueError("value_scale must be positive and explicit")
    if metadata.canonicality not in {"CANONICAL", "CORROBORATING", "NONCANONICAL"}:
        raise ValueError("unsupported 13F source canonicality")


class _FrozenSEC13FAdapter:
    """Parse frozen SEC Form 13F information-table XML without aggregating source rows."""

    def __init__(self, xml_bytes: bytes, metadata: _SEC13FFilingMetadata) -> None:
        _validate_13f_metadata(metadata)
        if not xml_bytes:
            raise ValueError("xml_bytes cannot be empty")
        self._xml_bytes = bytes(xml_bytes)
        self._metadata = metadata
        try:
            self._root = ET.fromstring(self._xml_bytes)
        except ET.ParseError as exc:
            raise ValueError("invalid SEC 13F XML") from exc
        if _local_name(self._root.tag) != "informationTable":
            raise ValueError("expected SEC 13F informationTable root")

    @property
    def source_id(self) -> str:
        accession = "".join(ch for ch in self._metadata.accession_number if ch.isalnum())
        return f"SRC_CAP_SEC_13F_{accession}"

    def _info_tables(self) -> tuple[ET.Element, ...]:
        return tuple(child for child in list(self._root) if _local_name(child.tag) == "infoTable")

    def source_manifest(self) -> Mapping[str, Any]:
        rows = self._info_tables()
        digest = hashlib.sha256(self._xml_bytes).hexdigest()
        return {
            "source_id": self.source_id,
            "source_family": "REGULATORY_HOLDINGS",
            "source_authority": "U.S. Securities and Exchange Commission",
            "retrieval_utc": self._metadata.retrieval_utc,
            "source_url_or_locator": self._metadata.source_url,
            "byte_status": "FROZEN",
            "source_as_of_date": self._metadata.period_of_report,
            "refresh_date": self._metadata.filing_date,
            "query_identity": f"EDGAR accession {self._metadata.accession_number}",
            "page_or_offset": "INFORMATION_TABLE_XML",
            "raw_bytes_sha256": digest,
            "raw_bytes_size": len(self._xml_bytes),
            "schema_fingerprint": f"SEC_FORM_13F_INFORMATION_TABLE_XML:value_scale={self._metadata.value_scale:g}",
            "record_count": len(rows),
            "canonicality": self._metadata.canonicality,
            "notes": (
                "Frozen 13F information-table XML; rows are not aggregated. "
                "CANONICAL is valid only for complete as-filed SEC bytes."
            ),
        }

    def iter_records(self) -> Iterable[Mapping[str, Any]]:
        digest = hashlib.sha256(self._xml_bytes).hexdigest()
        for index, row in enumerate(self._info_tables(), start=1):
            children = _children_by_local(row)
            issuer_name = _text(children.get("nameOfIssuer"))
            security_class = _text(children.get("titleOfClass"))
            cusip = _text(children.get("cusip"))
            figi = _text(children.get("figi"))
            value_raw = _text(children.get("value"))
            shares_raw = _descendant_text(row, "shrsOrPrnAmt", "sshPrnamt")
            shares_type = _descendant_text(row, "shrsOrPrnAmt", "sshPrnamtType")
            investment_discretion = _text(children.get("investmentDiscretion"))
            other_manager = _text(children.get("otherManager"))
            put_call = _text(children.get("putCall"))
            sole = _descendant_text(row, "votingAuthority", "Sole")
            shared = _descendant_text(row, "votingAuthority", "Shared")
            none_value = _descendant_text(row, "votingAuthority", "None")

            if not issuer_name:
                raise ValueError(f"13F row {index} missing nameOfIssuer")
            if not security_class and not cusip:
                raise ValueError(f"13F row {index} missing both titleOfClass and cusip")
            if not investment_discretion:
                raise ValueError(f"13F row {index} missing investmentDiscretion")

            source_record_id = f"{self._metadata.accession_number}:INFOTABLE:{index}"
            supersedes = None
            if self._metadata.supersedes_by_source_record_id:
                supersedes = self._metadata.supersedes_by_source_record_id.get(source_record_id)

            security_id = f"CUSIP:{cusip}" if cusip else None
            issuer_id = f"SEC_13F_SECURITY:{cusip}" if cusip else f"SEC_13F_UNRESOLVED_ISSUER:{index}"
            observation_hash = hashlib.sha256(source_record_id.encode("utf-8")).hexdigest()[:20]
            shares = _number(shares_raw, "sshPrnamt")
            market_value = _number(value_raw, "value")
            if market_value is not None:
                market_value *= self._metadata.value_scale

            yield {
                "observation_id": f"HOLD_SEC13F_{observation_hash}",
                "holder_id": f"INV_SEC_CIK_{self._metadata.filer_cik.zfill(10)}",
                "issuer_id": issuer_id,
                "position_class": "INVESTMENT_DISCRETION",
                "as_of_date": self._metadata.period_of_report,
                "report_date": self._metadata.filing_date,
                "source_id": self.source_id,
                "source_record_id": source_record_id,
                "identity_status": "PASS",
                "security_id": security_id,
                "security_class_raw": security_class,
                "direct_or_indirect": "UNKNOWN",
                "shares": shares if shares_type == "SH" else None,
                "principal_amount": shares if shares_type == "PRN" else None,
                "market_value": market_value,
                "currency": "USD",
                "sole_voting_power": _number(sole, "Sole"),
                "shared_voting_power": _number(shared, "Shared"),
                "beneficial_owner_status": "UNKNOWN",
                "investment_adviser_status": "UNKNOWN",
                "control_status": "UNKNOWN",
                "amendment_status": "AMENDED" if supersedes else "ORIGINAL",
                "supersedes_observation_id": supersedes,
                "source_document_sha256": digest,
                "notes": "13F investment-discretion observation; not beneficial-ownership proof.",
                "extra": {
                    "raw_name_of_issuer": issuer_name,
                    "raw_title_of_class": security_class,
                    "raw_cusip": cusip,
                    "raw_figi": figi,
                    "raw_value": value_raw,
                    "value_scale": self._metadata.value_scale,
                    "raw_shares_or_principal_amount": shares_raw,
                    "raw_shares_or_principal_type": shares_type,
                    "raw_investment_discretion": investment_discretion,
                    "raw_other_manager": other_manager,
                    "raw_put_call": put_call,
                    "raw_voting_none": none_value,
                    "source_is_amendment": self._metadata.is_amendment,
                },
            }


CapitalSourceDefinition = _CapitalSourceDefinition
SEC_SOURCE_DEFINITIONS = _SEC_SOURCE_DEFINITIONS
source_definition = _source_definition
source_for_form_type = _source_for_form_type
assert_source_registry_invariants = _assert_source_registry_invariants
FilingIndexRecord = _FilingIndexRecord
DenominatorResult = _DenominatorResult
build_filing_denominator = _build_filing_denominator
SEC13FFilingMetadata = _SEC13FFilingMetadata
FrozenSEC13FAdapter = _FrozenSEC13FAdapter
