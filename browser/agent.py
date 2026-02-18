"""
browser/agent.py
Browser Agent - Connects to existing 1xbet browser via Playwright CDP
"""

import asyncio
import logging
import json
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.error("Playwright not installed. Run: pip install playwright")


@dataclass
class GameEvent:
    """Represents a live game event"""
    id: str
    home_team: str
    away_team: str
    home_score: int = 0
    away_score: int = 0
    minute: int = 0
    league: str = ""
    odds: Dict[str, float] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class BrowserAgent:
    """
    Browser Agent that connects to existing 1xbet browser window.
    Uses Playwright CDP to control the browser and scrape live games.
    """
    
    def __init__(self, window_manager=None):
        self.window_manager = window_manager
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._is_connected = False
        self._connection_method = None  # "cdp" or "new"
        
        # Callbacks
        self.on_game_update: Optional[Callable[[List[GameEvent]], None]] = None
        self.on_connection_change: Optional[Callable[[bool, str], None]] = None
    
    async def connect(self, use_existing: bool = True, headless: bool = False) -> bool:
        """
        Connect to browser.
        
        Args:
            use_existing: If True, try to connect to existing 1xbet window via CDP
            headless: If True and no existing, launch new browser in headless mode
        
        Returns:
            True if connection successful
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available")
            return False
        
        try:
            self.playwright = await async_playwright().start()
            
            # Try to connect to existing browser
            if use_existing:
                connected = await self._connect_to_existing_browser()
                if connected:
                    self._connection_method = "cdp"
                    self._is_connected = True
                    self._fire_connection_change(True, "Connected via CDP")
                    return True
            
            # Fallback: launch new browser
            logger.info("Launching new browser...")
            self.browser = await self.playwright.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            self.page = await self.context.new_page()
            self._connection_method = "new"
            self._is_connected = True
            self._fire_connection_change(True, "New browser launched")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to browser: {e}")
            self._fire_connection_change(False, str(e))
            return False
    
    async def _connect_to_existing_browser(self) -> bool:
        """Connect to existing Chrome/Edge browser via CDP"""
        import subprocess
        import re
        
        # Try common CDP ports
        cdp_ports = [9222, 9223, 9224, 9333]
        
        for port in cdp_ports:
            try:
                # Try to connect via CDP
                browser = await self.playwright.chromium.connect_over_cdp(
                    f"http://localhost:{port}"
                )
                
                # Get all contexts
                contexts = browser.contexts
                if contexts:
                    self.browser = browser
                    self.context = contexts[0]
                    
                    # Get all pages
                    pages = self.context.pages
                    if pages:
                        # Find 1xbet page or use first page
                        for page in pages:
                            url = page.url
                            if "1xbet" in url.lower():
                                self.page = page
                                logger.info(f"Connected to existing 1xbet page: {url}")
                                return True
                        
                        # Use first page if no 1xbet found
                        if pages:
                            self.page = pages[0]
                            logger.info(f"Using first page: {self.page.url}")
                            return True
                
                await browser.close()
                
            except Exception as e:
                logger.debug(f"CDP port {port} failed: {e}")
                continue
        
        # Try to find Chrome with remote debugging
        try:
            # Windows: try to get Chrome debug port from command line
            result = subprocess.run(
                ['wmic', 'process', 'where', 'name="chrome.exe"', 'get', 'commandline'],
                capture_output=True, text=True
            )
            
            # Parse output to find debug port
            for line in result.stdout.split('\n')[1:]:
                if '--remote-debugging-port=' in line:
                    match = re.search(r'--remote-debugging-port=(\d+)', line)
                    if match:
                        port = match.group(1)
                        logger.info(f"Found Chrome debug port: {port}")
                        browser = await self.playwright.chromium.connect_over_cdp(
                            f"http://localhost:{port}"
                        )
                        self.browser = browser
                        self.context = browser.contexts[0] if browser.contexts else None
                        self.page = self.context.pages[0] if self.context and self.context.pages else None
                        if self.page:
                            return True
        except Exception as e:
            logger.debug(f"Failed to find Chrome debug port: {e}")
        
        logger.warning("Could not connect to existing browser")
        return False
    
    async def navigate_to_1xbet(self, url: str = None) -> bool:
        """Navigate to 1xbet live football page"""
        if not self.page:
            logger.error("No page available")
            return False
        
        if url is None:
            # Import config dynamically to get current URL
            import config
            url = config.SITE_URLS.get("1xbet", "https://1xbet.co.ke/en/live/football")
        
        try:
            # Use domcontentloaded instead of networkidle for faster loading
            await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Wait for page to settle
            await self.page.wait_for_timeout(5000)
            logger.info(f"Navigated to: {self.page.url}")
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False
    
    async def get_page_content(self) -> Optional[str]:
        """Get current page HTML content"""
        if not self.page:
            return None
        try:
            return await self.page.content()
        except Exception as e:
            logger.error(f"Failed to get page content: {e}")
            return None
    
    async def take_screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        """Take screenshot of current page"""
        if not self.page:
            return None
        
        try:
            screenshot_bytes = await self.page.screenshot(
                full_page=False,
                type='png'
            )
            if path:
                with open(path, 'wb') as f:
                    f.write(screenshot_bytes)
            return screenshot_bytes
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return None
    
    async def execute_js(self, script: str) -> Any:
        """Execute JavaScript in the page"""
        if not self.page:
            return None
        try:
            return await self.page.evaluate(script)
        except Exception as e:
            logger.error(f"JS execution failed: {e}")
            return None
    
    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """Wait for selector to appear"""
        if not self.page:
            return False
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except:
            return False
    
    async def click_element(self, selector: str) -> bool:
        """Click an element by selector"""
        if not self.page:
            return False
        try:
            await self.page.click(selector, timeout=5000)
            return True
        except Exception as e:
            logger.debug(f"Click failed: {e}")
            return False
    
    async def fill_input(self, selector: str, value: str) -> bool:
        """Fill an input field"""
        if not self.page:
            return False
        try:
            await self.page.fill(selector, value)
            return True
        except Exception as e:
            logger.debug(f"Fill failed: {e}")
            return False
    
    async def get_all_games_via_api(self) -> List[GameEvent]:
        """
        Extract live games by intercepting API calls or evaluating page data.
        This is the main method for getting live games.
        """
        games = []
        
        if not self.page:
            return games
        
        try:
            # Take debug screenshot
            try:
                screenshot = await self.page.screenshot(type='png')
                import os
                os.makedirs("debug", exist_ok=True)
                with open("debug/last_page.png", "wb") as f:
                    f.write(screenshot)
                logger.debug("Saved debug screenshot to debug/last_page.png")
            except:
                pass
            
            # Try to get data from page JavaScript
            game_data = await self.page.evaluate("""
                () => {
                    // Try to find 1xbet's internal data
                    // Look for window variables
                    for (let key in window) {
                        if (key.includes('Game') || key.includes('Live') || key.includes('Bet')) {
                            try {
                                const val = window[key];
                                if (val && typeof val === 'object' && val.Value) {
                                    return val;
                                }
                            } catch(e) {}
                        }
                    }
                    return null;
                }
            """)
            
            if game_data:
                games = self._parse_1xbet_api_response(game_data)
            
            # If no games from JS, try DOM scraping
            if not games:
                games = await self._scrape_dom_games()
            
            logger.info(f"Found {len(games)} live games")
            
        except Exception as e:
            logger.error(f"Failed to get games: {e}")
            games = await self._scrape_dom_games()
        
        return games
    
    def _parse_1xbet_api_response(self, data: Dict) -> List[GameEvent]:
        """Parse 1xbet API response into GameEvent objects"""
        games = []
        
        try:
            events = data.get("Value", data.get("value", []))
            if not isinstance(events, list):
                events = [events]
            
            for event in events:
                try:
                    game_id = str(event.get("Id", ""))
                    home = event.get("O1", event.get("homeTeam", {}).get("name", "Unknown"))
                    away = event.get("O2", event.get("awayTeam", {}).get("name", "Unknown"))
                    
                    # Get score
                    score = event.get("SC", {})
                    if isinstance(score, dict):
                        home_score = int(score.get("FS", {}).get("H", 0))
                        away_score = int(score.get("FS", {}).get("G", 0))
                    else:
                        home_score = 0
                        away_score = 0
                    
                    minute = int(event.get("LE", 0))
                    league = event.get("L", "Live")
                    
                    # Skip virtual/esports
                    league_lower = league.lower()
                    if any(term in league_lower for term in ["fifa", "esoccer", "virtual", "cyber"]):
                        continue
                    
                    # Extract odds
                    odds = {}
                    markets = event.get("E", [])
                    for market in markets:
                        market_type = market.get("T", 0)
                        outcomes = market.get("E", [])
                        
                        if market_type == 1 and len(outcomes) >= 3:  # 1X2
                            odds["home_win"] = float(outcomes[0].get("C", 0))
                            odds["draw"] = float(outcomes[1].get("C", 0))
                            odds["away_win"] = float(outcomes[2].get("C", 0))
                        elif market_type == 17:  # Total
                            for o in outcomes:
                                name = str(o.get("N", "")).lower()
                                if "2.5" in name:
                                    if "over" in name or o.get("T") == 1:
                                        odds["over_25"] = float(o.get("C", 0))
                                    else:
                                        odds["under_25"] = float(o.get("C", 0))
                        elif market_type == 40:  # BTTS
                            for o in outcomes:
                                name = str(o.get("N", "")).lower()
                                if "yes" in name:
                                    odds["btts_yes"] = float(o.get("C", 0))
                    
                    game = GameEvent(
                        id=f"1xbet_{game_id}",
                        home_team=home,
                        away_team=away,
                        home_score=home_score,
                        away_score=away_score,
                        minute=minute,
                        league=league,
                        odds=odds,
                        raw_data=event
                    )
                    games.append(game)
                    
                except Exception as e:
                    logger.debug(f"Event parse error: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"API response parse error: {e}")
        
        return games
    
    async def _scrape_dom_games(self) -> List[GameEvent]:
        """Fallback: scrape games from DOM"""
        games = []
        
        if not self.page:
            return games
        
        try:
            # Common 1xbet game selectors
            selectors = [
                ".liveLine__game",
                ".live-event",
                "[class*='gameRow']",
                "[class*='event-']",
                ".cm-live-_events__item",
                ".c-events__item",
                "[class*='live-game']",
                ".sport-event",
                ".eventMatch",
                "div[class*='event']",
            ]
            
            game_elements = []
            for sel in selectors:
                try:
                    game_elements = await self.page.query_selector_all(sel)
                    if game_elements:
                        break
                except:
                    continue
            
            for el in game_elements[:30]:  # Limit to 30 games
                try:
                    # Extract team names
                    home_el = await el.query_selector(".team-name:first-child, [class*='home']")
                    away_el = await el.query_selector(".team-name:last-child, [class*='away']")
                    
                    if not home_el or not away_el:
                        continue
                    
                    home = (await home_el.inner_text()).strip()
                    away = (await away_el.inner_text()).strip()
                    
                    if not home or not away:
                        continue
                    
                    # Score
                    score_el = await el.query_selector(".score, [class*='score']")
                    score_text = (await score_el.inner_text()).strip() if score_el else "0:0"
                    parts = score_text.replace("-", ":").split(":")
                    home_score = int(parts[0]) if parts else 0
                    away_score = int(parts[1]) if len(parts) > 1 else 0
                    
                    # Time
                    time_el = await el.query_selector(".time, [class*='time']")
                    minute = 0
                    if time_el:
                        time_text = (await time_el.inner_text()).strip()
                        import re
                        minute = int(re.sub(r"\D", "", time_text)) if time_text else 0
                    
                    # Odds (first few)
                    odds_els = await el.query_selector_all(".odd, [class*='odd']")
                    odds = {}
                    odds_vals = []
                    for oe in odds_els[:6]:
                        try:
                            txt = (await oe.inner_text()).strip()
                            val = float(txt)
                            odds_vals.append(val)
                        except:
                            pass
                    
                    if len(odds_vals) >= 3:
                        odds["home_win"] = odds_vals[0]
                        odds["draw"] = odds_vals[1]
                        odds["away_win"] = odds_vals[2]
                    if len(odds_vals) >= 5:
                        odds["over_25"] = odds_vals[3]
                        odds["under_25"] = odds_vals[4]
                    
                    game = GameEvent(
                        id=f"1xbet_dom_{hash(home + away)}",
                        home_team=home,
                        away_team=away,
                        home_score=home_score,
                        away_score=away_score,
                        minute=minute,
                        odds=odds
                    )
                    games.append(game)
                    
                except Exception as e:
                    logger.debug(f"DOM element parse error: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"DOM scraping failed: {e}")
        
        return games
    
    async def place_bet(self, game_id: str, bet_type: str, stake: float, odds: float) -> bool:
        """
        Attempt to place a bet on 1xbet.
        This navigates the page to the game and tries to place the bet.
        """
        if not self.page:
            logger.error("No page available for betting")
            return False
        
        try:
            # Navigate to game
            game_url = f"https://1xbet.com/en/line/football/event/{game_id}"
            await self.page.goto(game_url, wait_until="networkidle", timeout=15000)
            await self.page.wait_for_timeout(2000)
            
            # Find the bet selector based on bet type
            bet_selectors = {
                "home_win": ["[data-outcome='1']", ".odds-home", ".home-win"],
                "draw": ["[data-outcome='X']", ".odds-draw", ".draw"],
                "away_win": ["[data-outcome='2']", ".odds-away", ".away-win"],
                "over_25": ["[data-market*='over'][data-value='2.5']", ".over-25"],
                "under_25": ["[data-market*='under'][data-value='2.5']", ".under-25"],
            }
            
            selectors = bet_selectors.get(bet_type, [])
            
            # Click the odds
            clicked = False
            for sel in selectors:
                try:
                    await self.page.click(sel, timeout=3000)
                    clicked = True
                    break
                except:
                    continue
            
            if not clicked:
                logger.warning(f"Could not find bet button for {bet_type}")
                return False
            
            await self.page.wait_for_timeout(1000)
            
            # Fill stake
            stake_selectors = ["input.betslip-amount", "input[name='amount']", "[class*='stake'] input"]
            filled = False
            for sel in stake_selectors:
                try:
                    await self.page.fill(sel, str(int(stake)))
                    filled = True
                    break
                except:
                    continue
            
            if not filled:
                logger.warning("Could not fill stake amount")
                return False
            
            await self.page.wait_for_timeout(500)
            
            # Click place bet
            place_selectors = ["button.place-bet", "button[type='submit']", "[class*='place'] button"]
            for sel in place_selectors:
                try:
                    await self.page.click(sel, timeout=3000)
                    await self.page.wait_for_timeout(2000)
                    logger.info(f"✅ Bet placed: {bet_type} @ {odds} for {stake} KES")
                    return True
                except:
                    continue
            
            logger.warning("Could not find place bet button")
            return False
            
        except Exception as e:
            logger.error(f"Bet placement failed: {e}")
            return False
    
    async def get_balance(self) -> Optional[float]:
        """Get account balance from 1xbet"""
        if not self.page:
            return None
        
        try:
            balance = await self.page.evaluate("""
                () => {
                    // Try to find balance element
                    const selectors = [
                        '.balance-amount',
                        '.user-balance',
                        '[class*="balance"]',
                        '.header-balance'
                    ];
                    
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const text = el.textContent;
                            const num = parseFloat(text.replace(/[^0-9.]/g, ''));
                            if (!isNaN(num)) return num;
                        }
                    }
                    return null;
                }
            """)
            return float(balance) if balance else None
        except Exception as e:
            logger.debug(f"Could not get balance: {e}")
            return None
    
    async def login(self, username: str, password: str) -> bool:
        """Login to 1xbet"""
        if not self.page:
            return False
        
        try:
            await self.page.goto("https://1xbet.com/en/login", wait_until="networkidle")
            await self.page.wait_for_timeout(2000)
            
            # Fill credentials
            await self.page.fill("input[name='login'], input[type='email']", username)
            await self.page.fill("input[name='password']", password)
            
            # Click login
            await self.page.click("button[type='submit']")
            await self.page.wait_for_timeout(3000)
            
            # Check if logged in
            balance = await self.get_balance()
            if balance:
                logger.info("Login successful")
                return True
            
            # Check for 2FA
            content = await self.page.content()
            if "authenticator" in content.lower() or "sms" in content.lower():
                logger.warning("2FA required")
            
            return False
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def _fire_connection_change(self, connected: bool, message: str):
        """Fire connection change callback"""
        if self.on_connection_change:
            try:
                self.on_connection_change(connected, message)
            except Exception as e:
                logger.error(f"Connection callback error: {e}")
    
    async def disconnect(self):
        """Disconnect from browser"""
        try:
            if self.playwright:
                await self.playwright.stop()
        except:
            pass
        
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self._is_connected = False
        self._fire_connection_change(False, "Disconnected")
    
    @property
    def is_connected(self) -> bool:
        return self._is_connected
    
    @property
    def connection_method(self) -> Optional[str]:
        return self._connection_method
    
    @property
    def current_url(self) -> Optional[str]:
        return self.page.url if self.page else None


# Singleton
_browser_agent: Optional[BrowserAgent] = None

def get_browser_agent(window_manager=None) -> BrowserAgent:
    """Get the global browser agent instance"""
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent(window_manager)
    return _browser_agent
