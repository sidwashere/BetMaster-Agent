"""
ui/dashboard.py
Main desktop dashboard UI using CustomTkinter.
Dark themed, inspired by trading terminal aesthetics.

Layout:
  [Header: status, auto-bet toggle, stats]
  [Left: Live Games List]        [Right: Bet Recommendations]
  [Bottom: Bet History Table]
"""

import customtkinter as ctk
from tkinter import ttk, messagebox
import tkinter as tk
import asyncio
import threading
import logging
from datetime import datetime
from typing import List, Dict, Optional
import config

logger = logging.getLogger(__name__)

# Color scheme - dark terminal aesthetic
COLORS = {
    "bg": "#0d1117",
    "surface": "#161b22",
    "border": "#30363d",
    "text": "#e6edf3",
    "text_muted": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "yellow": "#d29922",
    "blue": "#58a6ff",
    "purple": "#bc8cff",
    "orange": "#e3b341",
    "conf_very_high": "#3fb950",  # Green
    "conf_high": "#58a6ff",       # Blue
    "conf_medium": "#d29922",     # Yellow
    "conf_low": "#f85149",        # Red
}


class SoccerBotDashboard:

    def __init__(self):
        ctk.set_appearance_mode(config.UI_THEME)
        ctk.set_default_color_theme(config.UI_COLOR)

        self.root = ctk.CTk()
        self.root.title("⚽ SoccerBot — Live Betting Intelligence")
        self.root.geometry("1400x900")
        self.root.configure(fg_color=COLORS["bg"])

        # State
        self._games = []
        self._recommendations = {}
        self._auto_bet_var = tk.BooleanVar(value=False)
        self._status_var = tk.StringVar(value="● Initializing...")
        self._balance_var = tk.StringVar(value="Balance: —")
        self._pnl_var = tk.StringVar(value="P&L: —")
        self._last_refresh = tk.StringVar(value="Last refresh: —")

        # Callbacks (set by main.py)
        self.on_manual_bet = None      # fn(rec)
        self.on_auto_bet_toggle = None # fn(enabled: bool)
        self.on_force_refresh = None   # fn()

        self._build_ui()

    def _build_ui(self):
        """Build the complete UI layout."""
        self._build_header()
        self._build_main_area()
        self._build_history_panel()
        self._build_status_bar()

    def _build_header(self):
        """Top header bar with stats and controls."""
        header = ctk.CTkFrame(self.root, fg_color=COLORS["surface"], height=70, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        # Logo
        logo = ctk.CTkLabel(
            header, text="⚽ SOCCERBOT",
            font=ctk.CTkFont(family="Courier New", size=20, weight="bold"),
            text_color=COLORS["green"]
        )
        logo.pack(side="left", padx=20)

        # Status indicator
        status_label = ctk.CTkLabel(
            header, textvariable=self._status_var,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"]
        )
        status_label.pack(side="left", padx=15)

        # Right side controls
        right_frame = ctk.CTkFrame(header, fg_color="transparent")
        right_frame.pack(side="right", padx=20)

        # P&L
        pnl_label = ctk.CTkLabel(
            right_frame, textvariable=self._pnl_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["green"]
        )
        pnl_label.pack(side="right", padx=15)

        # Balance
        balance_label = ctk.CTkLabel(
            right_frame, textvariable=self._balance_var,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"]
        )
        balance_label.pack(side="right", padx=10)

        # Auto-bet toggle
        auto_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        auto_frame.pack(side="right", padx=15)

        ctk.CTkLabel(
            auto_frame, text="AUTO-BET",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        self._auto_switch = ctk.CTkSwitch(
            auto_frame,
            text="",
            variable=self._auto_bet_var,
            command=self._toggle_auto_bet,
            button_color=COLORS["green"],
            progress_color=COLORS["green"],
            width=50,
        )
        self._auto_switch.pack(side="left", padx=5)

        # Refresh button
        ctk.CTkButton(
            right_frame, text="⟳ Refresh",
            command=self._force_refresh,
            width=90, height=32,
            fg_color=COLORS["surface"],
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text"],
            hover_color=COLORS["border"],
            font=ctk.CTkFont(size=12),
        ).pack(side="right", padx=5)

        # Last refresh
        ctk.CTkLabel(
            right_frame, textvariable=self._last_refresh,
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        ).pack(side="right", padx=10)

    def _build_main_area(self):
        """Main two-panel area: games left, recommendations right."""
        main = ctk.CTkFrame(self.root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # Left: Live games list
        left = ctk.CTkFrame(main, fg_color=COLORS["surface"], width=380, corner_radius=8)
        left.pack(side="left", fill="both", padx=(0, 5))
        left.pack_propagate(False)

        ctk.CTkLabel(
            left, text="📺 LIVE GAMES",
            font=ctk.CTkFont(family="Courier New", size=13, weight="bold"),
            text_color=COLORS["blue"]
        ).pack(padx=15, pady=(12, 5), anchor="w")

        # Games scrollable frame
        self._games_scroll = ctk.CTkScrollableFrame(
            left, fg_color="transparent", scrollbar_button_color=COLORS["border"]
        )
        self._games_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        # Right: Recommendations
        right = ctk.CTkFrame(main, fg_color=COLORS["surface"], corner_radius=8)
        right.pack(side="right", fill="both", expand=True)

        ctk.CTkLabel(
            right, text="🎯 BET RECOMMENDATIONS",
            font=ctk.CTkFont(family="Courier New", size=13, weight="bold"),
            text_color=COLORS["green"]
        ).pack(padx=15, pady=(12, 5), anchor="w")

        self._recs_scroll = ctk.CTkScrollableFrame(
            right, fg_color="transparent", scrollbar_button_color=COLORS["border"]
        )
        self._recs_scroll.pack(fill="both", expand=True, padx=5, pady=5)

    def _build_history_panel(self):
        """Bottom panel: bet history table."""
        history_frame = ctk.CTkFrame(self.root, fg_color=COLORS["surface"], height=220, corner_radius=8)
        history_frame.pack(fill="x", padx=10, pady=(0, 5))
        history_frame.pack_propagate(False)

        header_row = ctk.CTkFrame(history_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            header_row, text="📋 BET HISTORY",
            font=ctk.CTkFont(family="Courier New", size=13, weight="bold"),
            text_color=COLORS["purple"]
        ).pack(side="left")

        # History treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("History.Treeview",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            fieldbackground=COLORS["surface"],
            rowheight=24,
            font=("Courier New", 10),
        )
        style.configure("History.Treeview.Heading",
            background=COLORS["border"],
            foreground=COLORS["text"],
            font=("Courier New", 10, "bold"),
        )

        cols = ("time", "auto", "match", "bet", "odds", "stake", "conf", "status", "pnl")
        self._history_tree = ttk.Treeview(
            history_frame, columns=cols, show="headings",
            style="History.Treeview", height=6
        )

        widths = {"time": 120, "auto": 40, "match": 200, "bet": 140,
                  "odds": 60, "stake": 70, "conf": 70, "status": 70, "pnl": 80}
        labels = {"time": "Time", "auto": "By", "match": "Match", "bet": "Bet",
                  "odds": "Odds", "stake": "Stake", "conf": "Conf%", "status": "Result", "pnl": "P&L"}

        for col in cols:
            self._history_tree.heading(col, text=labels[col])
            self._history_tree.column(col, width=widths[col], anchor="center")

        scrollbar = ttk.Scrollbar(history_frame, orient="horizontal", command=self._history_tree.xview)
        self._history_tree.configure(xscrollcommand=scrollbar.set)
        self._history_tree.pack(fill="both", expand=True, padx=10, pady=(0, 2))
        scrollbar.pack(fill="x", padx=10)

    def _build_status_bar(self):
        """Bottom status bar."""
        status_bar = ctk.CTkFrame(self.root, fg_color=COLORS["border"], height=24, corner_radius=0)
        status_bar.pack(fill="x", side="bottom")
        status_bar.pack_propagate(False)

        ctk.CTkLabel(
            status_bar,
            text="⚠️  For educational purposes only. Bet responsibly.  |  "
                 "Auto-bet requires valid login credentials in config.py",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            status_bar,
            text=f"v1.0 | Refresh: {config.REFRESH_INTERVAL}s | "
                 f"Min Confidence: {config.MIN_DISPLAY_CONFIDENCE}%",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        ).pack(side="right", padx=10)

    # ─────────────────────────────────────────────
    # Public update methods (called from main loop)
    # ─────────────────────────────────────────────

    def update_games(self, games: list):
        """Refresh the games panel."""
        self._games = games
        self.root.after(0, self._render_games)

    def update_recommendations(self, recs: dict):
        """Refresh the recommendations panel."""
        self._recommendations = recs
        self.root.after(0, self._render_recommendations)

    def update_history(self, bets: list):
        """Refresh the history table."""
        self.root.after(0, lambda: self._render_history(bets))

    def update_status(self, msg: str, color: str = None):
        """Update status indicator."""
        self._status_var.set(msg)

    def update_stats(self, stats: dict):
        """Update header stats."""
        if stats:
            pnl = stats.get("pnl", 0)
            color = COLORS["green"] if pnl >= 0 else COLORS["red"]
            self._pnl_var.set(f"30d P&L: {'+' if pnl >= 0 else ''}{pnl:.0f} KES")
            self._last_refresh.set(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

    def update_balance(self, balance: float):
        self._balance_var.set(f"Balance: {balance:.0f} KES")

    # ─────────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────────

    def _render_games(self):
        """Render live games list."""
        for w in self._games_scroll.winfo_children():
            w.destroy()

        if not self._games:
            ctk.CTkLabel(
                self._games_scroll,
                text="No live games found.\nCheck scraper configuration.",
                text_color=COLORS["text_muted"],
                font=ctk.CTkFont(size=12)
            ).pack(pady=30)
            return

        for game in self._games:
            self._render_game_card(game)

    def _render_game_card(self, game):
        """Render a single game card."""
        has_recs = game.game_id in self._recommendations

        card = ctk.CTkFrame(
            self._games_scroll,
            fg_color=COLORS["bg"] if not has_recs else "#0d2818",
            corner_radius=6,
            border_color=COLORS["green"] if has_recs else COLORS["border"],
            border_width=1 if has_recs else 0,
        )
        card.pack(fill="x", padx=5, pady=3)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(8, 2))

        # Teams
        teams_label = ctk.CTkLabel(
            top_row,
            text=f"{game.home_team}  vs  {game.away_team}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text"]
        )
        teams_label.pack(side="left")

        # Score
        score_color = COLORS["yellow"] if game.home_score != game.away_score else COLORS["text_muted"]
        ctk.CTkLabel(
            top_row,
            text=f"  {game.home_score} - {game.away_score}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=score_color
        ).pack(side="left")

        # Minute badge
        ctk.CTkLabel(
            top_row,
            text=f" {game.minute}'",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["red"]
        ).pack(side="left")

        bottom_row = ctk.CTkFrame(card, fg_color="transparent")
        bottom_row.pack(fill="x", padx=10, pady=(0, 8))

        # Site badge
        site_colors = {"1xbet": COLORS["blue"], "sportpesa": COLORS["orange"]}
        ctk.CTkLabel(
            bottom_row,
            text=game.site.upper(),
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=site_colors.get(game.site, COLORS["text_muted"])
        ).pack(side="left")

        # League
        ctk.CTkLabel(
            bottom_row,
            text=f"  {game.league[:35]}",
            font=ctk.CTkFont(size=9),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        # Recommendation badge
        if has_recs:
            top_rec = self._recommendations[game.game_id][0]
            ctk.CTkLabel(
                bottom_row,
                text=f"🎯 {top_rec.confidence:.0f}%",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=COLORS["green"]
            ).pack(side="right")

    def _render_recommendations(self):
        """Render bet recommendations panel."""
        for w in self._recs_scroll.winfo_children():
            w.destroy()

        all_recs = []
        for recs in self._recommendations.values():
            all_recs.extend(recs)

        # Sort all recommendations globally by confidence
        all_recs.sort(key=lambda r: r.confidence, reverse=True)

        if not all_recs:
            ctk.CTkLabel(
                self._recs_scroll,
                text="No betting opportunities found.\n\nWaiting for analysis...",
                text_color=COLORS["text_muted"],
                font=ctk.CTkFont(size=13)
            ).pack(pady=40)
            return

        for rec in all_recs[:20]:  # Show top 20
            self._render_rec_card(rec)

    def _render_rec_card(self, rec):
        """Render a single recommendation card."""
        conf_colors = {
            "🔥 Very High": COLORS["conf_very_high"],
            "✅ High": COLORS["conf_high"],
            "⚡ Medium": COLORS["conf_medium"],
            "⚠️ Low": COLORS["conf_low"],
        }
        conf_color = conf_colors.get(rec.confidence_label, COLORS["text_muted"])

        card = ctk.CTkFrame(
            self._recs_scroll,
            fg_color=COLORS["bg"],
            corner_radius=8,
            border_color=conf_color,
            border_width=1,
        )
        card.pack(fill="x", padx=5, pady=4)

        # Header row
        h = ctk.CTkFrame(card, fg_color="transparent")
        h.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(
            h,
            text=f"{rec.game.home_team} vs {rec.game.away_team}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["text"]
        ).pack(side="left")

        ctk.CTkLabel(
            h,
            text=f"{rec.game.home_score}-{rec.game.away_score}  {rec.game.minute}'",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["yellow"]
        ).pack(side="left", padx=10)

        # Confidence badge
        ctk.CTkLabel(
            h,
            text=f"{rec.confidence_label}  {rec.confidence:.0f}%",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=conf_color
        ).pack(side="right")

        # Bet details row
        d = ctk.CTkFrame(card, fg_color="transparent")
        d.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(
            d,
            text=f"BET: {rec.bet_label}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=conf_color
        ).pack(side="left")

        ctk.CTkLabel(
            d,
            text=f"@ {rec.odds:.2f}",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"]
        ).pack(side="left", padx=10)

        edge_color = COLORS["green"] if rec.edge > 0 else COLORS["red"]
        ctk.CTkLabel(
            d,
            text=f"Edge: {'+' if rec.edge > 0 else ''}{rec.edge*100:.1f}%",
            font=ctk.CTkFont(size=11),
            text_color=edge_color
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            d,
            text=f"Stake: {rec.recommended_stake:.0f} KES",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=COLORS["blue"]
        ).pack(side="right")

        # Analysis row
        a = ctk.CTkFrame(card, fg_color="transparent")
        a.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(
            a,
            text=f"Model: {rec.model_probability*100:.1f}%  |  Bookmaker: {rec.implied_probability*100:.1f}%  "
                 f"|  xG: {rec.home_xg:.1f}-{rec.away_xg:.1f}  |  Predicted: {rec.predicted_score}",
            font=ctk.CTkFont(size=10),
            text_color=COLORS["text_muted"]
        ).pack(side="left")

        # Reasons (first 2)
        if rec.reasons:
            r_frame = ctk.CTkFrame(card, fg_color="transparent")
            r_frame.pack(fill="x", padx=12, pady=(2, 4))
            for reason in rec.reasons[:2]:
                ctk.CTkLabel(
                    r_frame,
                    text=f"• {reason}",
                    font=ctk.CTkFont(size=10),
                    text_color=COLORS["text_muted"],
                    wraplength=700,
                ).pack(anchor="w")

        # Warnings
        for w in rec.warnings[:1]:
            ctk.CTkLabel(
                card,
                text=w,
                font=ctk.CTkFont(size=10),
                text_color=COLORS["yellow"]
            ).pack(anchor="w", padx=12, pady=(0, 2))

        # Action buttons
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(4, 10))

        # Manual bet button
        ctk.CTkButton(
            btn_row,
            text=f"📋 Manual Bet ({rec.recommended_stake:.0f} KES)",
            command=lambda r=rec: self._manual_bet_click(r),
            width=180, height=28,
            fg_color=COLORS["surface"],
            border_color=conf_color,
            border_width=1,
            text_color=conf_color,
            hover_color=COLORS["border"],
            font=ctk.CTkFont(size=11),
        ).pack(side="left")

        if rec.is_auto_bettable:
            ctk.CTkLabel(
                btn_row,
                text="🤖 AUTO-BET ELIGIBLE",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=COLORS["green"]
            ).pack(side="left", padx=15)

        ctk.CTkLabel(
            btn_row,
            text=rec.game.site.upper(),
            font=ctk.CTkFont(size=9),
            text_color=COLORS["text_muted"]
        ).pack(side="right")

    def _render_history(self, bets: list):
        """Render bet history table."""
        for row in self._history_tree.get_children():
            self._history_tree.delete(row)

        for bet in bets[:50]:
            status = bet.get("status", "pending")
            pnl = bet.get("pnl")
            pnl_str = f"+{pnl:.0f}" if pnl and pnl > 0 else (f"{pnl:.0f}" if pnl else "-")

            self._history_tree.insert("", "end", values=(
                bet["timestamp"][:16].replace("T", " "),
                bet["auto"],
                bet["match"][:30],
                bet["bet"],
                f"{bet['odds']:.2f}",
                f"{bet['stake']:.0f}",
                f"{bet['confidence']:.0f}%",
                status.upper(),
                pnl_str,
            ))

    # ─────────────────────────────────────────────
    # Event handlers
    # ─────────────────────────────────────────────

    def _toggle_auto_bet(self):
        enabled = self._auto_bet_var.get()
        if enabled:
            confirmed = messagebox.askyesno(
                "Enable Auto-Bet",
                f"⚠️ CAUTION: Auto-bet will automatically place bets above "
                f"{config.AUTO_BET_THRESHOLD}% confidence.\n\n"
                f"Real money will be spent. Daily limit: {config.DAILY_LOSS_LIMIT} KES.\n\n"
                f"Are you sure you want to enable auto-betting?",
                icon="warning"
            )
            if not confirmed:
                self._auto_bet_var.set(False)
                return
        
        if self.on_auto_bet_toggle:
            self.on_auto_bet_toggle(enabled)

    def _manual_bet_click(self, rec):
        """Show manual bet confirmation dialog."""
        confirmed = messagebox.askyesno(
            "Manual Bet Confirmation",
            f"Place bet manually:\n\n"
            f"Match: {rec.game.home_team} vs {rec.game.away_team}\n"
            f"Bet: {rec.bet_label}\n"
            f"Odds: {rec.odds:.2f}\n"
            f"Confidence: {rec.confidence:.1f}%\n"
            f"Suggested Stake: {rec.recommended_stake:.0f} KES\n\n"
            f"Record this bet in history?",
        )
        if confirmed and self.on_manual_bet:
            self.on_manual_bet(rec)

    def _force_refresh(self):
        if self.on_force_refresh:
            self.on_force_refresh()

    def run(self):
        """Start the UI event loop."""
        self.root.mainloop()
