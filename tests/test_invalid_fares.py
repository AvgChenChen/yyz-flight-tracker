import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from api_client import SerpAPIClient


@pytest.mark.parametrize("invalid", ["not a price", "NaN", "Infinity", float("inf"), float("nan"), -20, True, {}])
def test_bad_fares_do_not_crash_or_poison_valid_results(invalid):
    legs = [{"airline": "Example", "departure_airport": {"time": "2026-12-01 09:30"}}]
    data = {"best_flights": [{"price": invalid, "flights": legs}, {"price": "420", "flights": legs}]}
    results = SerpAPIClient()._parse_flights(data, "DUB", "2026-12-01", None)
    assert len(results) == 1
    assert results[0]["price_cad"] == 420.0
