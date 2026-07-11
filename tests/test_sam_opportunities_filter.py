"""Unit tests for the SAM.gov Opportunities pre-award notice filter.

The source is defined as pre-award solicitations / bid notices, so post-award
notice types (Award Notice, J&A justifications, surplus-property sales) must be
excluded before writing to avoid overlap with the award datasets.
"""

from __future__ import annotations

import importlib

import pytest

sam = importlib.import_module("scripts.download_sam_opportunities")


@pytest.mark.unit
@pytest.mark.parametrize(
    "notice_type",
    [
        "Solicitation",
        "Presolicitation",
        "Combined Synopsis/Solicitation",
        "Sources Sought",
        "Special Notice",
        "Intent to Bundle Requirements (a-76)",
        "",  # unknown/empty is kept rather than dropped
    ],
)
def test_pre_award_types_kept(notice_type):
    assert sam._is_pre_award(notice_type) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "notice_type",
    [
        "Award Notice",
        "Justification",
        "Justification and Approval (J&A)",
        "Sale of Surplus Property",
        "  award notice  ",  # whitespace/case-insensitive
    ],
)
def test_post_award_types_excluded(notice_type):
    assert sam._is_pre_award(notice_type) is False
