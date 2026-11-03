# YYZ flight deal tracker

Find cheap flights from Toronto Pearson (YYZ) to a region, or to anywhere on a list of about 130
destinations. It rates each fare as a deal against your own price history, flags places you
haven't been yet, saves every search, and checks results against price alerts you set.

Built with Python, Streamlit and SQLite. Fares come from Google Flights through
[SerpAPI](https://serpapi.com/google-flights-api).

## What it does

- **Search** one-way or round trip, by region (Europe, Caribbean, Asia…) or "Anywhere", with a
  maximum price, number of stops, and countries or cities to exclude.
- **Rate deals.** Once you've searched a route before, a fare is rated against its own history:
  25% or more below the average is *Excellent*, 15% *Great*, 5% *Good*. Without history, it uses
  fixed price thresholds per region (in `config.py`).
- **New places first.** Destinations you haven't visited can be shown first, filtered to, or
  weighted higher in the priority sort.
- **History and alerts.** Every result is saved in a local SQLite database. Alerts ("Europe under
  $600") are checked after each search.
- **Export** results, history and the destination list to CSV.
- **Run from the command line** (`run_search.py`), for example on a daily schedule.

## Setup

Needs Python 3.11 or newer and a SerpAPI key (the free plan allows 100 searches a month).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # then put your SerpAPI key in .env
cp data/visited.example.csv data/visited.csv   # then list the places you've been
streamlit run app.py               # opens http://localhost:8501
pytest                             # 23 tests; no key or internet needed
```

`.env`, `data/visited.csv` and the search database (`flight_tracker.db`) are listed in
`.gitignore`, so your key, travel history and searches stay on your computer.

## Watch your API usage

**Each destination is one SerpAPI request.** An "Anywhere" search checks up to 50 destinations,
so it can use half of a free month in one go. To save requests, search a region, or lower
`MAX_DESTINATIONS_PER_RUN` in `config.py` (or `--max-destinations` on the command line).

## Command line

```bash
python run_search.py --region Europe --depart 2026-12-04 --max-price 700
python run_search.py --trip-type round_trip --depart 2026-12-04 --return-date 2026-12-12 --max-price 800
python run_search.py --region Caribbean --visited-filter new_only --sort new_destination_priority
python run_search.py --help
```

## How it's organised

```
app.py             the Streamlit app: Search, Results, History, Alerts and Settings tabs
search.py          runs a search: destinations → SerpAPI → filters → ratings → database
api_client.py      the SerpAPI client and Google Flights links
deal_rating.py     deal ratings and the priority score
destinations.py    loads the destination list and your visited list
database.py        SQLite tables for results, alerts and alert matches
config.py          default origin, deal thresholds per region, request limits
run_search.py      the command-line version
data/destinations.csv       the destinations searched (edit to add or remove)
data/visited.example.csv    a made-up example of the visited list
tests/test_core.py          tests for destinations, filters, ratings and the database
```

## Limitations

- **Prices are a snapshot** of what Google Flights showed at search time, through SerpAPI. Always
  check the airline or booking site before buying.
- **"Anywhere" means the destination list**, not every airport in the world.
- **The fixed thresholds are rough** and in Canadian dollars. Ratings get better as your own
  price history builds up.
- **The free API plan is small** (see "Watch your API usage").

## How this was built

AI-assisted: the code, tests and write-up were produced with Claude Code, then reviewed. An
earlier version used the Amadeus API; it was switched to SerpAPI.

## Licence

MIT
