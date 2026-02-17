"""
scraper/base_scraper.py
Abstract base class all site scrapers must implement.
Inspired by: github.com/microsoft/playwright-python examples
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class LiveGame:
    """Represents a single live football game with odds."""
    game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    minute: int                     # Current game minute
    league: str
    site: str                       # Which site this came from
    
    # Odds available on the site
    odds_home_win: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away_win: Optional[float] = None
    odds_over_25: Optional[float] = None
    odds_under_25: Optional[float] = None
    odds_over_35: Optional[float] = None
    odds_under_35: Optional[float] = None
    odds_btts_yes: Optional[float] = None   # Both Teams To Score
    odds_btts_no: Optional[float] = None
    
    # Metadata
    bet_url: str = ""              # Direct URL to place bet
    extra_markets: dict = field(default_factory=dict)  # Any extra odds


class BaseScraper(ABC):
    """
    Abstract scraper. Subclass this for each betting site.
    
    Pattern derived from: github.com/microsoft/playwright-python
    and adapted from: github.com/nicholasmccullum/python-automation
    """

    def __init__(self, site_name: str, url: str):
        self.site_name = site_name
        self.url = url
        self.browser = None
        self.page = None

    @abstractmethod
    async def get_live_games(self) -> List[LiveGame]:
        """Scrape and return all current live football games."""
        pass

    @abstractmethod
    async def place_bet(self, game: LiveGame, bet_type: str, stake: float) -> bool:
        """
        Place a bet on a game.
        bet_type: 'home', 'draw', 'away', 'over_25', 'under_25', etc.
        Returns True if bet was placed successfully.
        """
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        """Return current account balance in KES."""
        pass

    async def setup_browser(self, playwright, headless: bool = False):
        """Initialize Playwright browser."""
        self.browser = await playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        self.page = await context.new_page()
        # Hide automation signals
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
        """)

    async def safe_goto(self, url: str, timeout: int = 30000):
        """Navigate with error handling."""
        try:
            await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            return True
        except Exception as e:
            logger.error(f"[{self.site_name}] Navigation failed: {e}")
            return False

    async def close(self):
        if self.browser:
            await self.browser.close()

    def implied_probability(self, odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if not odds or odds <= 1:
            return 0.0
        return 1.0 / odds

    def to_dict(self, game: LiveGame) -> dict:
        return {
            "id": game.game_id,
            "match": f"{game.home_team} vs {game.away_team}",
            "score": f"{game.home_score}-{game.away_score}",
            "minute": game.minute,
            "league": game.league,
            "site": game.site,
        }
