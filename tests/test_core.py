"""
Core unit tests. No API key required — uses mock data.
Run: pytest tests/test_core.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import tempfile
import sqlite3

# Use a temp DB for tests
import config
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
config.DB_FILE = _tmp.name
_tmp.close()

import database
import deal_rating as dr
import destinations as dest_module
import search as s

database.init_db()


# ── Destination loading ───────────────────────────────────────────────────────

def test_destinations_load():
    dests = dest_module.load_destinations()
    assert len(dests) > 50
    for d in dests:
        assert d["iata"], f"Missing IATA: {d}"
        assert d["region"], f"Missing region: {d}"


def test_visited_load():
    visited = dest_module.load_visited()
    assert isinstance(visited, set)
    assert "DUB" in visited    # Dublin — in visited list
    assert "PRG" not in visited  # Prague — not visited


def test_filter_by_region():
    europe = dest_module.get_destinations(region="Europe")
    for d in europe:
        assert d["region"] == "Europe"


def test_exclude_country():
    dests = dest_module.get_destinations(exclude_countries=["France"])
    countries = [d["country"] for d in dests]
    assert "France" not in countries


def test_exclude_city():
    dests = dest_module.get_destinations(exclude_cities=["Dublin"])
    cities = [d["city"] for d in dests]
    assert "Dublin" not in cities


# ── Visited / new destination filtering ──────────────────────────────────────

def test_is_visited():
    dest_module.load_visited()
    assert dest_module.is_visited("DUB") is True
    assert dest_module.is_visited("PRG") is False


def test_visited_filter_new_only():
    dests = dest_module.get_destinations()
    for d in dests:
        visited = d["visited_before"]
        # new_only filter: only show non-visited
        if not visited:
            assert s._passes_visited_filter("new_only", False, "Normal") is True
        else:
            assert s._passes_visited_filter("new_only", True, "Normal") is False


def test_visited_filter_excellent_only():
    # Visited + excellent deal → allowed
    assert s._passes_visited_filter("excellent_only", True, "Excellent") is True
    # Visited + normal → blocked
    assert s._passes_visited_filter("excellent_only", True, "Normal") is False
    # New + any → allowed
    assert s._passes_visited_filter("excellent_only", False, "Good") is True


# ── Deal rating ───────────────────────────────────────────────────────────────

def test_deal_rating_europe_excellent():
    assert dr.rate_deal(300, "Europe", "one_way") == "Excellent"

def test_deal_rating_europe_great():
    assert dr.rate_deal(450, "Europe", "one_way") == "Great"

def test_deal_rating_europe_good():
    assert dr.rate_deal(650, "Europe", "one_way") == "Good"

def test_deal_rating_europe_normal():
    assert dr.rate_deal(900, "Europe", "one_way") == "Normal"

def test_deal_rating_us_excellent():
    assert dr.rate_deal(150, "United States", "one_way") == "Excellent"

def test_deal_rating_round_trip():
    assert dr.rate_deal(550, "Europe", "round_trip") == "Excellent"

def test_deal_rating_history_based():
    # Seed history
    database.save_result({
        "searched_at": "2026-01-01T00:00:00",
        "origin": "YYZ", "destination": "Dublin", "iata": "DUB",
        "country": "Ireland", "region": "Europe", "visited_before": 1,
        "trip_type": "one_way", "depart_date": "2026-01-01", "return_date": None,
        "price_cad": 800.0, "airline": "AC", "stops": 0, "duration_min": 420,
        "layovers": None, "booking_url": None, "provider": "test",
        "deal_rating": "Normal", "priority_score": 0, "is_new_low": 0,
    })
    # 600 = 25% below 800 → Excellent
    assert dr.rate_deal(600, "Europe", "one_way", iata="DUB") == "Excellent"
    # 700 = 12.5% below → Normal (less than 15%)
    assert dr.rate_deal(700, "Europe", "one_way", iata="DUB") in ("Good", "Normal")


# ── Priority scoring ──────────────────────────────────────────────────────────

def test_priority_new_excellent():
    score = dr.score_priority("Excellent", visited_before=False)
    assert score >= 60     # new(30) + excellent(40)

def test_priority_visited_normal():
    score = dr.score_priority("Normal", visited_before=True)
    assert score == 0

def test_priority_new_good():
    score_new = dr.score_priority("Good", visited_before=False)
    score_visited = dr.score_priority("Good", visited_before=True)
    assert score_new > score_visited


# ── Database ──────────────────────────────────────────────────────────────────

def test_save_and_read_result():
    row = {
        "searched_at": "2026-05-11T12:00:00",
        "origin": "YYZ", "destination": "Prague", "iata": "PRG",
        "country": "Czech Republic", "region": "Europe", "visited_before": 0,
        "trip_type": "one_way", "depart_date": "2026-10-24", "return_date": None,
        "price_cad": 420.0, "airline": "AC", "stops": 1, "duration_min": 510,
        "layovers": "LHR", "booking_url": "https://google.com/flights",
        "provider": "test", "deal_rating": "Great", "priority_score": 55, "is_new_low": 1,
    }
    rid = database.save_result(row)
    assert rid is not None

    recent = database.get_recent_results(limit=5)
    iatas = [r["iata"] for r in recent]
    assert "PRG" in iatas


def test_historical_lowest():
    database.save_result({
        "searched_at": "2026-05-11T00:00:00",
        "origin": "YYZ", "destination": "Berlin", "iata": "BER",
        "country": "Germany", "region": "Europe", "visited_before": 0,
        "trip_type": "one_way", "depart_date": "2026-10-01", "return_date": None,
        "price_cad": 395.0, "airline": "LH", "stops": 1, "duration_min": 490,
        "layovers": "FRA", "booking_url": None, "provider": "test",
        "deal_rating": "Great", "priority_score": 45, "is_new_low": 1,
    })
    low = database.get_historical_lowest("BER", "one_way")
    assert low is not None
    assert low <= 395.0


def test_is_new_low():
    # No history → always new low
    assert dr.is_new_low(999, "XYZ_TEST_NOHIST", "one_way") is True


# ── API response parsing (mock) ───────────────────────────────────────────────

def test_parse_flights_mock():
    from api_client import SerpAPIClient
    c = SerpAPIClient()
    mock_data = {
        "best_flights": [
            {
                "price": 420,
                "total_duration": 510,
                "flights": [
                    {
                        "airline": "Air Canada",
                        "departure_airport": {"id": "YYZ", "time": "2026-10-24 10:00"},
                        "arrival_airport": {"id": "LHR", "time": "2026-10-24 22:00"},
                    },
                    {
                        "airline": "Aer Lingus",
                        "departure_airport": {"id": "LHR", "time": "2026-10-24 23:30"},
                        "arrival_airport": {"id": "DUB", "time": "2026-10-25 01:00"},
                    },
                ],
            }
        ],
        "other_flights": [],
    }
    results = c._parse_flights(mock_data, "DUB", "2026-10-24", None)
    assert len(results) == 1
    r = results[0]
    assert r["price_cad"] == 420.0
    assert r["stops"] == 1
    assert r["airline"] == "Air Canada"
    assert "LHR" in r["layovers"]
    assert r["duration_min"] == 510
    assert r["iata"] == "DUB"


def test_parse_flights_mock_no_price():
    from api_client import SerpAPIClient
    c = SerpAPIClient()
    mock_data = {"best_flights": [{"flights": [{"airline": "AC"}]}], "other_flights": []}
    results = c._parse_flights(mock_data, "LHR", "2026-10-24", None)
    assert results == []  # no price → skipped
