"""
SerpAPI — Google Flights client.
Docs: https://serpapi.com/google-flights-api
Free tier: 100 searches/month. Sign up at serpapi.com.

Endpoint: GET https://serpapi.com/search.json?engine=google_flights
"""

import os
import logging
from datetime import datetime
from typing import Optional
import requests
from dotenv import load_dotenv
import config

load_dotenv()
log = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"


class SerpAPIClient:
    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY", "")

    def _check_credentials(self) -> bool:
        return bool(self.api_key)

    def search_offers(
        self,
        origin: str,
        destination: str,
        depart_date: str,           # YYYY-MM-DD
        return_date: Optional[str] = None,
        adults: int = 1,
        max_price: Optional[int] = None,
        max_results: int = 5,
    ) -> list[dict]:
        """Search Google Flights for a specific route, within the requested limits."""
        if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results < 0:
            raise ValueError("max_results must be a non-negative integer")
        if max_results == 0:
            return []
        params = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": depart_date,
            "currency": "CAD",
            "hl": "en",
            "adults": adults,
            "api_key": self.api_key,
            "type": "1" if return_date else "2",  # 1=round-trip, 2=one-way
        }
        if return_date:
            params["return_date"] = return_date
        if max_price is not None:
            params["max_price"] = max_price

        try:
            resp = requests.get(SERPAPI_URL, params=params, timeout=20)
            if resp.status_code == 401:
                raise RuntimeError("Invalid SerpAPI key. Check your .env file.")
            if resp.status_code == 429:
                raise RuntimeError("SerpAPI rate limit reached. Try again later.")
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise RuntimeError(f"SerpAPI error: {data['error']}")

            offers = self._parse_flights(data, destination, depart_date, return_date)
            if max_price is not None:
                offers = [offer for offer in offers if offer["price_cad"] <= max_price]
            return offers[:max_results]

        except requests.exceptions.ConnectionError:
            raise RuntimeError("Network error. Check your internet connection.")
        except requests.exceptions.Timeout:
            raise RuntimeError("Request timed out. Try again.")

    def _parse_flights(
        self, data: dict, destination: str,
        depart_date: str, return_date: Optional[str]
    ) -> list[dict]:
        results = []

        # SerpAPI returns best_flights and other_flights
        all_flights = data.get("best_flights", []) + data.get("other_flights", [])

        for flight in all_flights:
            price = flight.get("price")
            if not price:
                continue

            legs = flight.get("flights", [])
            if not legs:
                continue

            first_leg = legs[0]
            last_leg = legs[-1]

            depart_dt = first_leg.get("departure_airport", {}).get("time", depart_date)
            airline = first_leg.get("airline", "")
            stops = len(legs) - 1
            layovers = [
                leg.get("arrival_airport", {}).get("id", "")
                for leg in legs[:-1]
            ]
            total_duration = flight.get("total_duration", 0)  # minutes

            results.append({
                "iata": destination,
                "depart_date": depart_dt[:10] if depart_dt else depart_date,
                "depart_time": depart_dt[11:16] if len(str(depart_dt)) > 10 else "",
                "return_date": return_date,
                "price_cad": float(price),
                "airline": airline,
                "stops": stops,
                "duration_min": total_duration,
                "layovers": ",".join(filter(None, layovers)),
            })

        return results


def build_google_flights_url(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: Optional[str] = None,
) -> str:
    """Deep link to Google Flights for this route."""
    base = "https://www.google.com/travel/flights"
    if return_date:
        return (f"{base}?q=flights+from+{origin}+to+{destination}"
                f"+on+{depart_date}+returning+{return_date}")
    return f"{base}?q=one+way+flights+from+{origin}+to+{destination}+on+{depart_date}"


# Module-level singleton
client = SerpAPIClient()
