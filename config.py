"""Central configuration — edit thresholds, defaults, and regions here."""

import os

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_ORIGIN = "YYZ"
DEFAULT_CURRENCY = "CAD"
MAX_DESTINATIONS_PER_RUN = 50       # cap to avoid hammering the API
API_REQUEST_DELAY_SEC = 0.5         # polite delay between requests

# ── Deal thresholds (CAD) ─────────────────────────────────────────────────────
# Used when there is no historical data to compare against.
# Format: {region: {trip_type: {"excellent": X, "great": Y, "good": Z}}}
DEAL_THRESHOLDS = {
    "Europe": {
        "one_way":    {"excellent": 350, "great": 500, "good": 700},
        "round_trip": {"excellent": 600, "great": 900, "good": 1200},
    },
    "Caribbean": {
        "one_way":    {"excellent": 250, "great": 350, "good": 500},
        "round_trip": {"excellent": 500, "great": 700, "good": 900},
    },
    "United States": {
        "one_way":    {"excellent": 180, "great": 250, "good": 380},
        "round_trip": {"excellent": 350, "great": 500, "good": 700},
    },
    "Central America": {
        "one_way":    {"excellent": 300, "great": 450, "good": 600},
        "round_trip": {"excellent": 600, "great": 850, "good": 1100},
    },
    "South America": {
        "one_way":    {"excellent": 450, "great": 650, "good": 900},
        "round_trip": {"excellent": 750, "great": 1100, "good": 1500},
    },
    "Asia": {
        "one_way":    {"excellent": 650, "great": 900, "good": 1200},
        "round_trip": {"excellent": 1000, "great": 1400, "good": 1800},
    },
    "Mexico": {
        "one_way":    {"excellent": 250, "great": 380, "good": 520},
        "round_trip": {"excellent": 500, "great": 700, "good": 950},
    },
    "Canada": {
        "one_way":    {"excellent": 120, "great": 200, "good": 300},
        "round_trip": {"excellent": 250, "great": 400, "good": 550},
    },
    "Default": {
        "one_way":    {"excellent": 400, "great": 600, "good": 900},
        "round_trip": {"excellent": 700, "great": 1000, "good": 1400},
    },
}

# % below historical average to qualify as deal
DEAL_PCT = {"excellent": 25, "great": 15, "good": 5}

# Priority score weights
PRIORITY_WEIGHTS = {
    "new_destination": 30,
    "excellent_deal": 40,
    "great_deal": 25,
    "good_deal": 10,
    "visited_excellent": 20,
}

# ── Regions ───────────────────────────────────────────────────────────────────
REGIONS = [
    "Anywhere",
    "Europe",
    "Caribbean",
    "United States",
    "Central America",
    "South America",
    "Asia",
    "Mexico",
    "Canada",
]

# ── File paths ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DESTINATIONS_FILE = os.path.join(DATA_DIR, "destinations.csv")
# Your own list of places you've been is private and not committed. Without it, the app uses a
# short made-up example so it still runs.
VISITED_FILE = os.path.join(DATA_DIR, "visited.csv")
if not os.path.exists(VISITED_FILE):
    VISITED_FILE = os.path.join(DATA_DIR, "visited.example.csv")
DB_FILE = os.path.join(BASE_DIR, "flight_tracker.db")
