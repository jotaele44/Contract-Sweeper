from __future__ import annotations

import re
from dataclasses import fields
from datetime import date, datetime, timedelta
from typing import Any, Mapping, TypeVar

from .models import (
    AMENDMENT_STATUSES,
    BINDING_BASES,
    BYTE_STATUSES,
    CANONICALITY_STATES,
    DIRECTNESS_STATES,
    IDENTITY_LEVELS,
    IDENTITY_STATUSES,
    PASS_BINDING_BASES,
    POSITION_CLASSES,
    SOURCE_FAMILIES,
    TRISTATE_STATES,
    HoldingObservation,
    InvestorIdentity,
    SourceManifest,
)


_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_T = TypeVar("_T")


class ValidationError(ValueError):
    pass


def _unknown_keys(cls: type[Any], payload: Mapping[str, Any]) -> set[str]:
    return set(payload) - {item.name for item in fields(cls)}


def _construct(cls: type[_T], payload: Mapping[str, Any]) -> _T:
    unknown = _unknown_keys(cls, payload)
    if unknown:
        raise ValidationError(f"unexpected fields: {sorted(unknown)}")
    try:
        return cls(**payload)
    except TypeError as exc:
        raise ValidationError(str(exc)) from exc


def _require_date(name: str, value: object) -> None:
    if type(value) is not date:
        raise ValidationError(f"{name} must be a date")


def _require_optional_date(name: str, value: object) -> None:
    if value is not None:
        _require_date(name, value)


def validate_investor_identity(payload: Mapping[str, Any]) -> InvestorIdentity:
    item = _construct(InvestorIdentity, payload)
    if not item.investor_id.startswith("INV_"):
        raise ValidationError("investor_id must start with INV_")
    if not item.raw_name:
        raise ValidationError("raw_name is required and must be preserved")
    if item.identity_level not in IDENTITY_LEVELS:
        raise ValidationError("invalid identity_level")
    if item.identity_status not in IDENTITY_STATUSES:
        raise ValidationError("invalid identity_status")
    if item.binding_basis not in BINDING_BASES:
        raise ValidationError("invalid binding_basis")
    if not item.source_id:
        raise ValidationError("source_id is required")
    if item.identity_status == "PASS" and item.binding_basis not in PASS_BINDING_BASES:
        raise ValidationError(
            "PASS identity requires binding evidence stronger than heuristic discovery"
        )
    _require_optional_date("valid_from", item.valid_from)
    _require_optional_date("valid_to", item.valid_to)
    if item.valid_from and item.valid_to and item.valid_to < item.valid_from:
        raise ValidationError("valid_to precedes valid_from")
    return item


def _check_nonnegative(name: str, value: float | None) -> None:
    if value is not None and value < 0:
        raise ValidationError(f"{name} must be nonnegative")


def _check_percent(name: str, value: float | None) -> None:
    if value is not None and not 0 <= value <= 100:
        raise ValidationError(f"{name} must be between 0 and 100")


def validate_holding_observation(payload: Mapping[str, Any]) -> HoldingObservation:
    item = _construct(HoldingObservation, payload)
    if not item.observation_id.startswith("HOLD_"):
        raise ValidationError("observation_id must start with HOLD_")
    if not item.holder_id.startswith("INV_"):
        raise ValidationError("holder_id must start with INV_")
    if not item.issuer_id or not item.source_id or not item.source_record_id:
        raise ValidationError("issuer_id, source_id, and source_record_id are required")
    if item.position_class not in POSITION_CLASSES:
        raise ValidationError("invalid position_class")
    if item.identity_status not in IDENTITY_STATUSES:
        raise ValidationError("invalid identity_status")
    if item.direct_or_indirect not in DIRECTNESS_STATES:
        raise ValidationError("invalid direct_or_indirect")
    for name, value in (
        ("beneficial_owner_status", item.beneficial_owner_status),
        ("investment_adviser_status", item.investment_adviser_status),
        ("control_status", item.control_status),
    ):
        if value not in TRISTATE_STATES:
            raise ValidationError(f"invalid {name}")
    if item.amendment_status not in AMENDMENT_STATUSES:
        raise ValidationError("invalid amendment_status")
    _require_date("as_of_date", item.as_of_date)
    _require_date("report_date", item.report_date)
    if not item.security_id and not item.security_class_raw:
        raise ValidationError("security_id or security_class_raw is required")
    if item.currency is not None and (
        len(item.currency) != 3 or item.currency.upper() != item.currency
    ):
        raise ValidationError("currency must be an uppercase ISO-style three-letter code")
    for name in (
        "shares",
        "principal_amount",
        "market_value",
        "sole_voting_power",
        "shared_voting_power",
        "sole_dispositive_power",
        "shared_dispositive_power",
    ):
        _check_nonnegative(name, getattr(item, name))
    _check_percent("percent_class", item.percent_class)
    _check_percent("percent_issuer", item.percent_issuer)
    if item.source_document_sha256 is not None and not _HEX64.fullmatch(
        item.source_document_sha256
    ):
        raise ValidationError("source_document_sha256 must be 64 lowercase hex characters")
    if item.amendment_status == "AMENDED" and not item.supersedes_observation_id:
        raise ValidationError("AMENDED rows require supersedes_observation_id")
    return item


def validate_source_manifest(payload: Mapping[str, Any]) -> SourceManifest:
    item = _construct(SourceManifest, payload)
    if not item.source_id.startswith("SRC_CAP_"):
        raise ValidationError("source_id must start with SRC_CAP_")
    if item.source_family not in SOURCE_FAMILIES:
        raise ValidationError("invalid source_family")
    if item.byte_status not in BYTE_STATUSES:
        raise ValidationError("invalid byte_status")
    if item.canonicality not in CANONICALITY_STATES:
        raise ValidationError("invalid canonicality")
    if not item.source_authority or not item.source_url_or_locator:
        raise ValidationError("source authority and locator are required")
    if not isinstance(item.retrieval_utc, datetime):
        raise ValidationError("retrieval_utc must be a datetime")
    if item.retrieval_utc.utcoffset() != timedelta(0):
        raise ValidationError("retrieval_utc must be timezone-aware UTC")
    _require_optional_date("source_as_of_date", item.source_as_of_date)
    _require_optional_date("refresh_date", item.refresh_date)
    if item.raw_bytes_size is not None and item.raw_bytes_size < 0:
        raise ValidationError("raw_bytes_size must be nonnegative")
    if item.record_count is not None and item.record_count < 0:
        raise ValidationError("record_count must be nonnegative")
    if item.raw_bytes_sha256 is not None and not _HEX64.fullmatch(item.raw_bytes_sha256):
        raise ValidationError("raw_bytes_sha256 must be 64 lowercase hex characters")
    if item.byte_status == "FROZEN":
        if item.raw_bytes_size is None or item.raw_bytes_sha256 is None:
            raise ValidationError("FROZEN source requires byte size and SHA-256")
    return item
