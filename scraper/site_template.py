"""
scraper/site_template.py
Template for adding a new betting site.

INSTRUCTIONS TO ADD A NEW SITE:
1. Copy this file to scraper/site_YOURSITE.py
2. Replace all "YOURSITE" occurrences
3. Implement the 4 abstract methods
4. Add to scraper/scraper_manager.py SCRAPER_CLASSES dict
5. Add URL to config.py SITE_URLS
6. Add site name to config.py ENABLED_SITES

That's it! The rest of the system picks it up automatically.

TIPS for finding API endpoints:
- Open DevTools in Chrome (F12) → Network tab
- Filter by "Fetch/XHR"
- Navigate to the live games page
- Look for requests returning JSON with odds data
- Copy the request URL and headers
"""

import asyncio
import logging
import re
from typing import List
from .base_scraper import BaseScraper, LiveGame
import config

logger = logging.getLogger(__name__)


class YOURSITEScraper(BaseScraper):

    def __init__(self):
        super().__init__("yoursite", config.SITE_URLS.get("yoursite", ""))

    async def get_live_games(self) -> List[LiveGame]:
        """
        Fetch live games from YOURSITE.
        
        Implementation strategies (pick one):
        A) API interception: intercept XHR calls, parse JSON
        B) DOM scraping: use Playwright to select elements
        C) Direct API: call their internal REST endpoint directly
        """
        games = []

        try:
            await self.safe_goto(self.url)
            await self.page.wait_for_timeout(3000)

            # ─── YOUR SCRAPING CODE HERE ───

            # Example DOM approach:
            # rows = await self.page.query_selector_all(".live-game-row")
            # for row in rows:
            #     home = await row.query_selector(".home-team")
            #     ... etc

            # Example API interception:
            # self.page.on("response", self._handle_response)
            # await self.page.wait_for_timeout(5000)
            # if self._api_data:
            #     games = self._parse(self._api_data)

        except Exception as e:
            logger.error(f"[YOURSITE] Scraping failed: {e}")

        return games

    async def place_bet(self, game: LiveGame, bet_type: str, stake: float) -> bool:
        """Place a bet on YOURSITE."""
        try:
            await self.safe_goto(game.bet_url)
            await self.page.wait_for_timeout(2000)

            # 1. Click the odds button for bet_type
            # 2. Enter stake amount
            # 3. Click "Place Bet"
            # 4. Return True if successful

            # Example:
            # await self.page.click(f"[data-bet='{bet_type}']")
            # await self.page.fill("input.stake", str(stake))
            # await self.page.click("button.place-bet")
            return True

        except Exception as e:
            logger.error(f"[YOURSITE] Bet failed: {e}")
            return False

    async def login(self) -> bool:
        """Login to YOURSITE account."""
        creds = config.SITE_CREDENTIALS.get("yoursite", {})
        if not creds.get("username"):
            return False

        try:
            await self.safe_goto("https://yoursite.com/login")
            await self.page.fill("input[name='username']", creds["username"])
            await self.page.fill("input[name='password']", creds["password"])
            await self.page.click("button[type='submit']")
            await self.page.wait_for_timeout(3000)
            return True
        except Exception as e:
            logger.error(f"[YOURSITE] Login failed: {e}")
            return False

    async def get_balance(self) -> float:
        """Fetch account balance."""
        try:
            el = await self.page.query_selector(".balance-display")
            if el:
                text = (await el.inner_text()).strip()
                return float(re.sub(r"[^\d.]", "", text))
        except Exception:
            pass
        return 0.0
