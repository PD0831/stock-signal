from unittest.mock import Mock

from scripts import market_snapshot_data


def test_fetch_current_nasdaq_symbols_uses_constituent_list(monkeypatch):
    response = Mock()
    rows = "".join(
        f"<tr><td>TEST{i:02d}</td><td>Company {i}</td></tr>" for i in range(80)
    )
    response.text = f"""
        <table>
          <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
    """
    response.raise_for_status.return_value = None
    requested_urls = []

    def fake_get(url, **kwargs):
        requested_urls.append(url)
        return response

    monkeypatch.setattr(market_snapshot_data.requests, "get", fake_get)

    assert market_snapshot_data._wikipedia_symbols("nasdaq100") == [
        f"TEST{i:02d}" for i in range(80)
    ]
    assert requested_urls == [
        "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
    ]
