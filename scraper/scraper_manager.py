"""
scraper/scraper_manager.py
Coordinates all scrapers, deduplicates games across sites.
"""

import asyncio
import logging
from typing import List, Dict
from playwright.async_api import async_playwright

from .base_scraper import LiveGame
from .site_1xbet import XBetScraper
from .site_sportpesa import SportPesaScraper
import config

logger = logging.getLogger(__name__)


class ScraperManager:
    """
    Manages all site scrapers.
    To add a new site: add scraper class here and in ENABLED_SCRAPERS dict.
    """

    SCRAPER_CLASSES = {
        "1xbet": XBetScraper,
        "sportpesa": SportPesaScraper,
        # "betway": BetwayScraper,    # Uncomment when you add scraper
        # "odibets": OdibetsScraper,  # Uncomment when you add scraper
    }

    def __init__(self):
        self.scrapers: Dict[str, any] = {}
        self.playwright = None
        self._active = False

    async def start(self):
        """Initialize Playwright and all enabled scrapers."""
        self.playwright = await async_playwright().start()
        
        for site_name in config.ENABLED_SITES:
            if site_name in self.SCRAPER_CLASSES:
                scraper_cls = self.SCRAPER_CLASSES[site_name]
                scraper = scraper_cls()
                await scraper.setup_browser(self.playwright, headless=config.BROWSER_HEADLESS)
                
                # Login if credentials configured
                if hasattr(scraper, 'login'):
                    creds = config.SITE_CREDENTIALS.get(site_name, {})
                    if creds.get("username"):
                        await scraper.login()
                
                self.scrapers[site_name] = scraper
                logger.info(f"✅ Initialized scraper: {site_name}")
            else:
                logger.warning(f"⚠️ No scraper class for site: {site_name}")

        self._active = True

    async def get_all_live_games(self) -> List[LiveGame]:
        """
        Fetch live games from all enabled sites concurrently.
        Returns deduplicated list (same game on multiple sites = single entry with best odds).
        """
        all_games = []

        # Scrape all sites concurrently
        tasks = {
            site: scraper.get_live_games()
            for site, scraper in self.scrapers.items()
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        for site, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"[{site}] Scraping error: {result}")
            elif result:
                logger.info(f"[{site}] Got {len(result)} games")
                all_games.extend(result)

        # Deduplicate: same teams = keep entry with most odds available
        deduplicated = self._deduplicate(all_games)
        logger.info(f"Total unique live games: {len(deduplicated)}")
        return deduplicated

    def _deduplicate(self, games: List[LiveGame]) -> List[LiveGame]:
        """
        Merge same game from multiple sites, keeping best available odds.
        Key: normalized home+away team names + score.
        """
        seen: Dict[str, LiveGame] = {}

        for game in games:
            # Normalize team names for matching
            key = self._make_key(game.home_team, game.away_team)

            if key not in seen:
                seen[key] = game
            else:
                # Merge: keep whichever has more odds data
                existing = seen[key]
                merged = self._merge_games(existing, game)
                seen[key] = merged

        return list(seen.values())

    def _make_key(self, home: str, away: str) -> str:
        """Normalize team names for deduplication."""
        def normalize(name: str) -> str:
            return name.lower().strip().replace(" fc", "").replace("fc ", "").replace(".", "")
        return f"{normalize(home)}__vs__{normalize(away)}"

    def _merge_games(self, a: LiveGame, b: LiveGame) -> LiveGame:
        """Merge two LiveGame entries, taking best available odds from each."""
        # Take odds from whichever source has them
        a.odds_home_win = a.odds_home_win or b.odds_home_win
        a.odds_draw = a.odds_draw or b.odds_draw
        a.odds_away_win = a.odds_away_win or b.odds_away_win
        a.odds_over_25 = a.odds_over_25 or b.odds_over_25
        a.odds_under_25 = a.odds_under_25 or b.odds_under_25
        a.odds_btts_yes = a.odds_btts_yes or b.odds_btts_yes
        a.odds_btts_no = a.odds_btts_no or b.odds_btts_no

        # Prefer higher odds (better value for bettor)
        if a.odds_home_win and b.odds_home_win:
            a.odds_home_win = max(a.odds_home_win, b.odds_home_win)
        if a.odds_over_25 and b.odds_over_25:
            a.odds_over_25 = max(a.odds_over_25, b.odds_over_25)

        # Keep track of all sites offering this game
        a.extra_markets["also_on"] = b.site
        return a

    async def place_bet(self, game: LiveGame, bet_type: str, stake: float) -> bool:
        """Place bet via the appropriate site's scraper."""
        site = game.site
        if site in self.scrapers:
            return await self.scrapers[site].place_bet(game, bet_type, stake)
        logger.error(f"No scraper available for site: {site}")
        return False

    async def stop(self):
        """Cleanly close all browsers."""
        for scraper in self.scrapers.values():
            await scraper.close()
        if self.playwright:
            await self.playwright.stop()
        self._active = False
        logger.info("All scrapers stopped.")
