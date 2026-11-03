#!/usr/bin/env python3
r"""
CLI script for running a search without the Streamlit UI.
Usage:
    python run_search.py --region Europe --depart 2026-10-24 --max-price 600
    python run_search.py --help

Schedule with cron (Mac/Linux):
    0 8 * * * cd /path/to/yyz-flight-tracker && python run_search.py >> logs/search.log 2>&1

Windows Task Scheduler:
    Create a task that runs: python run_search.py
    with Start In: C:\path\to\yyz-flight-tracker
"""

import argparse
import sys
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

import database
import search as s

database.init_db()


def main():
    parser = argparse.ArgumentParser(description="YYZ Flight Deal Tracker CLI")
    parser.add_argument("--origin", default="YYZ")
    parser.add_argument("--region", default="Anywhere",
                        choices=["Anywhere","Europe","Caribbean","United States",
                                 "Central America","South America","Asia","Mexico","Canada"])
    parser.add_argument("--trip-type", default="one_way", choices=["one_way","round_trip"])
    parser.add_argument("--depart", default=None, help="Departure date YYYY-MM-DD")
    parser.add_argument("--return-date", default=None, help="Return date YYYY-MM-DD")
    parser.add_argument("--max-price", type=float, default=None)
    parser.add_argument("--max-stops", type=int, default=99)
    parser.add_argument("--visited-filter", default="show_all",
                        choices=["show_all","hide_visited","new_only","excellent_only"])
    parser.add_argument("--sort", default="cheapest",
                        choices=["cheapest","best_value","fewest_stops","shortest_duration",
                                 "new_destination_priority","best_deal_rating"])
    parser.add_argument("--max-destinations", type=int, default=50,
                        help="each destination uses one SerpAPI request (free tier: 100 a month)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  YYZ Flight Deal Tracker — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"  Region: {args.region} | Trip: {args.trip_type} | Sort: {args.sort}")
    if args.depart:
        print(f"  Depart: {args.depart}" + (f" | Return: {args.return_date}" if args.return_date else ""))
    if args.max_price:
        print(f"  Max price: ${args.max_price:.0f} CAD")
    print()

    def progress(msg: str):
        print(f"  ⟶  {msg}")

    try:
        results = s.run_search(
            origin=args.origin,
            trip_type=args.trip_type,
            depart_date=args.depart,
            return_date=args.return_date,
            region=args.region,
            max_price=args.max_price,
            max_stops=args.max_stops,
            visited_filter=args.visited_filter,
            sort_by=args.sort,
            max_destinations=args.max_destinations,
            progress_cb=progress,
        )
    except ValueError as e:
        print(f"\n  ERROR: {e}\n")
        sys.exit(1)

    s.check_alerts(results)

    if not results:
        print("  No results found. Try adjusting filters.\n")
        return

    print(f"\n  Found {len(results)} deals:\n")
    print(f"  {'Deal':<12} {'Destination':<22} {'Country':<20} {'Price CAD':>10} {'New?':<6} {'Airline':<10} {'Depart'}")
    print(f"  {'-'*95}")
    for r in results[:30]:
        visited = "No" if not r.get("visited_before") else "Yes"
        new_marker = "NEW" if not r.get("visited_before") else "   "
        airline = r.get("airline") or "—"
        print(
            f"  {r.get('deal_rating',''):<12} "
            f"{r['destination']:<22} "
            f"{r['country']:<20} "
            f"${r['price_cad']:>8.0f}  "
            f"{new_marker:<6} "
            f"{airline:<10} "
            f"{r.get('depart_date','')}"
        )

    if len(results) > 30:
        print(f"\n  … and {len(results)-30} more. Run the Streamlit app for full results.")
    print()


if __name__ == "__main__":
    main()
