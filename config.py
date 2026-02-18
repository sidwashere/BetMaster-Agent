"""
config.py - Central configuration for BetMaster Agent
"""

# ===============================================
# STRATEGY MODE
# ===============================================
# "conservative" = 85%+ confidence, 8%+ edge, max 3 bets/day
# "aggressive" = 70%+ confidence, 5%+ edge, max 10 bets/day
STRATEGY_MODE = "conservative"

# ===============================================
# STRATEGY SETTINGS
# ===============================================
CONSERVATIVE_SETTINGS = {
    "min_confidence": 85,
    "min_edge": 0.08,  # 8%
    "max_daily_bets": 3,
    "max_stake": 500,
    "min_odds": 1.4,
    "max_odds": 4.0,
    "kelly_fraction": 0.20,
    "max_hourly_bets": 1,
    "min_minute": 15,
    "max_minute": 75,
}

AGGRESSIVE_SETTINGS = {
    "min_confidence": 70,
    "min_edge": 0.05,  # 5%
    "max_daily_bets": 10,
    "max_stake": 1000,
    "min_odds": 1.2,
    "max_odds": 6.0,
    "kelly_fraction": 0.30,
    "max_hourly_bets": 3,
    "min_minute": 5,
    "max_minute": 85,
}

# ===============================================
# AUTO-LOGIN
# ===============================================
AUTO_LOGIN_ENABLED = False

# ===============================================
# STAKE CONFIGURATION (in KES)
# Format: { min_confidence: (min_stake, max_stake) }
# ===============================================
STAKE_CONFIG = {
    90: (300, 500),   # 90%+ confidence  → 300-500 KES
    75: (200, 300),   # 75-89% confidence → 200-300 KES
    60: (150, 200),   # 60-74% confidence → 150-200 KES
    0:  (100, 150),   # <60% confidence   → 100-150 KES
}

# Minimum confidence % to even display a bet recommendation
MIN_DISPLAY_CONFIDENCE = 50

# Auto-bet only fires above this confidence level
AUTO_BET_THRESHOLD = 85

# Kelly Criterion fraction (0.25 = quarter Kelly, conservative)
KELLY_FRACTION = 0.25

# Maximum single bet size regardless of Kelly output (KES)
MAX_BET_KES = 1000

# Daily loss limit - stops auto-betting if reached (KES)
DAILY_LOSS_LIMIT = 3000

# ===============================================
# BETTING SITES
# ===============================================
ENABLED_SITES = [
    "1xbet",
    "sportpesa",
]

SITE_URLS = {
    "1xbet": "https://1xbet.com/en/live/football",
    "sportpesa": "https://www.sportpesa.com/games/live",
    "betway": "https://betway.co.ke/sport/live/football",
    "odibets": "https://odibets.com/live",
}

# ===============================================
# BROWSER SETTINGS
# ===============================================
# Connect to existing browser instead of launching new one
BROWSER_CONNECT_TO_EXISTING = True
BROWSER_HEADLESS = False

# CDP port for connecting to existing browser
CHROME_DEBUG_PORT = 9222

# ===============================================
# AI / OLLAMA SETTINGS
# ===============================================
OLLAMA_ENABLED = True
OLLAMA_MODEL = "gemma3:1b"  # User confirmed this is running
OLLAMA_URL = "http://localhost:11434"

# ===============================================
# API KEYS
# ===============================================
# The Odds API - Free tier available at https://the-odds-api.com
THE_ODDS_API_KEY = "2dc9ef12536b609e01be1b97b06ea970"  # User provided

# Football-data.org - Free API for team stats
# Get key at https://www.football-data.org/client/register
FOOTBALL_DATA_API_KEY = "YOUR_API_KEY_HERE"

# API-Football (RapidAPI) - Optional
API_FOOTBALL_KEY = ""

# ===============================================
# DATA REFRESH SETTINGS
# ===============================================
# Refresh interval for live data (seconds)
REFRESH_INTERVAL = 60

# Cache TTL for various data sources
STATS_CACHE_TTL = 3600  # 1 hour
ODDS_CACHE_TTL = 30      # 30 seconds

# ===============================================
# BETTING SITES CREDENTIALS
# ===============================================
SITE_CREDENTIALS = {
    "1xbet": {
        "username": "",
        "password": "",
    },
    "sportpesa": {
        "username": "",
        "password": "",
    },
}

# ===============================================
# DATABASE
# ===============================================
DB_PATH = "data/bets.db"

# ===============================================
# UI SETTINGS
# ===============================================
UI_THEME = "dark"
UI_COLOR = "blue"

# ===============================================
# ANALYSIS WEIGHTS (must sum to 1.0)
# ===============================================
ANALYSIS_WEIGHTS = {
    "poisson_model": 0.35,
    "value_edge":    0.25,
    "recent_form":   0.20,
    "head_to_head":  0.10,
    "home_advantage": 0.10,
}

# ===============================================
# REPORTING & NOTIFICATIONS
# ===============================================
ENABLE_DESKTOP_NOTIFICATIONS = True

# Session report settings
REPORT_SESSION_PNL = True
REPORT_DAILY_SUMMARY = True

# ===============================================
# RISK MANAGEMENT
# ===============================================
# Maximum exposure per game (KES)
MAX_EXPOSURE_PER_GAME = 1000

# Maximum concurrent open bets
MAX_OPEN_BETS = 5

# Cool-down period after a loss (minutes)
LOSS_COOLDOWN = 10

# ===============================================
# LOGGING
# ===============================================
LOG_LEVEL = "INFO"
LOG_TO_FILE = True
LOG_FILE = "logs/betmaster.log"
