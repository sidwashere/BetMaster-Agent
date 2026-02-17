"""
scraper/site_sportpesa.py
Scrapes live football games + odds from sportpesa.com

SportPesa loads data via REST API calls to their backend.
We intercept these calls to get structured JSON data.
"""

import asyncio
import json
import logging
import re
from typing import List
from .base_scraper import BaseScraper, LiveGame
import config

logger = logging.getLogger(__name__)


class SportPesaScraper(BaseScraper):

    def __init__(self):
        super().__init__("sportpesa", config.SITE_URLS["sportpesa"])
        self._live_data = None

    async def get_live_games(self) -> List[LiveGame]:
        games = []

        try:
            # SportPesa API endpoint pattern (found via network inspection)
            api_url = "https://www.sportpesa.com/api/v1/games/live?sport=football&page=1&limit=50"
            
            # Try direct API call first (no auth needed for public odds)
            games = await self._fetch_via_api(api_url)

            if not games:
                # Fallback: browser-based scraping
                self.page.on("response", self._handle_response)
                await self.safe_goto(self.url)
                await self.page.wait_for_timeout(5000)

                if self._live_data:
                    games = self._parse_live_data(self._live_data)
                else:
                    games = await self._scrape_dom()

            logger.info(f"[SportPesa] Found {len(games)} live games")

        except Exception as e:
            logger.error(f"[SportPesa] Failed: {e}")

        return games

    async def _fetch_via_api(self, api_url: str) -> List[LiveGame]:
        """Try to fetch directly from SportPesa's internal API."""
        try:
            import aiohttp
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.sportpesa.com/",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self._parse_live_data(data)
        except Exception as e:
            logger.debug(f"[SportPesa] Direct API failed: {e}")
        return []

    async def _handle_response(self, response):
        """Intercept SportPesa API responses."""
        url = response.url
        if any(p in url for p in ["live", "events", "odds", "api/v"]):
            try:
                if response.status == 200:
                    body = await response.json()
                    if isinstance(body, (list, dict)) and body:
                        self._live_data = body
            except Exception:
                pass

    def _parse_live_data(self, data) -> List[LiveGame]:
        """Parse SportPesa API response."""
        games = []
        try:
            # Handle both list and dict responses
            events = data if isinstance(data, list) else data.get("data", data.get("events", []))
            
            for event in events:
                game = self._parse_event(event)
                if game:
                    games.append(game)
        except Exception as e:
            logger.debug(f"[SportPesa] Parse error: {e}")
        return games

    def _parse_event(self, event: dict) -> LiveGame:
        """Parse single event from SportPesa."""
        try:
            game_id = str(event.get("id", event.get("eventId", "")))
            
            # Team names
            home = event.get("homeName", event.get("home_team", {}).get("name", ""))
            away = event.get("awayName", event.get("away_team", {}).get("name", ""))
            
            if not home or not away:
                return None

            # Score
            home_score = int(event.get("homeScore", event.get("home_score", 0)) or 0)
            away_score = int(event.get("awayScore", event.get("away_score", 0)) or 0)
            minute = int(event.get("minute", event.get("elapsed", 0)) or 0)
            league = event.get("competitionName", event.get("competition", {}).get("name", "Unknown"))

            # Odds parsing - SportPesa structure
            markets = event.get("markets", event.get("odds", []))
            odds = self._parse_markets(markets)

            return LiveGame(
                game_id=f"sportpesa_{game_id}",
                home_team=home,
                away_team=away,
                home_score=home_score,
                away_score=away_score,
                minute=minute,
                league=league,
                site="sportpesa",
                odds_home_win=odds.get("home"),
                odds_draw=odds.get("draw"),
                odds_away_win=odds.get("away"),
                odds_over_25=odds.get("over_25"),
                odds_under_25=odds.get("under_25"),
                odds_btts_yes=odds.get("btts_yes"),
                bet_url=f"https://www.sportpesa.com/games/live/{game_id}",
            )
        except Exception as e:
            logger.debug(f"[SportPesa] Event parse error: {e}")
            return None

    def _parse_markets(self, markets) -> dict:
        """Extract odds from SportPesa market structure."""
        odds = {}
        
        if isinstance(markets, list):
            for market in markets:
                name = market.get("name", market.get("marketName", "")).lower()
                picks = market.get("picks", market.get("outcomes", []))
                
                if "match result" in name or "1x2" in name or "moneyline" in name:
                    for pick in picks:
                        label = pick.get("label", pick.get("name", "")).upper()
                        val = float(pick.get("odds", pick.get("value", 0)) or 0)
                        if "1" == label or "HOME" in label:
                            odds["home"] = val
                        elif "X" == label or "DRAW" in label:
                            odds["draw"] = val
                        elif "2" == label or "AWAY" in label:
                            odds["away"] = val
                
                elif "over" in name or "under" in name or "total" in name:
                    for pick in picks:
                        label = pick.get("label", pick.get("name", "")).lower()
                        val = float(pick.get("odds", pick.get("value", 0)) or 0)
                        if "over" in label and "2.5" in label:
                            odds["over_25"] = val
                        elif "under" in label and "2.5" in label:
                            odds["under_25"] = val
                
                elif "both teams" in name or "btts" in name or "gg" in name:
                    for pick in picks:
                        label = pick.get("label", pick.get("name", "")).lower()
                        val = float(pick.get("odds", pick.get("value", 0)) or 0)
                        if "yes" in label or "gg" == label:
                            odds["btts_yes"] = val
                        elif "no" in label or "ng" == label:
                            odds["btts_no"] = val

        return odds

    async def _scrape_dom(self) -> List[LiveGame]:
        """DOM fallback for SportPesa."""
        games = []
        try:
            await self.page.wait_for_selector(".live-event, [class*='event-row'], .match-row", timeout=8000)
            rows = await self.page.query_selector_all(".live-event, [class*='live-match'], .event-item")

            for row in rows[:20]:
                try:
                    teams = await row.query_selector_all(".team-name, .participant")
                    if len(teams) < 2:
                        continue
                    home_name = (await teams[0].inner_text()).strip()
                    away_name = (await teams[1].inner_text()).strip()

                    score_el = await row.query_selector(".score, .result")
                    score_text = (await score_el.inner_text()).strip() if score_el else "0-0"
                    parts = re.split(r"[-:]", score_text)
                    hs = int(parts[0]) if parts else 0
                    as_ = int(parts[1]) if len(parts) > 1 else 0

                    time_el = await row.query_selector(".time, .minute, .elapsed")
                    minute_text = (await time_el.inner_text()).strip() if time_el else "0"
                    minute = int(re.sub(r"\D", "", minute_text) or 0)

                    odd_els = await row.query_selector_all(".odd-value, .odds button, .pick-value")
                    odd_vals = []
                    for o in odd_els[:5]:
                        try:
                            odd_vals.append(float((await o.inner_text()).strip()))
                        except ValueError:
                            pass

                    games.append(LiveGame(
                        game_id=f"sp_dom_{hash(home_name + away_name)}",
                        home_team=home_name,
                        away_team=away_name,
                        home_score=hs,
                        away_score=as_,
                        minute=minute,
                        league="Live",
                        site="sportpesa",
                        odds_home_win=odd_vals[0] if odd_vals else None,
                        odds_draw=odd_vals[1] if len(odd_vals) > 1 else None,
                        odds_away_win=odd_vals[2] if len(odd_vals) > 2 else None,
                    ))
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[SportPesa] DOM scrape failed: {e}")
        return games

    async def place_bet(self, game: LiveGame, bet_type: str, stake: float) -> bool:
        """Place bet on SportPesa."""
        try:
            await self.safe_goto(game.bet_url)
            await self.page.wait_for_timeout(2000)

            bet_map = {
                "home": "[data-outcome='1'], .market-pick:nth-child(1)",
                "draw": "[data-outcome='x'], .market-pick:nth-child(2)",
                "away": "[data-outcome='2'], .market-pick:nth-child(3)",
                "over_25": "[data-label*='Over 2.5']",
                "under_25": "[data-label*='Under 2.5']",
            }

            selector = bet_map.get(bet_type)
            if not selector:
                return False

            await self.page.click(selector, timeout=5000)
            await self.page.wait_for_timeout(800)

            stake_el = await self.page.query_selector("input.betslip-input, input[placeholder*='amount'], input[name*='stake']")
            if stake_el:
                await stake_el.triple_click()
                await stake_el.type(str(int(stake)))

            place_el = await self.page.query_selector("button.place-bet, button:has-text('Place Bet'), .confirm-bet")
            if place_el:
                await place_el.click()
                await self.page.wait_for_timeout(2000)
                logger.info("[SportPesa] ✅ Bet placed")
                return True

        except Exception as e:
            logger.error(f"[SportPesa] Auto-bet error: {e}")
        return False

    async def login(self) -> bool:
        creds = config.SITE_CREDENTIALS.get("sportpesa", {})
        if not creds.get("username"):
            return False
        try:
            await self.safe_goto("https://www.sportpesa.com/login")
            await self.page.fill("input[name='username'], input[type='tel']", creds["username"])
            await self.page.fill("input[name='password']", creds["password"])
            await self.page.click("button[type='submit']")
            await self.page.wait_for_timeout(3000)
            return True
        except Exception as e:
            logger.error(f"[SportPesa] Login error: {e}")
            return False

    async def get_balance(self) -> float:
        try:
            el = await self.page.query_selector(".user-balance, [class*='balance']")
            if el:
                text = (await el.inner_text()).strip()
                return float(re.sub(r"[^\d.]", "", text))
        except Exception:
            pass
        return 0.0
