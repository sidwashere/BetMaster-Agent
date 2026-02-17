"""
config.py - Central configuration for SoccerBot
Edit this file to customize your experience.
"""

# ─────────────────────────────────────────────
# STAKE CONFIGURATION (in KES)
# Format: { min_confidence: (min_stake, max_stake) }
# ─────────────────────────────────────────────
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

# ─────────────────────────────────────────────
# BETTING SITES
# Add/remove sites here - scrapers must exist in scraper/
# ─────────────────────────────────────────────
ENABLED_SITES = [
    "1xbet",
    "sportpesa",
    # "betway",    # add scraper/site_betway.py to enable
    # "odibets",   # add scraper/site_odibets.py to enable
]

SITE_URLS = {
    "1xbet": "https://1xbet.com/en/live/football",
    "sportpesa": "https://www.sportpesa.com/games/live",
    "betway": "https://betway.co.ke/sport/live/football",
    "odibets": "https://odibets.com/live",
}

# AI / Ollama Settings
OLLAMA_ENABLED = True
OLLAMA_MODEL = "llama3" # Ensure you 'ollama pull llama3'
OLLAMA_URL = "http://localhost:11434"

# ─────────────────────────────────────────────
# API SETTINGS
# ─────────────────────────────────────────────
# Free API - get key at https://www.football-data.org/client/register
FOOTBALL_DATA_API_KEY = "YOUR_API_KEY_HERE"

# Free alternative (no key needed): api.football-data.org v2 limited
# Or use: https://rapidapi.com/api-sports/api/api-football (freemium)
API_FOOTBALL_KEY = ""  # RapidAPI key for api-football (optional)

# Refresh interval for live data (seconds)
REFRESH_INTERVAL = 60

# ─────────────────────────────────────────────
# BROWSER AUTOMATION (for auto-betting)
# ─────────────────────────────────────────────
BROWSER_HEADLESS = False  # Set True to hide browser window

# Your login credentials per site (stored locally, never shared)
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

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
DB_PATH = "data/bets.db"

# ─────────────────────────────────────────────
# UI SETTINGS
# ─────────────────────────────────────────────
UI_THEME = "dark"   # "dark" or "light"
UI_COLOR = "blue"   # "blue", "green", "dark-blue"

# ─────────────────────────────────────────────
# ANALYSIS WEIGHTS (must sum to 1.0)
# ─────────────────────────────────────────────
ANALYSIS_WEIGHTS = {
    "poisson_model": 0.35,
    "value_edge":    0.25,
    "recent_form":   0.20,
    "head_to_head":  0.10,
    "home_advantage": 0.10,
}
