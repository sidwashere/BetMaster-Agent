"""
scraper/site_1xbet.py
Scrapes live football games + odds from 1xbet.com

Approach:
- Uses Playwright to navigate 1xbet live section
- Intercepts XHR/API calls (1xbet uses internal API endpoints)
- Falls back to DOM scraping if API interception fails

Reference pattern: github.com/microsoft/playwright-python/blob/main/examples
"""

import asyncio
import json
import logging
import re
from typing import List
from .base_scraper import BaseScraper, LiveGame
import config

logger = logging.getLogger(__name__)


class XBetScraper(BaseScraper):

    def __init__(self):
        super().__init__("1xbet", config.SITE_URLS["1xbet"])
        self._captured_games = []
        self._api_response = None

    async def get_live_games(self) -> List[LiveGame]:
        """
        Strategy: intercept 1xbet's internal API calls for live odds.
        1xbet loads live data via: /LiveFeed/Get1x2_VZip or similar endpoints.
        We capture these network responses directly.
        """
        games = []

        try:
            # Intercept network responses to capture odds data
            self.page.on("response", self._handle_response)

            await self.safe_goto(self.url)
            
            # Wait for live games to load
            await self.page.wait_for_timeout(4000)

            # Click football/soccer filter if needed
            try:
                await self.page.click('[data-sport-id="1"], .sport-icon--football', timeout=3000)
                await self.page.wait_for_timeout(2000)
            except Exception:
                pass  # Already on football or selector changed

            # If API interception worked, use that data
            if self._api_response:
                games = self._parse_api_response(self._api_response)
                logger.info(f"[1xbet] Got {len(games)} games via API interception")
            else:
                # Fallback: DOM scraping
                games = await self._scrape_dom()
                logger.info(f"[1xbet] Got {len(games)} games via DOM scraping")

        except Exception as e:
            logger.error(f"[1xbet] Scraping failed: {e}")

        return games

    async def _handle_response(self, response):
        """Capture API responses containing live odds data."""
        url = response.url
        # 1xbet serves live data through these patterns
        if any(pattern in url for pattern in [
            "LiveFeed", "live-games", "1x2", "odds"
        ]):
            try:
                if response.status == 200:
                    body = await response.json()
                    self._api_response = body
            except Exception:
                pass

    def _parse_api_response(self, data: dict) -> List[LiveGame]:
        """Parse 1xbet API JSON response into LiveGame objects."""
        games = []
        try:
            # 1xbet API structure varies - handle common patterns
            events = data.get("Value", data.get("events", data.get("data", [])))
            if isinstance(events, list):
                for event in events:
                    game = self._parse_event(event)
                    if game:
                        games.append(game)
        except Exception as e:
            logger.debug(f"[1xbet] API parse error: {e}")
        return games

    def _parse_event(self, event: dict) -> LiveGame:
        """Parse a single event from 1xbet API."""
        try:
            game_id = str(event.get("Id", event.get("id", "")))
            home = event.get("O1", event.get("homeTeam", {}).get("name", "Unknown"))
            away = event.get("O2", event.get("awayTeam", {}).get("name", "Unknown"))
            
            score = event.get("SC", {})
            home_score = int(score.get("FS", {}).get("H", 0))
            away_score = int(score.get("FS", {}).get("G", 0))
            minute = int(event.get("LE", 0))
            league = event.get("L", "Unknown League")

            # Extract odds - 1xbet odds structure
            odds = self._extract_odds(event.get("E", []))

            return LiveGame(
                game_id=f"1xbet_{game_id}",
                home_team=home,
                away_team=away,
                home_score=home_score,
                away_score=away_score,
                minute=minute,
                league=league,
                site="1xbet",
                odds_home_win=odds.get("home_win"),
                odds_draw=odds.get("draw"),
                odds_away_win=odds.get("away_win"),
                odds_over_25=odds.get("over_25"),
                odds_under_25=odds.get("under_25"),
                odds_btts_yes=odds.get("btts_yes"),
                bet_url=f"https://1xbet.com/en/line/football/event/{game_id}",
            )
        except Exception as e:
            logger.debug(f"[1xbet] Event parse error: {e}")
            return None

    def _extract_odds(self, markets: list) -> dict:
        """Extract standard odds from 1xbet market structure."""
        odds = {}
        for market in markets:
            market_id = market.get("T", 0)
            outcomes = market.get("E", [])
            
            # Market type 1 = 1X2 (match result)
            if market_id == 1 and len(outcomes) >= 3:
                odds["home_win"] = outcomes[0].get("C", None)
                odds["draw"] = outcomes[1].get("C", None)
                odds["away_win"] = outcomes[2].get("C", None)
            
            # Market type 17 = Total goals over/under
            elif market_id == 17:
                for o in outcomes:
                    name = o.get("N", "").lower()
                    if "2.5" in name:
                        if "over" in name or o.get("T") == 1:
                            odds["over_25"] = o.get("C")
                        else:
                            odds["under_25"] = o.get("C")
            
            # BTTS
            elif market_id == 40:
                for o in outcomes:
                    name = o.get("N", "").lower()
                    if "yes" in name:
                        odds["btts_yes"] = o.get("C")
                    elif "no" in name:
                        odds["btts_no"] = o.get("C")
        
        return odds

    async def _scrape_dom(self) -> List[LiveGame]:
        """DOM fallback scraper for 1xbet."""
        games = []
        try:
            # Wait for game rows
            await self.page.wait_for_selector(".liveLine__game, [class*='live-game']", timeout=8000)
            
            game_elements = await self.page.query_selector_all(
                ".liveLine__game, .live-event-row, [data-live-game]"
            )

            for el in game_elements[:20]:  # Limit to 20 games
                try:
                    home = await el.query_selector(".liveLine__teamName:first-child, .team-home")
                    away = await el.query_selector(".liveLine__teamName:last-child, .team-away")
                    score_el = await el.query_selector(".liveLine__score, .score")
                    minute_el = await el.query_selector(".liveLine__time, .game-time")

                    if not all([home, away]):
                        continue

                    home_name = (await home.inner_text()).strip()
                    away_name = (await away.inner_text()).strip()
                    score_text = (await score_el.inner_text()).strip() if score_el else "0:0"
                    minute_text = (await minute_el.inner_text()).strip() if minute_el else "0"

                    # Parse score
                    parts = re.split(r"[-:]", score_text)
                    hs = int(parts[0]) if parts else 0
                    as_ = int(parts[1]) if len(parts) > 1 else 0
                    minute = int(re.sub(r"\D", "", minute_text) or 0)

                    # Odds from buttons
                    odd_buttons = await el.query_selector_all(".odd, .coefficient, [class*='odds']")
                    odds_vals = []
                    for btn in odd_buttons[:5]:
                        txt = (await btn.inner_text()).strip()
                        try:
                            odds_vals.append(float(txt))
                        except ValueError:
                            pass

                    game = LiveGame(
                        game_id=f"1xbet_dom_{hash(home_name + away_name)}",
                        home_team=home_name,
                        away_team=away_name,
                        home_score=hs,
                        away_score=as_,
                        minute=minute,
                        league="Live",
                        site="1xbet",
                        odds_home_win=odds_vals[0] if len(odds_vals) > 0 else None,
                        odds_draw=odds_vals[1] if len(odds_vals) > 1 else None,
                        odds_away_win=odds_vals[2] if len(odds_vals) > 2 else None,
                    )
                    games.append(game)

                except Exception as e:
                    logger.debug(f"[1xbet] Row parse error: {e}")

        except Exception as e:
            logger.warning(f"[1xbet] DOM scraping failed: {e}")

        return games

    async def place_bet(self, game: LiveGame, bet_type: str, stake: float) -> bool:
        """Auto-place a bet on 1xbet."""
        try:
            logger.info(f"[1xbet] Placing {bet_type} bet on {game.home_team} vs {game.away_team}, stake: {stake}")

            # Navigate to game
            await self.safe_goto(game.bet_url)
            await self.page.wait_for_timeout(2000)

            # Map bet_type to button selector
            bet_selectors = {
                "home": ".odds-item:nth-child(1), [data-outcome='1']",
                "draw": ".odds-item:nth-child(2), [data-outcome='X']",
                "away": ".odds-item:nth-child(3), [data-outcome='2']",
                "over_25": "[data-market='over'] [data-value='2.5']",
                "under_25": "[data-market='under'] [data-value='2.5']",
            }

            selector = bet_selectors.get(bet_type)
            if not selector:
                logger.error(f"[1xbet] Unknown bet type: {bet_type}")
                return False

            # Click the odds button → adds to betslip
            await self.page.click(selector, timeout=5000)
            await self.page.wait_for_timeout(1000)

            # Enter stake amount
            stake_input = await self.page.query_selector("input.betslip__stake, [placeholder*='stake'], [name*='amount']")
            if stake_input:
                await stake_input.triple_click()
                await stake_input.type(str(int(stake)))
                await self.page.wait_for_timeout(500)

            # Click Place Bet button
            place_btn = await self.page.query_selector(".betslip__place-bet, button:has-text('Place bet'), [data-action='place-bet']")
            if place_btn:
                await place_btn.click()
                await self.page.wait_for_timeout(2000)
                logger.info(f"[1xbet] ✅ Bet placed successfully")
                return True
            else:
                logger.error("[1xbet] Could not find 'Place Bet' button")
                return False

        except Exception as e:
            logger.error(f"[1xbet] Auto-bet failed: {e}")
            return False

    async def login(self) -> bool:
        """Login to 1xbet account."""
        creds = config.SITE_CREDENTIALS.get("1xbet", {})
        username = creds.get("username", "")
        password = creds.get("password", "")

        if not username or not password:
            logger.warning("[1xbet] No credentials configured")
            return False

        try:
            await self.safe_goto("https://1xbet.com/en/login")
            await self.page.fill("input[name='email'], input[type='email']", username)
            await self.page.fill("input[name='password'], input[type='password']", password)
            await self.page.click("button[type='submit'], .login-btn")
            await self.page.wait_for_timeout(3000)
            return True
        except Exception as e:
            logger.error(f"[1xbet] Login failed: {e}")
            return False

    async def get_balance(self) -> float:
        """Fetch current account balance."""
        try:
            balance_el = await self.page.query_selector(".user-info__balance, [class*='balance-amount']")
            if balance_el:
                text = (await balance_el.inner_text()).strip()
                return float(re.sub(r"[^\d.]", "", text))
        except Exception:
            pass
        return 0.0
