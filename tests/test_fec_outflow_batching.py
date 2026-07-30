import logging

import pytest

from moneysweep.runtime.base_downloader import HttpRequestFailed
from scripts import download_fec_committees as mod


@pytest.mark.unit
def test_retryable_batch_failure_splits_until_requests_succeed(monkeypatch):
    calls = []

    def fake_get(_session, _url, params, _logger, _sleep_s):
        batch = list(params["committee_id"])
        calls.append(batch)
        if len(batch) > 5:
            raise HttpRequestFailed("gateway timeout", status_code=None, retryable=True)
        return {"results": [], "pagination": {"pages": 1}}

    monkeypatch.setattr(mod, "_get", fake_get)
    rows = mod._fetch_disbursements(
        object(),
        [f"C{index:08d}" for index in range(10)],
        [2018],
        0,
        logging.getLogger("test"),
    )
    assert rows == []
    assert [len(batch) for batch in calls] == [10, 5, 5]


@pytest.mark.unit
def test_single_committee_retryable_failure_remains_fatal(monkeypatch):
    def fake_get(_session, _url, _params, _logger, _sleep_s):
        raise HttpRequestFailed("gateway timeout", status_code=None, retryable=True)

    monkeypatch.setattr(mod, "_get", fake_get)
    with pytest.raises(HttpRequestFailed):
        mod._fetch_disbursements(
            object(),
            ["C00000001"],
            [2018],
            0,
            logging.getLogger("test"),
        )
