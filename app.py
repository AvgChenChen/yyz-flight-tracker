"""
YYZ Flight Deal Tracker — Streamlit UI
Run: streamlit run app.py
"""

import io
import os
import logging
from datetime import datetime, date, timedelta
from typing import Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import config
import database
import deal_rating as dr
import destinations as dest_module
import search as s
from api_client import client

database.init_db()
dest_module.load_destinations()
dest_module.load_visited()

log = logging.getLogger(__name__)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YYZ Flight Deal Tracker",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: 700; margin-bottom: 0; }
    .sub-header  { color: #666; margin-top: 0; font-size: 1rem; }
    .deal-excellent { background: #d4edda; border-left: 4px solid #28a745; padding: 12px 16px; border-radius: 6px; margin-bottom: 8px; }
    .deal-great     { background: #cce5ff; border-left: 4px solid #004085; padding: 12px 16px; border-radius: 6px; margin-bottom: 8px; }
    .deal-good      { background: #fff3cd; border-left: 4px solid #856404; padding: 12px 16px; border-radius: 6px; margin-bottom: 8px; }
    .deal-normal    { background: #f8f9fa; border-left: 4px solid #6c757d; padding: 12px 16px; border-radius: 6px; margin-bottom: 8px; }
    .stButton>button { width: 100%; }
</style>
""", unsafe_allow_html=True)


# ── Helper functions ──────────────────────────────────────────────────────────

def _results_to_df(results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in results:
        dur = ""
        if r.get("duration_min"):
            h, m = divmod(r["duration_min"], 60)
            dur = f"{h}h {m}m"
        rows.append({
            "Deal": dr.RATING_EMOJI.get(r.get("deal_rating", "Normal"), r.get("deal_rating", "")),
            "Priority": r.get("priority_score", 0),
            "Destination": r["destination"],
            "IATA": r["iata"],
            "Country": r["country"],
            "Region": r["region"],
            "Visited?": "Yes" if r.get("visited_before") else "No",
            "New?": "🌟 New" if not r.get("visited_before") else "",
            "Price (CAD)": r["price_cad"],
            "Airline": r.get("airline") or "—",
            "Stops": r.get("stops") if r.get("stops") is not None else "?",
            "Duration": dur or "—",
            "Depart": r.get("depart_date", ""),
            "Return": r.get("return_date") or "",
            "New Low?": "🔻 New low!" if r.get("is_new_low") else "",
            "Booking Link": r.get("booking_url", ""),
            "Updated": r.get("searched_at", "")[:16],
        })
    return pd.DataFrame(rows)


def _friendly_error(e: Exception):
    msg = str(e)
    if "API key" in msg or "credentials" in msg.lower() or "401" in msg:
        st.error("🔑 API key missing or invalid. Check the **Settings** tab for setup instructions.")
    elif "rate limit" in msg.lower() or "429" in msg:
        st.error("⏳ API rate limit reached. Wait a few minutes and try again, or reduce the number of destinations.")
    elif "timeout" in msg.lower() or "connection" in msg.lower():
        st.error("🌐 Network error. Check your internet connection and try again.")
    elif "destination" in msg.lower() and "file" in msg.lower():
        st.error("📁 Destination list not found. Make sure `data/destinations.csv` exists.")
    else:
        st.error(f"❌ Error: {msg}")
    log.exception("Search error")


# ── API Key check ─────────────────────────────────────────────────────────────
api_ok = bool(os.getenv("SERPAPI_KEY"))

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_status = st.columns([4, 1])
with col_title:
    st.markdown('<p class="main-header">✈️ YYZ Flight Deal Tracker</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Find cheap flights from Toronto (YYZ) to anywhere</p>', unsafe_allow_html=True)
with col_status:
    if api_ok:
        st.success("API Connected", icon="✅")
    else:
        st.error("API Key Missing", icon="🔑")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_search, tab_results, tab_history, tab_alerts, tab_settings = st.tabs(
    ["🔍 Search", "📊 Results", "📅 History", "🔔 Alerts", "⚙️ Settings"]
)

# ─────────────────────────────────────────────────────────────────────────────
#  SIDEBAR  (search controls)
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Search Controls")

    if not api_ok:
        st.warning(
            "⚠️ **API key not set.**\n\n"
            "Add `SERPAPI_KEY` to the `.env` file, "
            "then restart the app.\n\nSee the **Settings** tab for instructions.",
        )

    origin = st.text_input("Origin airport", value=config.DEFAULT_ORIGIN, max_chars=3).upper()

    trip_type = st.radio("Trip type", ["One-way", "Round trip"], horizontal=True)
    is_round = trip_type == "Round trip"

    tomorrow = date.today() + timedelta(days=1)
    depart_date = st.date_input("Departure date", value=tomorrow, min_value=tomorrow)

    return_date = None
    if is_round:
        min_ret = depart_date + timedelta(days=1)
        return_date = st.date_input("Return date", value=min_ret, min_value=min_ret)
        if return_date <= depart_date:
            st.error("Return date must be after departure date.")

    st.divider()

    region = st.selectbox("Destination region", config.REGIONS, index=0)

    max_price = st.number_input(
        "Max price (CAD)", min_value=0, max_value=10000, value=0, step=50,
        help="Set to 0 for no limit",
    )
    max_price_val = float(max_price) if max_price > 0 else None

    max_stops_label = st.selectbox("Max stops", ["Any", "Nonstop only", "Max 1 stop"])
    max_stops = {"Any": 99, "Nonstop only": 0, "Max 1 stop": 1}[max_stops_label]

    st.divider()

    visited_filter = st.selectbox(
        "Visited destination filter",
        ["Show all", "Hide visited", "New destinations only", "Visited only if Excellent deal"],
    )
    vf_map = {
        "Show all": "show_all",
        "Hide visited": "hide_visited",
        "New destinations only": "new_only",
        "Visited only if Excellent deal": "excellent_only",
    }
    visited_filter_val = vf_map[visited_filter]

    sort_by = st.selectbox(
        "Sort by",
        ["Cheapest", "Best value", "Fewest stops", "Shortest duration",
         "New destination priority", "Best deal rating"],
    )
    sort_map = {
        "Cheapest": "cheapest",
        "Best value": "best_value",
        "Fewest stops": "fewest_stops",
        "Shortest duration": "shortest_duration",
        "New destination priority": "new_destination_priority",
        "Best deal rating": "best_deal_rating",
    }
    sort_by_val = sort_map[sort_by]

    with st.expander("Advanced filters"):
        exclude_countries_raw = st.text_input(
            "Exclude countries (comma-separated)", "",
            placeholder="e.g. France, Germany"
        )
        exclude_cities_raw = st.text_input(
            "Exclude cities (comma-separated)", "",
            placeholder="e.g. Paris, Munich"
        )
        max_dests = st.slider("Max destinations to search", 5, 120, 50, 5)

    exclude_countries = [c.strip() for c in exclude_countries_raw.split(",") if c.strip()]
    exclude_cities = [c.strip() for c in exclude_cities_raw.split(",") if c.strip()]

    # Preview count
    preview_dests = dest_module.get_destinations(
        region=region,
        exclude_countries=exclude_countries,
        exclude_cities=exclude_cities,
        origin_iata=origin,
    )
    dest_count = min(len(preview_dests), max_dests)
    st.caption(f"Destinations to search: **{dest_count}**")

    if dest_count > 40:
        st.warning(f"Searching {dest_count} destinations will use ~{dest_count} API calls.", icon="⚠️")

    if exclude_countries:
        st.caption(f"🚫 Excluding countries: {', '.join(exclude_countries)}")
    if exclude_cities:
        st.caption(f"🚫 Excluding cities: {', '.join(exclude_cities)}")

    st.divider()
    search_btn = st.button("🔍 Search Flights", type="primary", disabled=not api_ok)
    reset_btn = st.button("↺ Reset filters")

    if reset_btn:
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  SEARCH TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_search:
    if not api_ok:
        st.info(
            "### 👋 Welcome to YYZ Flight Deal Tracker!\n\n"
            "To get started:\n"
            "1. Get a **free SerpAPI key** at [serpapi.com](https://serpapi.com) — it's on your dashboard instantly after signup\n"
            "2. Copy `.env.example` to `.env` in the project folder and paste in your key\n"
            "3. Restart the app (`Ctrl+C` then `streamlit run app.py`)\n"
            "4. Use the **Search Controls** in the left sidebar\n\n"
            "The SerpAPI free tier gives you **100 searches/month**. Search by region to save quota.",
            icon="ℹ️",
        )
    else:
        st.markdown("### Ready to search")
        c1, c2, c3 = st.columns(3)
        c1.metric("Origin", origin)
        c2.metric("Trip type", trip_type)
        c3.metric("Region", region)
        if max_price_val:
            st.caption(f"Max price: **${max_price_val:.0f} CAD** | Filter: **{visited_filter}** | Sort: **{sort_by}**")
        else:
            st.caption(f"No price limit | Filter: **{visited_filter}** | Sort: **{sort_by}**")
        st.info("👈 Configure your search in the sidebar, then click **Search Flights**.")

    if search_btn:
        if is_round and (not return_date or return_date <= depart_date):
            st.error("Please fix the return date before searching.")
        else:
            with st.spinner("Searching flights…"):
                status_placeholder = st.empty()

                def update_progress(msg: str):
                    status_placeholder.caption(f"⟶ {msg}")

                st.session_state["last_results"] = []
                try:
                    results = s.run_search(
                        origin=origin,
                        trip_type="round_trip" if is_round else "one_way",
                        depart_date=depart_date.strftime("%Y-%m-%d"),
                        return_date=return_date.strftime("%Y-%m-%d") if return_date else None,
                        region=region,
                        max_price=max_price_val,
                        max_stops=max_stops,
                        exclude_countries=exclude_countries,
                        exclude_cities=exclude_cities,
                        visited_filter=visited_filter_val,
                        sort_by=sort_by_val,
                        max_destinations=max_dests,
                        progress_cb=update_progress,
                    )
                    st.session_state["last_results"] = results
                    st.session_state["last_search_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    s.check_alerts(results)
                    status_placeholder.empty()
                    st.success(f"Found {len(results)} deals! Switch to the **Results** tab to view them.")
                except Exception as e:
                    status_placeholder.empty()
                    _friendly_error(e)


# ─────────────────────────────────────────────────────────────────────────────
#  RESULTS TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_results:
    results = st.session_state.get("last_results", [])
    search_time = st.session_state.get("last_search_time", "Never")

    if not results:
        st.info(
            "No results yet. Run a search from the **Search** tab.\n\n"
            "If a search returned nothing, try:\n"
            "- Increasing the max price\n"
            "- Allowing more stops\n"
            "- Expanding the destination region",
            icon="ℹ️",
        )
    else:
        st.caption(f"Last updated: {search_time}")

        # ── Summary cards ─────────────────────────────────────────────────────
        cheapest = min(results, key=lambda r: r["price_cad"])
        new_dests = [r for r in results if not r.get("visited_before")]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cheapest flight", f"${cheapest['price_cad']:.0f} CAD", cheapest["destination"])
        m2.metric("Destinations found", len(results))
        m3.metric("Excellent/Great deals",
                  len([r for r in results if r.get("deal_rating") in ("Excellent", "Great")]))
        m4.metric("New destinations", len(new_dests))

        st.divider()

        # ── Top 3 deal cards ──────────────────────────────────────────────────
        top3 = results[:3]
        st.subheader("Top Deals")
        cols = st.columns(len(top3))
        for col, r in zip(cols, top3):
            with col:
                rating = r.get("deal_rating", "Normal")
                css_class = f"deal-{rating.lower()}"
                visited_tag = "🔁 Visited before" if r.get("visited_before") else "🌟 New destination"
                stops_str = (
                    "Nonstop" if r.get("stops") == 0
                    else f"{r.get('stops', '?')} stop(s)" if r.get("stops") is not None
                    else "?"
                )
                dur = ""
                if r.get("duration_min"):
                    h, m = divmod(r["duration_min"], 60)
                    dur = f"{h}h {m}m"
                else:
                    dur = "—"
                st.markdown(f"""
<div class="{css_class}">
  <strong>{dr.RATING_EMOJI.get(rating, rating)}</strong><br>
  <span style="font-size:1.3rem; font-weight:700">{r['destination']}</span>
  <span style="color:#666"> ({r['iata']})</span><br>
  {r['country']} · {r['region']}<br>
  <span style="font-size:1.2rem; font-weight:700; color:#155724">${r['price_cad']:.0f} CAD</span><br>
  {visited_tag}<br>
  ✈️ {r.get('airline') or '—'} &nbsp;|&nbsp; {stops_str} &nbsp;|&nbsp; {dur}<br>
  📅 {r.get('depart_date', '—')}{"  →  " + r['return_date'] if r.get('return_date') else ""}
  <br><br>
  <a href="{r.get('booking_url', '#')}" target="_blank">🔗 Search on Google Flights</a>
</div>
""", unsafe_allow_html=True)

        st.divider()

        # ── Results table ──────────────────────────────────────────────────────
        st.subheader(f"All Results ({len(results)})")
        df = _results_to_df(results)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Price (CAD)": st.column_config.NumberColumn(format="$%.0f"),
                "Booking Link": st.column_config.LinkColumn("Book"),
                "Priority": st.column_config.NumberColumn(),
            },
        )

        # ── Export ─────────────────────────────────────────────────────────────
        csv_bytes = df.to_csv(index=False).encode()
        st.download_button(
            "⬇️ Download results as CSV",
            data=csv_bytes,
            file_name=f"yyz_flights_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )


# ─────────────────────────────────────────────────────────────────────────────
#  HISTORY TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_history:
    st.subheader("Price History")

    hist = database.get_search_history(limit=300)
    if not hist:
        st.info("No search history yet. Run a search to start building your price database.", icon="ℹ️")
    else:
        df_hist = pd.DataFrame(hist)
        df_hist.rename(columns={
            "destination": "City", "country": "Country", "region": "Region",
            "iata": "IATA", "lowest_price": "Lowest (CAD)", "highest_price": "Highest (CAD)",
            "last_seen": "Last Seen", "search_count": "Searches", "best_rating": "Best Deal",
            "visited_before": "Visited?",
        }, inplace=True)
        df_hist["Visited?"] = df_hist["Visited?"].map({1: "Yes", 0: "No", True: "Yes", False: "No"})
        df_hist["Lowest (CAD)"] = df_hist["Lowest (CAD)"].map(lambda x: f"${x:.0f}" if x else "—")
        df_hist["Highest (CAD)"] = df_hist["Highest (CAD)"].map(lambda x: f"${x:.0f}" if x else "—")

        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        csv_hist = pd.DataFrame(hist).to_csv(index=False).encode()
        st.download_button("⬇️ Download history as CSV", data=csv_hist,
                           file_name="yyz_history.csv", mime="text/csv")


# ─────────────────────────────────────────────────────────────────────────────
#  ALERTS TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_alerts:
    st.subheader("Deal Alerts")
    st.caption("Create alerts and we'll flag matching flights after each search.")

    with st.expander("➕ Create new alert", expanded=True):
        a_name = st.text_input("Alert name", placeholder="e.g. Europe under $600")
        a_region = st.selectbox("Region", ["Any"] + config.REGIONS[1:], key="a_region")
        a_iata = st.text_input("Specific destination IATA (optional)", placeholder="e.g. DUB",
                               max_chars=3).upper()
        a_trip = st.selectbox("Trip type", ["Any", "One-way", "Round trip"], key="a_trip")
        a_price = st.number_input("Target price (CAD)", min_value=1, max_value=10000, value=500)
        a_new_only = st.checkbox("New destinations only")
        a_visited_ok = st.checkbox("Include visited destinations", value=True)

        if st.button("✅ Create Alert"):
            if not a_name:
                st.error("Please enter an alert name.")
            else:
                trip_val = {"Any": "any", "One-way": "one_way", "Round trip": "round_trip"}[a_trip]
                database.save_alert({
                    "created_at": datetime.utcnow().isoformat(),
                    "name": a_name,
                    "destination": None,
                    "iata": a_iata or None,
                    "region": None if a_region == "Any" else a_region,
                    "trip_type": trip_val,
                    "target_price": a_price,
                    "new_only": int(a_new_only),
                    "visited_ok": int(a_visited_ok),
                    "active": 1,
                })
                st.success(f"Alert '{a_name}' created!")
                st.rerun()

    st.divider()

    alerts = database.get_alerts()
    if not alerts:
        st.info("No alerts yet. Create one above.", icon="ℹ️")
    else:
        for alert in alerts:
            col1, col2, col3 = st.columns([5, 1, 1])
            with col1:
                tags = []
                if alert.get("iata"):
                    tags.append(f"→ {alert['iata']}")
                if alert.get("region"):
                    tags.append(alert["region"])
                if alert.get("new_only"):
                    tags.append("New dests only")
                tag_str = " · ".join(tags) if tags else "Any destination"
                trip_disp = {"any": "Any", "one_way": "One-way", "round_trip": "Round trip"}.get(
                    alert.get("trip_type", "any"), "Any")
                st.write(
                    f"**{alert['name']}** — Under ${alert['target_price']:.0f} CAD "
                    f"| {trip_disp} | {tag_str}"
                )
                if alert.get("last_triggered"):
                    st.caption(f"Last matched: {alert['last_triggered'][:16]}")
            with col2:
                is_active = bool(alert["active"])
                label = "🟢 Active" if is_active else "⚪ Paused"
                if st.button(label, key=f"toggle_{alert['id']}"):
                    database.toggle_alert(alert["id"], not is_active)
                    st.rerun()
            with col3:
                if st.button("🗑️ Delete", key=f"del_{alert['id']}"):
                    database.delete_alert(alert["id"])
                    st.rerun()

    st.divider()
    st.subheader("Recent Alert Matches")
    matches = database.get_alert_matches(limit=50)
    if not matches:
        st.caption("No alert matches yet.")
    else:
        df_m = pd.DataFrame(matches)[["alert_name", "destination", "price_cad", "depart_date", "matched_at"]]
        df_m.columns = ["Alert", "Destination", "Price (CAD)", "Depart", "Matched At"]
        df_m["Price (CAD)"] = df_m["Price (CAD)"].map(lambda x: f"${x:.0f}")
        st.dataframe(df_m, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SETTINGS TAB
# ─────────────────────────────────────────────────────────────────────────────
with tab_settings:
    st.subheader("Settings & Configuration")

    with st.expander("🔑 API Setup", expanded=not api_ok):
        st.markdown("""
**How to get your free SerpAPI key:**

1. Go to [serpapi.com](https://serpapi.com) and create a free account
2. Your API key is shown immediately on the dashboard
3. Open the `.env` file in the project folder and add:

```
SERPAPI_KEY=your_key_here
```

4. Save the file and restart the app (`Ctrl+C` → `streamlit run app.py`)

**Free tier:** 100 searches/month. Each destination you search = 1 search.
**Tip:** Search a specific region (e.g. Caribbean = ~15 destinations) instead of "Anywhere" to conserve quota.
""")
        if api_ok:
            st.success("✅ API keys are set and ready.")
        else:
            st.error("❌ API keys not set. Follow the steps above.")

    with st.expander("🗺️ Destinations"):
        st.markdown("""
**Adding destinations:** Edit `data/destinations.csv` — add a new row:
```
city, country, region, iata, airport_name, warm (true/false), visited_before (true/false), notes
```

**Marking as visited:** Edit `data/visited.csv` — add the city/country/IATA with `visited_before=true`.

**Regions available:** Europe, Caribbean, United States, Central America, South America, Asia, Mexico, Canada
""")
        dests = dest_module.get_destinations()
        df_d = pd.DataFrame(dests)
        st.dataframe(df_d, use_container_width=True, hide_index=True)
        csv_d = df_d.to_csv(index=False).encode()
        st.download_button("⬇️ Download destinations CSV", data=csv_d,
                           file_name="destinations.csv", mime="text/csv")

    with st.expander("💰 Deal Thresholds (CAD)"):
        st.markdown("Edit `config.py` to change these thresholds.")
        thresh_rows = []
        for rgn, tt_dict in config.DEAL_THRESHOLDS.items():
            for trip, vals in tt_dict.items():
                thresh_rows.append({
                    "Region": rgn, "Trip type": trip,
                    "Excellent (≤)": f"${vals['excellent']}",
                    "Great (≤)": f"${vals['great']}",
                    "Good (≤)": f"${vals['good']}",
                })
        st.dataframe(pd.DataFrame(thresh_rows), use_container_width=True, hide_index=True)

    with st.expander("🔄 Automation — Schedule Daily Searches"):
        project_dir = os.path.dirname(os.path.abspath(__file__))
        st.markdown(f"""
**Run manually from terminal:**
```bash
cd "{project_dir}"
python run_search.py --region Europe --trip-type round_trip --max-price 800
```

**Mac/Linux cron (daily at 8am) — run `crontab -e` and add:**
```
0 8 * * * cd "{project_dir}" && python run_search.py >> logs/search.log 2>&1
```

**Windows Task Scheduler:**
- New task → Daily trigger
- Action: Start Program → `python`
- Arguments: `run_search.py`
- Start in: `{project_dir}`
""")

    with st.expander("🗃️ Database"):
        st.caption(f"Database: `{config.DB_FILE}`")
        recent = database.get_recent_results(limit=5)
        if recent:
            st.write(f"Last {len(recent)} stored results:")
            st.dataframe(
                pd.DataFrame(recent)[["searched_at", "destination", "iata", "price_cad", "deal_rating"]],
                hide_index=True,
            )
        else:
            st.caption("No results stored yet.")

        all_results = database.get_recent_results(limit=10000)
        if all_results:
            csv_all = pd.DataFrame(all_results).to_csv(index=False).encode()
            st.download_button("⬇️ Download all stored results as CSV", data=csv_all,
                               file_name="yyz_all_results.csv", mime="text/csv")
