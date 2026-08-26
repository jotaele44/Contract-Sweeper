"""Fail-closed SEC ticker/CIK identity binding for equity issuers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class SecIdentityError(ValueError):
    """Raised when a ticker/CIK binding is absent, ambiguous, or contradictory."""


@dataclass(frozen=True)
class SecIssuerBinding:
    ticker: str
    cik: str
    title_raw: str


def canonical_cik(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits or len(digits) > 10:
        raise SecIdentityError(f"invalid CIK: {value!r}")
    return digits.zfill(10)


def ticker_map(payload: Mapping[str, Any]) -> dict[str, SecIssuerBinding]:
    """Parse SEC company_tickers.json without using names as identity evidence."""
    out: dict[str, SecIssuerBinding] = {}
    for raw in payload.values():
        if not isinstance(raw, Mapping):
            continue
        ticker = str(raw.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        binding = SecIssuerBinding(
            ticker=ticker,
            cik=canonical_cik(raw.get("cik_str")),
            title_raw=str(raw.get("title") or ""),
        )
        incumbent = out.get(ticker)
        if incumbent is not None and incumbent.cik != binding.cik:
            raise SecIdentityError(f"ticker {ticker} maps to multiple CIKs")
        out[ticker] = binding
    return out


def require_binding(
    payload: Mapping[str, Any], *, ticker: str, expected_cik: str | None = None
) -> SecIssuerBinding:
    wanted = ticker.strip().upper()
    binding = ticker_map(payload).get(wanted)
    if binding is None:
        raise SecIdentityError(f"ticker {wanted} is absent from SEC company_tickers.json")
    if expected_cik is not None and binding.cik != canonical_cik(expected_cik):
        raise SecIdentityError(
            f"ticker {wanted} CIK contradiction: expected {canonical_cik(expected_cik)}, "
            f"SEC reports {binding.cik}"
        )
    return binding


def require_submission_identity(
    submission: Mapping[str, Any], *, binding: SecIssuerBinding
) -> None:
    """Require the fetched submissions document to bind back to the same CIK."""
    submission_cik = canonical_cik(submission.get("cik"))
    if submission_cik != binding.cik:
        raise SecIdentityError(
            f"submission CIK contradiction for {binding.ticker}: "
            f"ticker-map={binding.cik} submission={submission_cik}"
        )
    tickers = {str(value).strip().upper() for value in submission.get("tickers", [])}
    if tickers and binding.ticker not in tickers:
        raise SecIdentityError(
            f"submission ticker contradiction for {binding.cik}: {binding.ticker} not in {sorted(tickers)}"
        )
