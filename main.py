"""
main.py - BetMaster Agent Entry Point

Orchestrates:
1. Browser Agent (window detection + CDP connection)
2. Live Scraper (multi-source game fetching)
3. Ollama Analyzer (gemma3:1b AI analysis)
4. Confidence Engine (Poisson + value detection)
5. Strategic Bettor (Conservative/Aggressive modes)
6. Dashboard UI

Run with: python main.py
"""

import asyncio
import logging
import threading
import time
import sys
import os

os.makedirs("logs", exist_ok=True)

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/betmaster.log", encoding="utf-8"),
    ]
)

# Fix for Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logger = logging.getLogger("main")

import config
from browser.window_manager import get_window_manager
from browser.agent import get_browser_agent
from browser.live_scraper import get_live_scraper
from scraper.scraper_manager import ScraperManager
from analyzer.stats_fetcher import StatsFetcher
from analyzer.poisson_model import PoissonModel
from analyzer.ollama_analyzer import get_ollama_analyzer
from predictor.confidence_engine import ConfidenceEngine
from bettor.bet_history import BetHistory
from bettor.auto_bettor import AutoBettor
from bettor.strategic_bettor import get_strategic_bettor, StrategyMode
from ui.web_server import SoccerBotWebServer


class BetMasterAgent:
    """
    Main application controller.
    Runs analysis loop in background, Web UI on port 8080.
    """

    def __init__(self):
        # Initialize components
        self.dashboard = SoccerBotWebServer(port=8080)
        self.history = BetHistory()
        self.engine = ConfidenceEngine()
        self.stats_fetcher = StatsFetcher()
        
        # Browser components
        self.window_manager = get_window_manager()
        self.browser_agent = get_browser_agent(self.window_manager)
        self.live_scraper = get_live_scraper(
            self.browser_agent, 
            config.THE_ODDS_API_KEY
        )
        
        # Strategic bettor
        strategy = StrategyMode.CONSERVATIVE
        if config.STRATEGY_MODE == "aggressive":
            strategy = StrategyMode.AGGRESSIVE
        self.strategic_bettor = get_strategic_bettor(strategy)
        
        # Legacy scraper manager (for SportPesa, etc.)
        self.scraper_manager = ScraperManager()
        
        # Auto-bettor
        self.auto_bettor = None
        
        # State
        self._running = False
        self._loop = None
        self._analysis_thread = None
        self._force_refresh = False
        
        # UI callbacks
        self.dashboard.on_manual_bet = self._handle_manual_bet
        self.dashboard.on_auto_bet_toggle = self._handle_auto_bet_toggle
        self.dashboard.on_force_refresh = self._trigger_refresh
        self.dashboard.on_recheck_login = self._handle_recheck_login
        self.dashboard.on_strategy_change = self._handle_strategy_change

    def start(self):
        """Start analysis loop in background, then launch server."""
        logger.info("🚀 Starting BetMaster Agent...")
        self._running = True

        # Start background analysis loop
        self._analysis_thread = threading.Thread(
            target=self._run_async_loop, daemon=True
        )
        self._analysis_thread.start()

        print("🌐 DASHBOARD: http://localhost:8080")
        print(f"📊 Strategy: {config.STRATEGY_MODE}")
        print(f"🤖 Ollama: {config.OLLAMA_MODEL}")
        
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._running = False
            
        logger.info("👋 BetMaster shutting down...")

    def _run_async_loop(self):
        """Run the async scraping + analysis loop in background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as e:
            logger.error(f"Async loop error: {e}")
        finally:
            self._loop.close()

    async def _async_main(self):
        """Main async loop: scrape → analyze → bet → repeat."""
        
        # Initialize browser agent
        self.dashboard.update_status("● Connecting to browser...")
        
        try:
            # Connect to existing browser or launch new
            browser_connected = await self.browser_agent.connect(
                use_existing=config.BROWSER_CONNECT_TO_EXISTING,
                headless=config.BROWSER_HEADLESS
            )
            
            if browser_connected:
                logger.info(f"Browser connected via: {self.browser_agent.connection_method}")
                self.dashboard.update_status("● Browser connected")
                
                # Navigate to 1xbet if not already there
                if self.browser_agent.page:
                    current_url = self.browser_agent.current_url
                    if not current_url or "1xbet" not in current_url.lower():
                        await self.browser_agent.navigate_to_1xbet()
            else:
                logger.warning("Could not connect to browser, using API fallback")
                self.dashboard.update_status("⚠️ Browser not connected, using API fallback")
                
        except Exception as e:
            logger.error(f"Browser connection failed: {e}")
            self.dashboard.update_status(f"⚠️ Browser error: {str(e)[:50]}")

        # Initialize web server
        await self.dashboard.start()
        
        # Initialize auto-bettor
        self.auto_bettor = AutoBettor(self.scraper_manager, self.history)
        self.auto_bettor.on_bet_placed = self._on_bet_placed
        self.auto_bettor.on_bet_blocked = self._on_bet_blocked

        # Fetch initial stats in background
        asyncio.create_task(self._fetch_stats_background())

        self.dashboard.update_status("● Running...")
        logger.info("✅ BetMaster Agent ready!")

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
        await self.browser_agent.disconnect()
        await self.live_scraper.close()
        await self.scraper_manager.stop()

    async def _run_analysis_cycle(self):
        """One full cycle: scrape → analyze → update UI."""
        
        logger.debug("🔄 Analysis cycle starting...")
        
        # Step 1: Get live games (browser agent + API fallback)
        self.dashboard.update_status("● Fetching live games...")
        
        # Try browser agent first
        games = []
        try:
            if self.browser_agent.is_connected:
                games = await self.live_scraper.get_live_games(force_refresh=True)
        except Exception as e:
            logger.warning(f"Browser scraper error: {e}")
        
        # If no games, try legacy scraper
        if not games:
            try:
                games = await self.scraper_manager.get_all_live_games()
            except Exception as e:
                logger.warning(f"Legacy scraper error: {e}")
        
        if not games:
            self.dashboard.update_status("⚠️ No live games found")
            self.dashboard.update_games([])
            return

        self.dashboard.update_status(f"● Analyzing {len(games)} games...")
        self.dashboard.update_games(games)

        # Step 2: Update Poisson model with team ratings
        all_ratings = self.stats_fetcher._cache
        if all_ratings:
            self.engine.poisson.update_team_ratings(all_ratings)

        # Step 3: Run analysis
        logger.info(f"Running batch analysis on {len(games)} games...")
        recommendations = await self.engine.batch_analyze(games)
        total_recs = sum(len(r) for r in recommendations.values())
        logger.info(f"Analysis complete: {total_recs} recommendations")

        # Step 4: Update UI
        self.dashboard.update_recommendations(recommendations)
        
        # Update history
        bets = self.history.get_recent_bets(50)
        self.dashboard.update_history(bets)
        
        # Update stats
        stats = self.history.get_stats(30)
        self.dashboard.update_stats(stats)
        
        # Update scraper statuses
        self.dashboard.update_scraper_statuses(self.scraper_manager.get_scraper_statuses())
        
        # Update strategy stats
        strategy_stats = self.strategic_bettor.get_session_stats()
        self.dashboard.update_strategy_stats(strategy_stats)

        # Step 5: Auto-betting
        if self.auto_bettor and self.auto_bettor.enabled:
            self.dashboard.update_status("🤖 Auto-betting...")
            placed = await self.auto_bettor.process_recommendations(recommendations)
            if placed:
                logger.info(f"🤖 Auto-placed {placed} bets")

        # Status update
        status = (
            f"● Live: {len(games)} games | {total_recs} opportunities | "
            f"{'🤖 AUTO-ON' if self.auto_bettor and self.auto_bettor.enabled else '👤 Auto-OFF'} | "
            f"{config.STRATEGY_MODE.title()}"
        )
        self.dashboard.update_status(status)

    async def _fetch_stats_background(self):
        """Fetch team stats from API in background."""
        logger.info("📊 Fetching team statistics...")
        try:
            await self.stats_fetcher.fetch_all_leagues()
            logger.info(f"📊 Stats loaded: {len(self.stats_fetcher._cache)} teams")
        except Exception as e:
            logger.warning(f"Stats fetch failed: {e}")

    def _trigger_refresh(self):
        """Force immediate refresh."""
        self._force_refresh = True
        logger.info("Manual refresh triggered")

    async def _handle_recheck_login(self):
        """Manually trigger login check."""
        logger.info("Manual login re-check triggered")
        await self.scraper_manager.trigger_recheck_login()

    def _handle_manual_bet(self, rec):
        """Record a manually placed bet."""
        if isinstance(rec, dict):
            bet_id = self.history.record_bet(
                site=rec.get("site", "unknown"),
                game_id=rec.get("game_id", ""),
                home_team=rec.get("home_team", "Unknown"),
                away_team=rec.get("away_team", "Unknown"),
                home_score=rec.get("home_score", 0),
                away_score=rec.get("away_score", 0),
                minute=rec.get("minute", 0),
                bet_type=rec.get("bet_type", ""),
                bet_label=rec.get("bet_label", "Bet"),
                odds=rec.get("odds", 1.0),
                stake=rec.get("recommended_stake", 0),
                confidence=rec.get("confidence", 0),
                model_probability=rec.get("model_probability", 0),
                edge=rec.get("edge", 0),
                auto_placed=False,
            )
        else:
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
        
        bets = self.history.get_recent_bets(50)
        self.dashboard.update_history(bets)

    def _handle_auto_bet_toggle(self, enabled: bool):
        """Enable or disable auto-betting."""
        if self.auto_bettor:
            if enabled:
                self.auto_bettor.enable()
            else:
                self.auto_bettor.disable()

    def _handle_strategy_change(self, mode: str):
        """Change betting strategy."""
        try:
            strategy = StrategyMode.CONSERVATIVE
            if mode.lower() == "aggressive":
                strategy = StrategyMode.AGGRESSIVE
            
            self.strategic_bettor.set_strategy(strategy)
            logger.info(f"Strategy changed to: {mode}")
            
            # Update config
            config.STRATEGY_MODE = mode
            
        except Exception as e:
            logger.error(f"Strategy change failed: {e}")

    def _on_bet_placed(self, rec, bet_id: int, success: bool):
        """Called when auto-bettor places a bet."""
        bets = self.history.get_recent_bets(50)
        self.dashboard.update_history(bets)

    def _on_bet_blocked(self, rec, reason: str):
        logger.debug(f"Bet blocked: {reason}")


if __name__ == "__main__":
    print("""
    ==================================================
          BetMaster Agent - AI-Powered Football Betting
    ==================================================
    
    Starting up...
    - Browser: CDP connection to existing or new browser
    - Ollama: {model}
    - Strategy: {strategy}
    
    Configuration: config.py
    Logs: logs/betmaster.log
    Bet history: data/bets.db
    
    Dashboard: http://localhost:8080
    """.format(model=config.OLLAMA_MODEL, strategy=config.STRATEGY_MODE))
    
    agent = BetMasterAgent()
    agent.start()
