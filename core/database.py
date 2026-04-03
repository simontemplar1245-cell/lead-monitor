"""
Database Layer
==============
SQLite database for storing leads, tracking duplicates, and providing
statistics for the dashboard.

Tables:
- leads: All discovered leads with classification data
- scan_logs: Record of each scan run for system health monitoring
- stats_daily: Aggregated daily statistics for the dashboard
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class LeadDatabase:
    """SQLite database manager for lead tracking and deduplication."""

    def __init__(self, db_path: str):
        """Initialize database connection and create tables if needed."""
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new database connection (SQLite is not thread-safe with shared connections)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
        return conn

    def _init_db(self):
        """Create all tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT UNIQUE NOT NULL,
                    platform TEXT NOT NULL,
                    community TEXT NOT NULL,
                    author TEXT,
                    title TEXT,
                    body TEXT,
                    url TEXT,
                    score REAL DEFAULT 0.0,
                    category TEXT DEFAULT 'COLD',
                    keyword_matched TEXT,
                    keyword_category TEXT,
                    reasoning TEXT,
                    suggested_reply TEXT,
                    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    post_created_at TIMESTAMP,

                    -- User interaction tracking (for dashboard conversion stats)
                    replied BOOLEAN DEFAULT 0,
                    replied_at TIMESTAMP,
                    response_received BOOLEAN DEFAULT 0,
                    response_received_at TIMESTAMP,
                    converted BOOLEAN DEFAULT 0,
                    converted_at TIMESTAMP,
                    notes TEXT
                );

                CREATE TABLE IF NOT EXISTS scan_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    platform TEXT NOT NULL,
                    community TEXT,
                    posts_scanned INTEGER DEFAULT 0,
                    leads_found INTEGER DEFAULT 0,
                    hot_leads INTEGER DEFAULT 0,
                    warm_leads INTEGER DEFAULT 0,
                    cold_leads INTEGER DEFAULT 0,
                    errors TEXT,
                    duration_seconds REAL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS stats_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    total_scanned INTEGER DEFAULT 0,
                    total_leads INTEGER DEFAULT 0,
                    hot_leads INTEGER DEFAULT 0,
                    warm_leads INTEGER DEFAULT 0,
                    cold_leads INTEGER DEFAULT 0,
                    replies_sent INTEGER DEFAULT 0,
                    responses_received INTEGER DEFAULT 0,
                    conversions INTEGER DEFAULT 0,
                    top_platform TEXT,
                    top_keyword TEXT
                );

                -- Indexes for fast lookups
                CREATE INDEX IF NOT EXISTS idx_leads_post_id ON leads(post_id);
                CREATE INDEX IF NOT EXISTS idx_leads_category ON leads(category);
                CREATE INDEX IF NOT EXISTS idx_leads_platform ON leads(platform);
                CREATE INDEX IF NOT EXISTS idx_leads_discovered ON leads(discovered_at);
                CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score DESC);
                CREATE INDEX IF NOT EXISTS idx_scan_logs_time ON scan_logs(scan_time);
                CREATE INDEX IF NOT EXISTS idx_stats_date ON stats_daily(date);
            """)
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
        finally:
            conn.close()

    # =========================================================================
    # LEAD OPERATIONS
    # =========================================================================

    def is_duplicate(self, post_id: str) -> bool:
        """Check if we've already seen this post (deduplication)."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT 1 FROM leads WHERE post_id = ?", (post_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def save_lead(self, lead_data: dict) -> Optional[int]:
        """
        Save a new lead to the database.
        Returns the lead ID if saved, None if duplicate.
        """
        if self.is_duplicate(lead_data.get("post_id", "")):
            logger.debug(f"Duplicate post skipped: {lead_data.get('post_id')}")
            return None

        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO leads (
                    post_id, platform, community, author, title, body, url,
                    score, category, keyword_matched, keyword_category,
                    reasoning, suggested_reply, post_created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead_data.get("post_id"),
                lead_data.get("platform"),
                lead_data.get("community"),
                lead_data.get("author"),
                lead_data.get("title", ""),
                lead_data.get("body", ""),
                lead_data.get("url", ""),
                lead_data.get("score", 0.0),
                lead_data.get("category", "COLD"),
                lead_data.get("keyword_matched", ""),
                lead_data.get("keyword_category", ""),
                lead_data.get("reasoning", ""),
                lead_data.get("suggested_reply", ""),
                lead_data.get("post_created_at"),
            ))
            conn.commit()
            lead_id = cursor.lastrowid
            logger.info(
                f"Lead saved: [{lead_data.get('category')}] "
                f"{lead_data.get('platform')}/{lead_data.get('community')} "
                f"- score {lead_data.get('score', 0):.2f}"
            )
            return lead_id
        except sqlite3.IntegrityError:
            logger.debug(f"Duplicate post (race condition): {lead_data.get('post_id')}")
            return None
        finally:
            conn.close()

    def mark_replied(self, lead_id: int):
        """Mark a lead as replied to (user clicks in dashboard)."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE leads SET replied = 1, replied_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), lead_id)
            )
            conn.commit()
        finally:
            conn.close()

    def mark_response_received(self, lead_id: int):
        """Mark that the lead responded back."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE leads SET response_received = 1, response_received_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), lead_id)
            )
            conn.commit()
        finally:
            conn.close()

    def mark_converted(self, lead_id: int):
        """Mark a lead as converted to a paying client."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE leads SET converted = 1, converted_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), lead_id)
            )
            conn.commit()
        finally:
            conn.close()

    def add_note(self, lead_id: int, note: str):
        """Add a note to a lead."""
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE leads SET notes = ? WHERE id = ?",
                (note, lead_id)
            )
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    # SCAN LOG OPERATIONS
    # =========================================================================

    def log_scan(self, platform: str, community: str, posts_scanned: int,
                 leads_found: int, hot: int, warm: int, cold: int,
                 errors: str = "", duration: float = 0.0):
        """Record a scan run for system health monitoring."""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO scan_logs (
                    platform, community, posts_scanned, leads_found,
                    hot_leads, warm_leads, cold_leads, errors, duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (platform, community, posts_scanned, leads_found,
                  hot, warm, cold, errors, duration))
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    # STATISTICS QUERIES (for dashboard)
    # =========================================================================

    def get_leads(self, category: str = None, platform: str = None,
                  days: int = 30, limit: int = 100) -> list:
        """Get leads with optional filtering."""
        conn = self._get_conn()
        try:
            query = "SELECT * FROM leads WHERE discovered_at >= ?"
            params = [(datetime.utcnow() - timedelta(days=days)).isoformat()]

            if category:
                query += " AND category = ?"
                params.append(category)
            if platform:
                query += " AND platform = ?"
                params.append(platform)

            query += " ORDER BY discovered_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_stats_summary(self, days: int = 7) -> dict:
        """Get summary statistics for the dashboard overview."""
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

            # Lead counts by category
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN category = 'HOT' THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN category = 'WARM' THEN 1 ELSE 0 END) as warm,
                    SUM(CASE WHEN category = 'COLD' THEN 1 ELSE 0 END) as cold,
                    SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END) as replied,
                    SUM(CASE WHEN response_received = 1 THEN 1 ELSE 0 END) as responses,
                    SUM(CASE WHEN converted = 1 THEN 1 ELSE 0 END) as conversions
                FROM leads
                WHERE discovered_at >= ?
            """, (cutoff,))
            row = dict(cursor.fetchone())

            # Today's counts
            today = datetime.utcnow().strftime("%Y-%m-%d")
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as today_total,
                    SUM(CASE WHEN category = 'HOT' THEN 1 ELSE 0 END) as today_hot,
                    SUM(CASE WHEN category = 'WARM' THEN 1 ELSE 0 END) as today_warm
                FROM leads
                WHERE date(discovered_at) = ?
            """, (today,))
            today_row = dict(cursor.fetchone())
            row.update(today_row)

            # Last scan time
            cursor = conn.execute(
                "SELECT scan_time FROM scan_logs ORDER BY scan_time DESC LIMIT 1"
            )
            last_scan = cursor.fetchone()
            row["last_scan"] = last_scan["scan_time"] if last_scan else "Never"

            return row
        finally:
            conn.close()

    def get_platform_stats(self, days: int = 30) -> list:
        """Get lead counts grouped by platform (for dashboard chart)."""
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            cursor = conn.execute("""
                SELECT
                    platform,
                    community,
                    COUNT(*) as total,
                    SUM(CASE WHEN category = 'HOT' THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN category = 'WARM' THEN 1 ELSE 0 END) as warm
                FROM leads
                WHERE discovered_at >= ?
                GROUP BY platform, community
                ORDER BY hot DESC, warm DESC
            """, (cutoff,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_keyword_stats(self, days: int = 30) -> list:
        """Get keyword match counts (for dashboard chart)."""
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            cursor = conn.execute("""
                SELECT
                    keyword_matched,
                    keyword_category,
                    COUNT(*) as hits,
                    SUM(CASE WHEN category = 'HOT' THEN 1 ELSE 0 END) as hot_hits
                FROM leads
                WHERE discovered_at >= ? AND keyword_matched != ''
                GROUP BY keyword_matched
                ORDER BY hits DESC
                LIMIT 20
            """, (cutoff,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_daily_trend(self, days: int = 30) -> list:
        """Get daily lead counts for trend chart."""
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            cursor = conn.execute("""
                SELECT
                    date(discovered_at) as date,
                    COUNT(*) as total,
                    SUM(CASE WHEN category = 'HOT' THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN category = 'WARM' THEN 1 ELSE 0 END) as warm,
                    SUM(CASE WHEN category = 'COLD' THEN 1 ELSE 0 END) as cold
                FROM leads
                WHERE discovered_at >= ?
                GROUP BY date(discovered_at)
                ORDER BY date ASC
            """, (cutoff,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_conversion_funnel(self, days: int = 30) -> dict:
        """Get conversion funnel data."""
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total_leads,
                    SUM(CASE WHEN category IN ('HOT', 'WARM') THEN 1 ELSE 0 END) as qualified,
                    SUM(CASE WHEN replied = 1 THEN 1 ELSE 0 END) as replied,
                    SUM(CASE WHEN response_received = 1 THEN 1 ELSE 0 END) as responded,
                    SUM(CASE WHEN converted = 1 THEN 1 ELSE 0 END) as converted
                FROM leads
                WHERE discovered_at >= ?
            """, (cutoff,))
            return dict(cursor.fetchone())
        finally:
            conn.close()

    def get_scan_health(self, hours: int = 24) -> list:
        """Get recent scan logs for system health monitoring."""
        conn = self._get_conn()
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            cursor = conn.execute("""
                SELECT * FROM scan_logs
                WHERE scan_time >= ?
                ORDER BY scan_time DESC
            """, (cutoff,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
