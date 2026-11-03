"""Load and filter the destination and visited lists."""

import csv
import logging
from typing import Optional
import config

log = logging.getLogger(__name__)

_destinations: list[dict] = []
_visited_set: set[str] = set()   # lowercase iata codes that have been visited


def _str_bool(val: str) -> bool:
    return str(val).strip().lower() in ("true", "1", "yes")


def load_destinations() -> list[dict]:
    global _destinations
    try:
        with open(config.DESTINATIONS_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            _destinations = [
                {
                    "city": r["city"].strip(),
                    "country": r["country"].strip(),
                    "region": r["region"].strip(),
                    "iata": r["iata"].strip().upper(),
                    "airport_name": r.get("airport_name", "").strip(),
                    "warm": _str_bool(r.get("warm", "false")),
                    "visited_before": _str_bool(r.get("visited_before", "false")),
                    "notes": r.get("notes", "").strip(),
                }
                for r in reader
                if r.get("iata", "").strip()
            ]
    except FileNotFoundError:
        log.error("destinations.csv not found at %s", config.DESTINATIONS_FILE)
        _destinations = []
    return _destinations


def load_visited() -> set[str]:
    global _visited_set
    try:
        with open(config.VISITED_FILE, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            _visited_set = {
                r["iata"].strip().upper()
                for r in reader
                if _str_bool(r.get("visited_before", "false"))
                and r.get("iata", "").strip()
            }
    except FileNotFoundError:
        log.warning("visited.csv not found — treating all destinations as unvisited")
        _visited_set = set()
    return _visited_set


def get_destinations(
    region: str = "Anywhere",
    exclude_countries: Optional[list[str]] = None,
    exclude_cities: Optional[list[str]] = None,
    origin_iata: str = "YYZ",
) -> list[dict]:
    """Return filtered destination list."""
    if not _destinations:
        load_destinations()
    if not _visited_set:
        load_visited()

    dests = []
    for d in _destinations:
        if d["iata"] == origin_iata:
            continue
        if region != "Anywhere" and d["region"] != region:
            continue
        if exclude_countries:
            if any(d["country"].lower() == c.lower() for c in exclude_countries):
                continue
        if exclude_cities:
            if any(d["city"].lower() == c.lower() for c in exclude_cities):
                continue

        # Merge visited status from visited.csv (overrides destinations.csv)
        d = dict(d)
        d["visited_before"] = d["iata"] in _visited_set or d["visited_before"]
        dests.append(d)

    return dests


def is_visited(iata: str) -> bool:
    if not _visited_set:
        load_visited()
    return iata in _visited_set


def dest_by_iata(iata: str) -> Optional[dict]:
    if not _destinations:
        load_destinations()
    for d in _destinations:
        if d["iata"] == iata:
            return d
    return None
