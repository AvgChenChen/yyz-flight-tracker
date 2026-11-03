"""Deal rating and priority scoring logic."""

import config
import database


def rate_deal(price: float, region: str, trip_type: str,
              iata: str = "") -> str:
    """
    Return 'Excellent', 'Great', 'Good', or 'Normal'.
    Prefers historical data; falls back to static thresholds.
    """
    # Try history-based rating first
    if iata:
        avg = database.get_historical_avg(iata, trip_type)
        if avg and avg > 0:
            pct_below = (avg - price) / avg * 100
            if pct_below >= config.DEAL_PCT["excellent"]:
                return "Excellent"
            if pct_below >= config.DEAL_PCT["great"]:
                return "Great"
            if pct_below >= config.DEAL_PCT["good"]:
                return "Good"
            return "Normal"

    # Fall back to static thresholds
    thresholds = config.DEAL_THRESHOLDS.get(region, config.DEAL_THRESHOLDS["Default"])
    tt = "round_trip" if trip_type == "round_trip" else "one_way"
    t = thresholds.get(tt, thresholds.get("one_way", {}))

    if price <= t.get("excellent", float("inf")):
        return "Excellent"
    if price <= t.get("great", float("inf")):
        return "Great"
    if price <= t.get("good", float("inf")):
        return "Good"
    return "Normal"


def score_priority(deal_rating: str, visited_before: bool) -> int:
    """
    Higher score = higher priority in results.
    New destination with excellent deal = 70 points.
    """
    w = config.PRIORITY_WEIGHTS
    score = 0

    if deal_rating == "Excellent":
        score += w["excellent_deal"]
    elif deal_rating == "Great":
        score += w["great_deal"]
    elif deal_rating == "Good":
        score += w["good_deal"]

    if not visited_before:
        score += w["new_destination"]
    elif deal_rating == "Excellent":
        score += w["visited_excellent"]

    return score


def is_new_low(price: float, iata: str, trip_type: str) -> bool:
    lowest = database.get_historical_lowest(iata, trip_type)
    return lowest is None or price < lowest


RATING_EMOJI = {
    "Excellent": "🔥 Excellent",
    "Great": "⭐ Great",
    "Good": "👍 Good",
    "Normal": "Normal",
}

RATING_COLOR = {
    "Excellent": "#d4edda",
    "Great": "#cce5ff",
    "Good": "#fff3cd",
    "Normal": "#f8f9fa",
}
