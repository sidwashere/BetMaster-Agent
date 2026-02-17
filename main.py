"""
main.py — SoccerBot Entry Point

Orchestrates:
 1. Stats fetcher (team ratings from API)
 2. Scraper manager (live odds from betting sites)
 3. Confidence engine (analysis + recommendations)
 4. Auto bettor (optional automated placement)
 5. Dashboard UI (displays everything)

Run with: python main.py
"""

import asyncio
import logging
import threading
import time
import sys
import os

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/soccerbot.log"),
    ]
)
logger = logging.getLogger("main")

import config
from scraper.scraper_manager import ScraperManager
from analyzer.stats_fetcher import StatsFetcher
from analyzer.poisson_model import PoissonModel
from predictor.confidence_engine import ConfidenceEngine
from bettor.bet_history import BetHistory
from bettor.auto_bettor import AutoBettor
from ui.web_server import SoccerBotWebServer


class SoccerBot:
    """
    Main application controller.
    Runs analysis loop in background thread, Web UI on port 8080.
    """

    def __init__(self):
        self.dashboard = SoccerBotWebServer(port=8080)
        self.history = BetHistory()
        self.engine = ConfidenceEngine()
        self.stats_fetcher = StatsFetcher()
        self.scraper_manager = ScraperManager()
        self.auto_bettor = None  # Initialized after scrapers ready

        self._running = False
        self._loop = None
        self._analysis_thread = None

        # Wire up UI callbacks
        self.dashboard.on_manual_bet = self._handle_manual_bet
        self.dashboard.on_auto_bet_toggle = self._handle_auto_bet_toggle
        self.dashboard.on_force_refresh = self._trigger_refresh
        self._force_refresh = False

    def start(self):
        """Start analysis loop in background, then launch server loop."""
        logger.info("🚀 Starting SoccerBot (Web UI)...")
        self._running = True

        # Start background analysis loop
        self._analysis_thread = threading.Thread(
            target=self._run_async_loop, daemon=True
        )
        self._analysis_thread.start()

        # Web Server runs in main thread or its own
        print("🌐 DASHBOARD: http://localhost:8080")
        
        # Keep main thread alive
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._running = False
            
        logger.info("👋 SoccerBot shutting down...")

    def _run_async_loop(self):
        """Run the async scraping + analysis loop in a background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            logger.error(f"Async loop error: {e}")
        finally:
            self._loop.close()

    async def _async_main(self):
        """Main async loop: fetch stats, scrape games, analyze, repeat."""
        # Initialize scrapers
        self.dashboard.update_status("● Launching browsers...")
        try:
            await self.scraper_manager.start()
        except Exception as e:
            logger.error(f"Failed to start scrapers: {e}")
            self.dashboard.update_status(f"❌ Scraper error: {e}")
            return

        # Initialize web server
        await self.dashboard.start()
        
        # Initialize auto-bettor
        self.auto_bettor = AutoBettor(self.scraper_manager, self.history)
        self.auto_bettor.on_bet_placed = self._on_bet_placed
        self.auto_bettor.on_bet_blocked = self._on_bet_blocked

        # Fetch initial stats (background, don't block)
        asyncio.create_task(self._fetch_stats_background())

        self.dashboard.update_status("● Running...")
        logger.info("✅ SoccerBot ready!")

        # Main loop
        while self._running:
            try:
                await self._run_analysis_cycle()
            except Exception as e:
                logger.error(f"Analysis cycle error: {e}")
                self.dashboard.update_status(f"⚠️ Error: {str(e)[:50]}")

            # Wait for next refresh
            self._force_refresh = False
            for _ in range(config.REFRESH_INTERVAL):
                if not self._running:
                    break
                if self._force_refresh:
                    break
                await asyncio.sleep(1)

        # Cleanup
        await self.scraper_manager.stop()

    async def _run_analysis_cycle(self):
        """One full cycle: scrape → analyze → update UI."""
        logger.info("🔄 Analysis cycle starting...")
        self.dashboard.update_status("● Scraping live games...")

        # Scrape all sites
        games = await self.scraper_manager.get_all_live_games()
        
        if not games:
            self.dashboard.update_status("⚠️ No live games found")
            self.dashboard.update_games([])
            return

        self.dashboard.update_status(f"● Analyzing {len(games)} games...")
        self.dashboard.update_games(games)

        # Update Poisson model with team ratings
        all_ratings = self.stats_fetcher._cache
        if all_ratings:
            self.engine.poisson.update_team_ratings(all_ratings)

        # Run analysis
        recommendations = await self.engine.batch_analyze(games)
        total_recs = sum(len(r) for r in recommendations.values())
        logger.info(f"Analysis complete: {total_recs} recommendations across {len(recommendations)} games")

        # Update UI
        self.dashboard.update_recommendations(recommendations)
        
        # Update history
        bets = self.history.get_recent_bets(50)
        self.dashboard.update_history(bets)
        
        # Update stats
        stats = self.history.get_stats(30)
        self.dashboard.update_stats(stats)

        # Auto-betting
        if self.auto_bettor and self.auto_bettor.enabled:
            self.dashboard.update_status("🤖 Auto-betting...")
            placed = await self.auto_bettor.process_recommendations(recommendations)
            if placed:
                logger.info(f"🤖 Auto-placed {placed} bets")

        self.dashboard.update_status(
            f"● Live: {len(games)} games | {total_recs} opportunities | "
            f"{'🤖 AUTO-ON' if self.auto_bettor and self.auto_bettor.enabled else '👤 Auto-OFF'}"
        )

    async def _fetch_stats_background(self):
        """Fetch team stats from API in background without blocking."""
        logger.info("📊 Fetching team statistics...")
        try:
            await self.stats_fetcher.fetch_all_leagues()
            logger.info(f"📊 Stats loaded: {len(self.stats_fetcher._cache)} teams")
        except Exception as e:
            logger.warning(f"Stats fetch failed (using defaults): {e}")

    def _trigger_refresh(self):
        """Force immediate refresh."""
        self._force_refresh = True
        logger.info("Manual refresh triggered")

    def _handle_manual_bet(self, rec):
        """Record a manually placed bet."""
        bet_id = self.history.record_bet(
            site=rec.game.site,
            game_id=rec.game.game_id,
            home_team=rec.game.home_team,
            away_team=rec.game.away_team,
            home_score=rec.game.home_score,
            away_score=rec.game.away_score,
            minute=rec.game.minute,
            bet_type=rec.bet_type,
            bet_label=rec.bet_label,
            odds=rec.odds,
            stake=rec.recommended_stake,
            confidence=rec.confidence,
            model_probability=rec.model_probability,
            edge=rec.edge,
            auto_placed=False,
        )
        logger.info(f"👤 Manual bet #{bet_id} recorded")
        # Refresh history
        bets = self.history.get_recent_bets(50)
        self.dashboard.update_history(bets)

    def _handle_auto_bet_toggle(self, enabled: bool):
        """Enable or disable auto-betting."""
        if self.auto_bettor:
            if enabled:
                self.auto_bettor.enable()
            else:
                self.auto_bettor.disable()

    def _on_bet_placed(self, rec, bet_id: int, success: bool):
        """Called when auto-bettor places a bet."""
        bets = self.history.get_recent_bets(50)
        self.dashboard.update_history(bets)

    def _on_bet_blocked(self, rec, reason: str):
        logger.debug(f"Bet blocked: {reason}")


if __name__ == "__main__":
    print("""
    ⚽ ================================================== ⚽
       SOCCERBOT — AI-Powered Live Football Betting Agent
    ⚽ ================================================== ⚽
    
    Starting up... Browser windows will open shortly.
    Press Ctrl+C or close the window to exit.
    
    Configuration: config.py
    Logs: logs/soccerbot.log
    Bet history: data/bets.db
    """)
    
    bot = SoccerBot()
    bot.start()
