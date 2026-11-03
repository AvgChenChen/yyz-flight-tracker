"""SQLite database setup and operations."""

import sqlite3
import json
from datetime import datetime
from typing import Optional
import config


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS flight_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            searched_at TEXT NOT NULL,
            origin      TEXT NOT NULL,
            destination TEXT NOT NULL,
            iata        TEXT NOT NULL,
            country     TEXT,
            region      TEXT,
            visited_before INTEGER DEFAULT 0,
            trip_type   TEXT NOT NULL,
            depart_date TEXT NOT NULL,
            return_date TEXT,
            price_cad   REAL NOT NULL,
            airline     TEXT,
            stops       INTEGER,
            duration_min INTEGER,
            layovers    TEXT,
            booking_url TEXT,
            provider    TEXT,
            deal_rating TEXT,
            priority_score INTEGER,
            is_new_low  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL,
            name        TEXT NOT NULL,
            destination TEXT,
            iata        TEXT,
            region      TEXT,
            trip_type   TEXT DEFAULT 'any',
            target_price REAL NOT NULL,
            new_only    INTEGER DEFAULT 0,
            visited_ok  INTEGER DEFAULT 1,
            active      INTEGER DEFAULT 1,
            last_triggered TEXT
        );

        CREATE TABLE IF NOT EXISTS alert_matches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id    INTEGER,
            matched_at  TEXT NOT NULL,
            destination TEXT,
            price_cad   REAL,
            depart_date TEXT,
            booking_url TEXT,
            FOREIGN KEY(alert_id) REFERENCES alerts(id)
        );
        """)


# ── Flight results ─────────────────────────────────────────────────────────────

def save_result(row: dict):
    """Insert one flight result. Returns the row id."""
    sql = """
    INSERT INTO flight_results
        (searched_at, origin, destination, iata, country, region, visited_before,
         trip_type, depart_date, return_date, price_cad, airline, stops,
         duration_min, layovers, booking_url, provider, deal_rating,
         priority_score, is_new_low)
    VALUES
        (:searched_at, :origin, :destination, :iata, :country, :region, :visited_before,
         :trip_type, :depart_date, :return_date, :price_cad, :airline, :stops,
         :duration_min, :layovers, :booking_url, :provider, :deal_rating,
         :priority_score, :is_new_low)
    """
    with get_conn() as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid


def save_results(rows: list[dict]):
    for r in rows:
        save_result(r)


def get_historical_lowest(iata: str, trip_type: str) -> Optional[float]:
    """Return the all-time lowest price seen for this destination+trip type."""
    sql = "SELECT MIN(price_cad) FROM flight_results WHERE iata=? AND trip_type=?"
    with get_conn() as conn:
        row = conn.execute(sql, (iata, trip_type)).fetchone()
        return row[0] if row and row[0] is not None else None


def get_historical_avg(iata: str, trip_type: str) -> Optional[float]:
    """Return average price for destination+trip type."""
    sql = "SELECT AVG(price_cad) FROM flight_results WHERE iata=? AND trip_type=?"
    with get_conn() as conn:
        row = conn.execute(sql, (iata, trip_type)).fetchone()
        return row[0] if row and row[0] is not None else None


def get_search_history(limit: int = 200) -> list[dict]:
    sql = """
    SELECT iata, destination, country, region, visited_before,
           MIN(price_cad) as lowest_price,
           MAX(price_cad) as highest_price,
           COUNT(*) as search_count,
           MAX(searched_at) as last_seen,
           MAX(deal_rating) as best_rating
    FROM flight_results
    GROUP BY iata, destination, trip_type
    ORDER BY last_seen DESC
    LIMIT ?
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_recent_results(limit: int = 500) -> list[dict]:
    sql = """
    SELECT * FROM flight_results
    ORDER BY searched_at DESC
    LIMIT ?
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]


# ── Alerts ────────────────────────────────────────────────────────────────────

def save_alert(alert: dict) -> int:
    sql = """
    INSERT INTO alerts (created_at, name, destination, iata, region,
                        trip_type, target_price, new_only, visited_ok, active)
    VALUES (:created_at, :name, :destination, :iata, :region,
            :trip_type, :target_price, :new_only, :visited_ok, :active)
    """
    with get_conn() as conn:
        cur = conn.execute(sql, alert)
        return cur.lastrowid


def get_alerts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def toggle_alert(alert_id: int, active: bool):
    with get_conn() as conn:
        conn.execute("UPDATE alerts SET active=? WHERE id=?", (int(active), alert_id))


def delete_alert(alert_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM alerts WHERE id=?", (alert_id,))
        conn.execute("DELETE FROM alert_matches WHERE alert_id=?", (alert_id,))


def save_alert_match(alert_id: int, result: dict):
    sql = """
    INSERT INTO alert_matches (alert_id, matched_at, destination, price_cad, depart_date, booking_url)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    with get_conn() as conn:
        conn.execute(sql, (
            alert_id,
            datetime.utcnow().isoformat(),
            result.get("destination"),
            result.get("price_cad"),
            result.get("depart_date"),
            result.get("booking_url"),
        ))
        conn.execute(
            "UPDATE alerts SET last_triggered=? WHERE id=?",
            (datetime.utcnow().isoformat(), alert_id),
        )


def get_alert_matches(limit: int = 100) -> list[dict]:
    sql = """
    SELECT am.*, a.name as alert_name, a.target_price
    FROM alert_matches am
    JOIN alerts a ON am.alert_id = a.id
    ORDER BY am.matched_at DESC
    LIMIT ?
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]
