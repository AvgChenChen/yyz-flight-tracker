"""
Search orchestrator.
Coordinates API calls, destination filtering, deal rating, and DB persistence.
"""

import time
import logging
from datetime import datetime
from typing import Optional, Callable

import config
import database
import deal_rating as dr
import destinations as dest_module
from api_client import client, build_google_flights_url

log = logging.getLogger(__name__)


def run_search(
    origin: str = config.DEFAULT_ORIGIN,
    trip_type: str = "one_way",             # "one_way" | "round_trip"
    depart_date: Optional[str] = None,      # YYYY-MM-DD
    return_date: Optional[str] = None,
    region: str = "Anywhere",
    max_price: Optional[float] = None,
    max_stops: int = 99,
    exclude_countries: Optional[list[str]] = None,
    exclude_cities: Optional[list[str]] = None,
    visited_filter: str = "show_all",       # show_all|hide_visited|new_only|excellent_only
    sort_by: str = "cheapest",
    max_destinations: int = config.MAX_DESTINATIONS_PER_RUN,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """
    Returns a list of enriched flight result dicts sorted per sort_by.

    Each destination is one SerpAPI request, so a search uses up to max_destinations requests.
    """
    if not client._check_credentials():
        raise ValueError(
            "SerpAPI key not set. Add SERPAPI_KEY to your .env file. "
            "Get a free key at serpapi.com."
        )

    dests = dest_module.get_destinations(
        region=region,
        exclude_countries=exclude_countries or [],
        exclude_cities=exclude_cities or [],
        origin_iata=origin,
    )[:max_destinations]

    if not dests:
        return []

    searched_at = datetime.utcnow().isoformat()
    results: list[dict] = []

    # ── Per-destination search ────────────────────────────────────────────────
    for i, d in enumerate(dests):
        iata = d["iata"]
        if progress_cb:
            progress_cb(f"[{i+1}/{len(dests)}] Searching {d['city']} ({iata})…")

        try:
            offers = client.search_offers(
                origin=origin,
                destination=iata,
                depart_date=depart_date or _today_str(),
                return_date=return_date if trip_type == "round_trip" else None,
                max_price=int(max_price) if max_price else None,
                max_results=3,
            )
        except Exception as e:
            log.warning("No offers for %s: %s", iata, e)
            offers = []

        for offer in offers:
            price = offer["price_cad"]
            if max_price and price > max_price:
                continue
            if max_stops < 99 and offer.get("stops", 0) > max_stops:
                continue

            rating = dr.rate_deal(price, d["region"], trip_type, iata)
            visited = d["visited_before"]

            if not _passes_visited_filter(visited_filter, visited, rating):
                continue

            priority = dr.score_priority(rating, visited)
            is_low = dr.is_new_low(price, iata, trip_type)

            booking_url = build_google_flights_url(
                origin, iata,
                offer.get("depart_date", depart_date or ""),
                return_date=offer.get("return_date") if trip_type == "round_trip" else None,
            )

            row = _build_row(
                searched_at=searched_at,
                origin=origin,
                dest=d,
                trip_type=trip_type,
                depart_date=offer.get("depart_date", depart_date or ""),
                return_date=offer.get("return_date"),
                price_cad=price,
                airline=offer.get("airline"),
                stops=offer.get("stops"),
                duration_min=offer.get("duration_min"),
                layovers=offer.get("layovers"),
                booking_url=booking_url,
                provider="SerpAPI Google Flights",
                deal_rating=rating,
                priority_score=priority,
                is_new_low=int(is_low),
            )
            results.append(row)
            database.save_result(row)

        time.sleep(config.API_REQUEST_DELAY_SEC)

    return _sort_results(results, sort_by)


def _passes_visited_filter(filter_mode: str, visited: bool, rating: str) -> bool:
    if filter_mode == "show_all":
        return True
    if filter_mode == "hide_visited":
        return not visited
    if filter_mode == "new_only":
        return not visited
    if filter_mode == "excellent_only":
        return not visited or rating == "Excellent"
    return True


def _build_row(**kw) -> dict:
    d = kw.pop("dest")
    return {
        "searched_at": kw["searched_at"],
        "origin": kw["origin"],
        "destination": d["city"],
        "iata": d["iata"],
        "country": d["country"],
        "region": d["region"],
        "visited_before": int(d["visited_before"]),
        "trip_type": kw["trip_type"],
        "depart_date": kw["depart_date"],
        "return_date": kw.get("return_date"),
        "price_cad": kw["price_cad"],
        "airline": kw.get("airline"),
        "stops": kw.get("stops"),
        "duration_min": kw.get("duration_min"),
        "layovers": kw.get("layovers"),
        "booking_url": kw.get("booking_url"),
        "provider": kw.get("provider"),
        "deal_rating": kw.get("deal_rating"),
        "priority_score": kw.get("priority_score"),
        "is_new_low": kw.get("is_new_low", 0),
    }


def _sort_results(results: list[dict], sort_by: str) -> list[dict]:
    key_map = {
        "cheapest": lambda r: r["price_cad"],
        "best_value": lambda r: -r.get("priority_score", 0),
        "fewest_stops": lambda r: (r.get("stops") or 99),
        "shortest_duration": lambda r: (r.get("duration_min") or 9999),
        "new_destination_priority": lambda r: (int(r.get("visited_before", 0)), r["price_cad"]),
        "best_deal_rating": lambda r: (
            ["Excellent","Great","Good","Normal"].index(r.get("deal_rating","Normal")),
            r["price_cad"]
        ),
    }
    key = key_map.get(sort_by, key_map["cheapest"])
    return sorted(results, key=key)


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def check_alerts(results: list[dict]):
    """Check results against saved alerts and record matches."""
    alerts = database.get_alerts()
    for alert in alerts:
        if not alert["active"]:
            continue
        for r in results:
            if r["price_cad"] > alert["target_price"]:
                continue
            if alert.get("iata") and r["iata"] != alert["iata"]:
                continue
            if alert.get("region") and alert["region"] != "Anywhere" and r["region"] != alert["region"]:
                continue
            if alert.get("trip_type") and alert["trip_type"] != "any" and r["trip_type"] != alert["trip_type"]:
                continue
            if alert.get("new_only") and r.get("visited_before"):
                continue
            if not alert.get("visited_ok") and r.get("visited_before"):
                continue
            database.save_alert_match(alert["id"], r)
            log.info("ALERT HIT: %s — %s $%.0f CAD", alert["name"], r["destination"], r["price_cad"])
