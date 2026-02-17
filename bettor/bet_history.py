"""
bettor/bet_history.py
Tracks all bets in SQLite for performance analysis.
Calculates ROI, win rate, P&L, and alerts on daily loss limit.
"""

import sqlite3
import logging
from datetime import datetime, date
from typing import List, Dict, Optional
import config

logger = logging.getLogger(__name__)


class BetHistory:
    """
    SQLite-backed bet history tracker.
    Tracks every bet recommendation and auto-placed bet.
    """

    def __init__(self, db_path: str = config.DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        import os
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    site TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    home_score_at_bet INTEGER,
                    away_score_at_bet INTEGER,
                    minute_at_bet INTEGER,
                    bet_type TEXT NOT NULL,
                    bet_label TEXT NOT NULL,
                    odds REAL NOT NULL,
                    stake REAL NOT NULL,
                    confidence REAL NOT NULL,
                    model_probability REAL NOT NULL,
                    edge REAL NOT NULL,
                    auto_placed INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',  -- pending, won, lost, void
                    pnl REAL DEFAULT NULL,
                    final_score TEXT DEFAULT NULL,
                    notes TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_summary (
                    date TEXT PRIMARY KEY,
                    total_bets INTEGER DEFAULT 0,
                    auto_bets INTEGER DEFAULT 0,
                    total_staked REAL DEFAULT 0,
                    total_won REAL DEFAULT 0,
                    pnl REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0
                )
            """)

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def record_bet(
        self,
        site: str,
        game_id: str,
        home_team: str,
        away_team: str,
        home_score: int,
        away_score: int,
        minute: int,
        bet_type: str,
        bet_label: str,
        odds: float,
        stake: float,
        confidence: float,
        model_probability: float,
        edge: float,
        auto_placed: bool = False,
    ) -> int:
        """Record a new bet. Returns bet ID."""
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT INTO bets (
                    timestamp, site, game_id, home_team, away_team,
                    home_score_at_bet, away_score_at_bet, minute_at_bet,
                    bet_type, bet_label, odds, stake, confidence,
                    model_probability, edge, auto_placed
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.now().isoformat(),
                site, game_id, home_team, away_team,
                home_score, away_score, minute,
                bet_type, bet_label, odds, stake, confidence,
                model_probability, edge, int(auto_placed)
            ))
            return cursor.lastrowid

    def update_result(self, bet_id: int, status: str, final_score: str = "", pnl: float = None):
        """Update bet result after game ends."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE bets SET status=?, final_score=?, pnl=? WHERE id=?
            """, (status, final_score, pnl, bet_id))

    def get_today_loss(self) -> float:
        """Total losses today (for daily limit check)."""
        today = date.today().isoformat()
        with self._conn() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 0)
                FROM bets
                WHERE DATE(timestamp) = ? AND status IN ('lost')
            """, (today,)).fetchone()
            return row[0] if row else 0.0

    def get_today_staked(self) -> float:
        """Total staked today."""
        today = date.today().isoformat()
        with self._conn() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(stake), 0)
                FROM bets WHERE DATE(timestamp) = ?
            """, (today,)).fetchone()
            return row[0] if row else 0.0

    def is_daily_limit_hit(self) -> bool:
        """Check if daily loss limit has been exceeded."""
        return self.get_today_loss() >= config.DAILY_LOSS_LIMIT

    def get_stats(self, days: int = 30) -> Dict:
        """Get performance stats for last N days."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN auto_placed=1 THEN 1 ELSE 0 END) as auto_bets,
                    COALESCE(SUM(stake), 0) as total_staked,
                    COALESCE(SUM(CASE WHEN status='won' THEN stake*(odds-1) ELSE 0 END), 0) as gross_won,
                    COALESCE(SUM(CASE WHEN status='lost' THEN stake ELSE 0 END), 0) as gross_lost,
                    COUNT(CASE WHEN status='won' THEN 1 END) as wins,
                    COUNT(CASE WHEN status='lost' THEN 1 END) as losses,
                    AVG(confidence) as avg_confidence,
                    AVG(edge) as avg_edge
                FROM bets
                WHERE DATE(timestamp) >= DATE('now', ?)
            """, (f"-{days} days",)).fetchone()

        if not rows or not rows[0]:
            return {}

        total, auto, staked, won, lost, wins, losses, avg_conf, avg_edge = rows
        settled = wins + losses
        pnl = won - lost

        return {
            "total_bets": total,
            "auto_bets": auto,
            "total_staked": round(staked, 2),
            "gross_won": round(won, 2),
            "gross_lost": round(lost, 2),
            "pnl": round(pnl, 2),
            "win_rate": round(wins / settled * 100, 1) if settled > 0 else 0,
            "roi": round(pnl / staked * 100, 1) if staked > 0 else 0,
            "avg_confidence": round(avg_conf or 0, 1),
            "avg_edge": round(avg_edge or 0, 4),
            "settled_bets": settled,
        }

    def get_recent_bets(self, limit: int = 50) -> List[Dict]:
        """Get most recent bets for display."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT id, timestamp, site, home_team, away_team,
                       bet_label, odds, stake, confidence, status, pnl, auto_placed,
                       minute_at_bet, final_score
                FROM bets ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()

        return [
            {
                "id": r[0], "timestamp": r[1], "site": r[2],
                "match": f"{r[3]} vs {r[4]}", "bet": r[5],
                "odds": r[6], "stake": r[7], "confidence": r[8],
                "status": r[9], "pnl": r[10],
                "auto": "🤖" if r[11] else "👤",
                "minute": r[12], "final_score": r[13] or "-",
            }
            for r in rows
        ]
