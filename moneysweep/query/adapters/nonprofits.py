"""ProPublica Nonprofit Explorer adapters (IRS 990 filings).

The geographic adapter mirrors the existing Puerto Rico search producer.
The entity-mode adapter uses ProPublica's direct organization endpoint keyed
by EIN. This keeps EIN as a stable external identifier and does not promote
name similarity to canonical Money Sweep identity.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from moneysweep.runtime.pagination_runtime import PageResult, paginate
from moneysweep.runtime.retry_runtime import RetryPolicy, with_retry

from ..entity_types import EntityQuery
from ..types import Query
from .base import SourceAdapter
from .entity_base import EntityAdapter

PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"
SEARCH_URL = f"{PROPUBLICA_BASE}/organizations/search.json"
ORGANIZATION_URL = f"{PROPUBLICA_BASE}/organizations/{{ein}}.json"
MAX_PAGES = 200


def _session(existing=None):
    if existing is not None:
        return existing
    import requests

    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "moneysweep-pr-query/1",
        }
    )
    api_key = os.environ.get("PROPUBLICA_API_KEY")
    if api_key:
        session.headers["X-API-Key"] = api_key
    return session


class NonprofitsIRS990Adapter(SourceAdapter):
    source_id = "nonprofits_irs990"

    def __init__(self, *, root, session=None):
        super().__init__(root=root)
        self._session = session

    def _get_session(self):
        return _session(self._session)

    def _get(self, session, params: dict[str, Any]):
        resp = session.get(SEARCH_URL, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def fetch(self, query: Query) -> pd.DataFrame:
        session = self._get_session()
        policy = RetryPolicy(max_attempts=4, base_delay_seconds=1.0, max_delay_seconds=15.0)

        def fetch_page(marker):
            page = int(marker) if marker is not None else 0
            params = {"state[id]": "PR", "page": page}
            data = with_retry(lambda: self._get(session, params), policy=policy)
            records = data.get("organizations") or []
            return PageResult(
                records=records,
                next_marker=(page + 1) if records else None,
            )

        rows = list(paginate(fetch_page, start_marker=0, max_pages=MAX_PAGES))
        return pd.DataFrame(rows) if rows else pd.DataFrame()


class NonprofitsIRS990EntityAdapter(EntityAdapter):
    """Direct IRS nonprofit lookup by EIN.

    Only ``ein`` is supported because it is the source-native stable identifier.
    Names remain discovery inputs elsewhere and are intentionally not sent to a
    fuzzy/search endpoint by this adapter.
    """

    source_id = "nonprofits_irs990"
    supported_kinds = frozenset({"ein"})

    def __init__(self, *, root, session=None):
        super().__init__(root=root)
        self._session = session

    def _get_session(self):
        return _session(self._session)

    @staticmethod
    def _normalize_ein(value: str) -> str:
        return "".join(ch for ch in str(value) if ch.isdigit())

    def _lookup(self, session, ein: str, policy: RetryPolicy) -> dict[str, Any] | None:
        normalized = self._normalize_ein(ein)
        if len(normalized) != 9:
            return None
        url = ORGANIZATION_URL.format(ein=normalized)

        def get():
            response = session.get(url, timeout=60)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

        data = with_retry(get, policy=policy)
        if not data:
            return None
        organization = data.get("organization") or {}
        if not organization:
            return None
        return {
            "lookup_kind": "ein",
            "lookup_value": ein,
            "ein": str(organization.get("ein") or normalized),
            "name": organization.get("name", ""),
            "city": organization.get("city", ""),
            "state": organization.get("state", ""),
            "ntee_code": organization.get("ntee_code", ""),
            "subsection_code": organization.get("subsection_code", ""),
            "classification_codes": organization.get("classification_codes", ""),
            "ruling_date": organization.get("ruling_date", ""),
        }

    def fetch(self, query: EntityQuery) -> pd.DataFrame:
        session = self._get_session()
        policy = RetryPolicy(max_attempts=4, base_delay_seconds=1.0, max_delay_seconds=15.0)
        rows: list[dict[str, Any]] = []
        for ident in query.identifiers:
            if ident.kind != "ein":
                continue
            row = self._lookup(session, ident.value, policy)
            if row is not None:
                rows.append(row)
        return pd.DataFrame(rows) if rows else pd.DataFrame()
