"""Normalization helpers for entity resolution.

Name normalization delegates to the established
``moneysweep.runtime.name_normalization`` implementation so resolution clusters
entities exactly the way the rest of the pipeline does. Address and telephone
normalizers are added here for the match features that need them.
"""

from __future__ import annotations

import re

from moneysweep.runtime.name_normalization import (
    normalize_name,
    normalize_person_name,
)

__all__ = [
    "normalize_name",
    "normalize_person_name",
    "normalize_address",
    "normalize_phone",
]

_WS = re.compile(r"\s+")
_NON_ALNUM_SPACE = re.compile(r"[^A-Z0-9 ]+")
_NON_DIGIT = re.compile(r"\D+")

# Common US/PR street-type abbreviations folded to a single token.
_ADDRESS_TOKENS = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "AVENIDA": "AVE",
    "CALLE": "C",
    "ROAD": "RD",
    "CARRETERA": "CARR",
    "SUITE": "STE",
    "APARTMENT": "APT",
    "URBANIZACION": "URB",
}


def normalize_address(address: str | None) -> str:
    """Uppercase, strip punctuation, fold common street-type words, collapse space."""
    if not address:
        return ""
    s = _NON_ALNUM_SPACE.sub(" ", str(address).upper())
    tokens = [_ADDRESS_TOKENS.get(t, t) for t in _WS.sub(" ", s).strip().split(" ") if t]
    return " ".join(tokens)


def normalize_phone(phone: str | None) -> str:
    """Return the trailing 10 digits of a phone number (drops country code / formatting)."""
    if not phone:
        return ""
    digits = _NON_DIGIT.sub("", str(phone))
    return digits[-10:] if len(digits) >= 10 else digits
