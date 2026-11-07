import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import api_client


def offer(price):
    return {"price": price, "flights": [{"airline": "Example"}]}


class Response:
    status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return {"best_flights": [offer(800), offer(300), offer(400), offer(450)]}


def test_price_filter_precedes_result_limit(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(api_client.requests, "get", get)
    results = api_client.SerpAPIClient().search_offers("YYZ", "DUB", "2026-12-01", max_price=500, max_results=2)
    assert [r["price_cad"] for r in results] == [300, 400]
    assert calls[0]["params"]["max_price"] == 500


def test_zero_limit_makes_no_request(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("zero results should not consume API quota")
    monkeypatch.setattr(api_client.requests, "get", unexpected)
    assert api_client.SerpAPIClient().search_offers("YYZ", "DUB", "2026-12-01", max_results=0) == []


@pytest.mark.parametrize("limit", [-1, 1.5, True])
def test_invalid_limits_are_rejected_before_a_request(monkeypatch, limit):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid limit reached the provider")
    monkeypatch.setattr(api_client.requests, "get", unexpected)
    with pytest.raises(ValueError):
        api_client.SerpAPIClient().search_offers("YYZ", "DUB", "2026-12-01", max_results=limit)
