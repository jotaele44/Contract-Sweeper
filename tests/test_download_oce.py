from unittest.mock import Mock

import pytest

from scripts import download_oce


@pytest.mark.unit
def test_fetch_rows_paginates_until_short_page():
    session = Mock()
    first = Mock()
    first.json.return_value = [{"nombre_completo": "A"}, {"nombre_completo": "B"}]
    first.url = "https://example.test/1"
    first.raise_for_status.return_value = None
    second = Mock()
    second.json.return_value = [{"nombre_completo": "C"}]
    second.url = "https://example.test/2"
    second.raise_for_status.return_value = None
    session.get.side_effect = [first, second]

    rows, pages = download_oce.fetch_rows(session, page_size=2)
    assert [r["nombre_completo"] for r in rows] == ["A", "B", "C"]
    assert [p["offset"] for p in pages] == [0, 2]
    assert session.get.call_count == 2
