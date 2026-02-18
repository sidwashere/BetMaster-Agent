"""
browser/__init__.py
Browser Agent Module for BetMaster
"""

from .window_manager import WindowManager, BrowserWindow, get_window_manager
from .agent import BrowserAgent, GameEvent, get_browser_agent
from .live_scraper import LiveScraper, LiveGame, get_live_scraper

__all__ = [
    "WindowManager",
    "BrowserWindow", 
    "get_window_manager",
    "BrowserAgent",
    "GameEvent",
    "get_browser_agent",
    "LiveScraper",
    "LiveGame",
    "get_live_scraper",
]
