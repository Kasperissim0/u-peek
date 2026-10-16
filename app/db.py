"""
Database layer for Room Lookup (SQLite).
Manages campuses, rooms, sync metadata, and the u:find calendar cache.
"""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "room_lookup.db"))

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    """Initializes the database schema if tables do not exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Campuses / Buildings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campuses (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                query_prefix TEXT NOT NULL,
                spl_codes TEXT DEFAULT '',
                display_order INTEGER DEFAULT 100
            )
        """)
        # Migration check for existing DB
        try:
            cursor.execute("ALTER TABLE campuses ADD COLUMN spl_codes TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Already exists
        
        # 2. Rooms table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT NOT NULL,
                campus_id TEXT NOT NULL,
                label TEXT NOT NULL,
                category TEXT NOT NULL,
                query_term TEXT NOT NULL,
                display_order INTEGER DEFAULT 100,
                last_synced TEXT NOT NULL,
                PRIMARY KEY (campus_id, id),
                FOREIGN KEY (campus_id) REFERENCES campuses(id)
            )
        """)
        
        # 3. Calendar response cache table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calendar_cache (
                cache_key TEXT PRIMARY KEY,
                ics_data TEXT NOT NULL,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 4. Sync metadata table (to record last monthly room sync)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()

def get_cached_calendar(cache_key: str, max_age_seconds: int = 21600) -> Optional[str]:
    """Retrieves cached .ics data if it is newer than max_age_seconds (default 6 hours)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ics_data, strftime('%s', 'now') - strftime('%s', fetched_at) AS age_seconds
            FROM calendar_cache
            WHERE cache_key = ?
        """, (cache_key,))
        row = cursor.fetchone()
        if row and row["age_seconds"] is not None and row["age_seconds"] < max_age_seconds:
            return row["ics_data"]
    return None

def set_cached_calendar(cache_key: str, ics_data: str):
    """Stores or updates .ics data in the cache."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO calendar_cache (cache_key, ics_data, fetched_at)
            VALUES (?, ?, datetime('now'))
        """, (cache_key, ics_data))
        conn.commit()

def get_meta(key: str) -> Optional[str]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM sync_meta WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

def set_meta(key: str, value: str):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sync_meta (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (key, value))
        conn.commit()
