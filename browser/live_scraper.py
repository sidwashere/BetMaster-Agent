"""
browser/live_scraper.py
Direct API scraper for 1xbet - bypasses DOM for more reliable data
"""

import asyncio
import logging
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class LiveGame:
    """Represents a live football game with odds"""
    game_id: str
    home_team: str
    away_team: str
    home_score: int = 0
    away_score: int = 0
    minute: int = 0
    league: str = ""
    site: str = "1xbet"
    odds_home_win: Optional[float] = None
    odds_draw: Optional[float] = None
    odds_away_win: Optional[float] = None
    odds_over_25: Optional[float] = None
    odds_under_25: Optional[float] = None
    odds_btts_yes: Optional[float] = None
    odds_btts_no: Optional[float] = None
    bet_url: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class LiveScraper:
    """
    Direct API scraper for 1xbet live games.
    Uses multiple strategies:
    1. Direct API calls to 1xbet endpoints
    2. Browser agent fallback (via BrowserAgent)
    3. The Odds API as backup data source
    """
    
    # 1xbet API endpoints (these are internal and may change)
    API_ENDPOINTS = [
        "https://1xbet.com/LiveFeed/Get1x2_VZip",
        "https://1xbet.com/LiveFeed/GetChampionshipVZip",
        "https://1xbet.com/api/v1/live/events",
    ]
    
    def __init__(self, browser_agent=None, odds_api_key: str = None):
        self.browser_agent = browser_agent
        self.odds_api_key = odds_api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_fetch = None
        self._cache_ttl = 30  # seconds
        self._cached_games: List[LiveGame] = []
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/html",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
        return self._session
    
    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def get_live_games(self, force_refresh: bool = False) -> List[LiveGame]:
        """
        Get live games using multiple strategies.
        Returns cached results if within TTL.
        """
        # Check cache
        if not force_refresh and self._cached_games:
            import time
            if time.time() - self._last_fetch < self._cache_ttl:
                return self._cached_games
        
        games = []
        
        # Strategy 1: Try browser agent
        if self.browser_agent and self.browser_agent.is_connected:
            try:
                games = await self._get_via_browser()
                if games:
                    logger.info(f"Got {len(games)} games via browser agent")
                    self._update_cache(games)
                    return games
            except Exception as e:
                logger.warning(f"Browser agent failed: {e}")
        
        # Strategy 2: Try direct API (if accessible)
        games = await self._get_via_direct_api()
        if games:
            logger.info(f"Got {len(games)} games via direct API")
            self._update_cache(games)
            return games
        
        # Strategy 3: The Odds API backup
        if self.odds_api_key:
            games = await self._get_via_odds_api()
            if games:
                logger.info(f"Got {len(games)} games via Odds API")
                self._update_cache(games)
                return games
        
        # Return cached if all strategies fail
        if self._cached_games:
            logger.warning("Using stale cache - all sources failed")
            return self._cached_games
        
        return []
    
    async def _get_via_browser(self) -> List[LiveGame]:
        """Get games using browser agent"""
        if not self.browser_agent or not self.browser_agent.page:
            return []
        
        try:
            # Evaluate JS to get 1xbet internal data
            game_events = await self.browser_agent.get_all_games_via_api()
            
            # Convert to LiveGame format
            games = []
            for event in game_events:
                game = LiveGame(
                    game_id=event.id,
                    home_team=event.home_team,
                    away_team=event.away_team,
                    home_score=event.home_score,
                    away_score=event.away_score,
                    minute=event.minute,
                    league=event.league,
                    odds_home_win=event.odds.get("home_win"),
                    odds_draw=event.odds.get("draw"),
                    odds_away_win=event.odds.get("away_win"),
                    odds_over_25=event.odds.get("over_25"),
                    odds_under_25=event.odds.get("under_25"),
                    odds_btts_yes=event.odds.get("btts_yes"),
                    bet_url=f"https://1xbet.com/en/line/football/event/{event.id.replace('1xbet_', '')}",
                    raw_data=event.raw_data
                )
                games.append(game)
            
            return games
        except Exception as e:
            logger.error(f"Browser scraper error: {e}")
            return []
    
    async def _get_via_direct_api(self) -> List[LiveGame]:
        """Try direct API calls to 1xbet"""
        games = []
        
        # Try each endpoint
        for endpoint in self.API_ENDPOINTS:
            try:
                session = await self.get_session()
                
                # 1xbet often requires specific parameters
                params = {
                    "sports": "1",  # Football
                    "champs": "0",
                    "count": "50",
                    "lng": "en",
                    "mode": "4",
                    "getMulti": "1",
                }
                
                async with session.get(endpoint, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        games = self._parse_1xbet_response(data)
                        if games:
                            logger.info(f"Direct API success: {len(games)} games from {endpoint}")
                            return games
                    else:
                        logger.debug(f"API {endpoint} returned {resp.status}")
                        
            except asyncio.TimeoutError:
                logger.debug(f"API timeout: {endpoint}")
            except Exception as e:
                logger.debug(f"API error {endpoint}: {e}")
        
        return games
    
    def _parse_1xbet_response(self, data: Dict) -> List[LiveGame]:
        """Parse 1xbet API response"""
        games = []
        
        try:
            events = data.get("Value", data.get("value", []))
            if not isinstance(events, list):
                events = [events]
            
            for event in events:
                try:
                    # Skip non-football or virtual
                    league = event.get("L", "")
                    if any(term in league.lower() for term in ["fifa", "esoccer", "virtual", "cyber", "e-sports"]):
                        continue
                    
                    game_id = str(event.get("Id", ""))
                    home = event.get("O1", "Unknown")
                    away = event.get("O2", "Unknown")
                    
                    # Score
                    score = event.get("SC", {})
                    if isinstance(score, dict):
                        home_score = int(score.get("FS", {}).get("H", 0))
                        away_score = int(score.get("FS", {}).get("G", 0))
                    else:
                        home_score = 0
                        away_score = 0
                    
                    minute = int(event.get("LE", 0))
                    
                    # Extract odds
                    odds = self._extract_odds(event.get("E", []))
                    
                    game = LiveGame(
                        game_id=f"1xbet_{game_id}",
                        home_team=home,
                        away_team=away,
                        home_score=home_score,
                        away_score=away_score,
                        minute=minute,
                        league=league,
                        odds_home_win=odds.get("home_win"),
                        odds_draw=odds.get("draw"),
                        odds_away_win=odds.get("away_win"),
                        odds_over_25=odds.get("over_25"),
                        odds_under_25=odds.get("under_25"),
                        odds_btts_yes=odds.get("btts_yes"),
                        odds_btts_no=odds.get("btts_no"),
                        bet_url=f"https://1xbet.com/en/line/football/event/{game_id}",
                        raw_data=event
                    )
                    games.append(game)
                    
                except Exception as e:
                    logger.debug(f"Event parse error: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Response parse error: {e}")
        
        return games
    
    def _extract_odds(self, markets: List) -> Dict[str, float]:
        """Extract odds from market data"""
        odds = {}
        
        for market in markets:
            try:
                market_type = market.get("T", 0)
                outcomes = market.get("E", [])
                
                # 1X2 (match result)
                if market_type == 1 and len(outcomes) >= 3:
                    odds["home_win"] = float(outcomes[0].get("C", 0)) or None
                    odds["draw"] = float(outcomes[1].get("C", 0)) or None
                    odds["away_win"] = float(outcomes[2].get("C", 0)) or None
                
                # Total goals
                elif market_type == 17:
                    for o in outcomes:
                        name = str(o.get("N", "")).lower()
                        if "2.5" in name:
                            outcome_type = o.get("T", 0)
                            if outcome_type == 1 or "over" in name:
                                odds["over_25"] = float(o.get("C", 0)) or None
                            else:
                                odds["under_25"] = float(o.get("C", 0)) or None
                
                # BTTS
                elif market_type == 40:
                    for o in outcomes:
                        name = str(o.get("N", "")).lower()
                        if "yes" in name:
                            odds["btts_yes"] = float(o.get("C", 0)) or None
                        elif "no" in name:
                            odds["btts_no"] = float(o.get("C", 0)) or None
                
            except Exception as e:
                continue
        
        # Clean up None values
        return {k: v for k, v in odds.items() if v}
    
    async def _get_via_odds_api(self) -> List[LiveGame]:
        """Get games via The Odds API (backup data source)"""
        games = []
        
        if not self.odds_api_key:
            return games
        
        try:
            session = await self.get_session()
            
            # Odds API for live odds - use soccer_epl which works
            url = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
            params = {
                "apiKey": self.odds_api_key,
                "regions": "uk,us,eu",
                "markets": "h2h,totals",
                "oddsFormat": "decimal",
                "live": "true"
            }
            
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"Odds API returned {len(data)} games")
                    
                    for event in data:
                        # Use first available bookmaker (not just 1xbet)
                        bookmakers = event.get("bookmakers", [])
                        if not bookmakers:
                            continue
                        
                        # Use the first bookmaker with odds
                        bookmaker = bookmakers[0]
                        
                        home = event.get("home_team", "Unknown")
                        away = event.get("away_team", "Unknown")
                        
                        # Parse score if available (live)
                        scores = event.get("scores", [])
                        home_score = 0
                        away_score = 0
                        for s in scores:
                            if s.get("name") == "home":
                                home_score = s.get("score", 0)
                            elif s.get("name") == "away":
                                away_score = s.get("score", 0)
                        
                        # Parse time
                        #commence_time = event.get("commence_time", "")
                        #live_status = event.get("live", False)
                        
                        # Extract odds
                        odds = {}
                        for outcome in bookmaker.get("markets", []):
                            if outcome.get("key") == "h2h":
                                for o in outcome.get("outcomes", []):
                                    name = o.get("name", "").lower()
                                    if home.lower() in name:
                                        odds["home_win"] = o.get("price")
                                    elif away.lower() in name:
                                        odds["away_win"] = o.get("price")
                                    elif "draw" in name:
                                        odds["draw"] = o.get("price")
                            
                            elif outcome.get("key") == "totals":
                                for o in outcome.get("outcomes", []):
                                    name = o.get("name", "").lower()
                                    if "over" in name:
                                        odds["over_25"] = o.get("price")
                                    elif "under" in name:
                                        odds["under_25"] = o.get("price")
                        
                        game = LiveGame(
                            game_id=f"oddsapi_{event.get('id', '')}",
                            home_team=home,
                            away_team=away,
                            home_score=home_score,
                            away_score=away_score,
                            minute=0,  # Odds API doesn't always provide live minute
                            league=event.get("league", "Unknown"),
                            site="odds_api",
                            odds_home_win=odds.get("home_win"),
                            odds_draw=odds.get("draw"),
                            odds_away_win=odds.get("away_win"),
                            odds_over_25=odds.get("over_25"),
                            odds_under_25=odds.get("under_25"),
                            bet_url=event.get("home_team", "")
                        )
                        games.append(game)
                    
                    logger.info(f"Odds API: {len(games)} games")
                    
        except Exception as e:
            logger.error(f"Odds API error: {e}")
        
        return games
    
    def _update_cache(self, games: List[LiveGame]):
        """Update the game cache"""
        import time
        self._cached_games = games
        self._last_fetch = time.time()
    
    async def refresh(self):
        """Force refresh the game cache"""
        return await self.get_live_games(force_refresh=True)


# Singleton
_live_scraper: Optional[LiveScraper] = None

def get_live_scraper(browser_agent=None, odds_api_key: str = None) -> LiveScraper:
    """Get the global live scraper instance"""
    global _live_scraper
    if _live_scraper is None:
        _live_scraper = LiveScraper(browser_agent, odds_api_key)
    return _live_scraper
