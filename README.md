# ⚽ SoccerBot - AI-Powered Betting Desktop Agent

A Python desktop agent that scrapes live football games from betting sites, applies statistical models (Poisson, Kelly Criterion, xG), and optionally auto-places bets through browser automation.

---

## 🧠 Architecture

```
soccerbot/
├── main.py                 # Entry point & desktop UI (CustomTkinter)
├── config.py               # All configurable settings
├── scraper/
│   ├── base_scraper.py     # Abstract scraper class
│   ├── site_1xbet.py       # 1xbet live game scraper
│   ├── site_sportpesa.py   # SportPesa live game scraper
│   └── scraper_manager.py  # Manages all scrapers
├── analyzer/
│   ├── poisson_model.py    # Goal prediction via Poisson distribution
│   ├── value_finder.py     # Value bet detection (edge finder)
│   ├── stats_fetcher.py    # Historical stats from free APIs
│   └── live_analyzer.py   # Combines all analysis
├── predictor/
│   ├── confidence_engine.py  # Weighted confidence scoring
│   ├── bet_selector.py       # Picks best bet type per game
│   └── kelly_criterion.py    # Optimal stake sizing
├── bettor/
│   ├── auto_bettor.py      # Playwright browser automation
│   └── bet_history.py      # Track all bets (SQLite)
├── ui/
│   └── dashboard.py        # Main GUI dashboard
├── data/
│   └── team_stats.json     # Cached team stats
└── logs/
    └── bets.log
```

---

## 🚀 Quick Setup

### 1. Install dependencies
```bash
pip install customtkinter playwright aiohttp requests sqlite3 scipy numpy pandas
playwright install chromium
```

### 2. Get free API key (optional but improves accuracy)
- **football-data.org** → free tier: 10 req/min, has fixtures, standings, live scores
- Sign up at: https://www.football-data.org/client/register

### 3. Configure stakes & settings
Edit `config.py`:
```python
STAKE_CONFIG = {
    90: (300, 500),   # 90%+ confidence → stake between 300-500 KES
    75: (200, 300),   # 75-89% confidence → 200-300 KES
    60: (150, 200),   # 60-74% → 150-200 KES
    0:  (100, 150),   # <60% → 100-150 KES (minimum)
}
AUTO_BET_THRESHOLD = 85  # Only auto-bet at 85%+ confidence
```

### 4. Run
```bash
python main.py
```

---

## 🎯 Betting Algorithms Used

### 1. **Poisson Distribution** (Goal Prediction)
Models goals scored as a Poisson process using each team's attack/defense strength.
- Calculates probability of every scoreline
- Derives Over/Under 2.5, BTTS, exact score probabilities

### 2. **Value Bet Detection**
Compares our model probability vs bookmaker implied probability.
`edge = our_probability - bookmaker_implied_probability`
Only bets with positive edge (+EV) are flagged.

### 3. **Kelly Criterion** (Stake Sizing)
`kelly_fraction = (bp - q) / b`
where b = odds-1, p = our win probability, q = 1-p
Prevents over-betting and optimizes long-term growth.

### 4. **Confidence Scoring** (Weighted ensemble)
- Poisson model agreement: 35%
- Value edge size: 25%
- Recent form (last 5 games): 20%
- Head-to-head record: 10%
- Home/Away advantage: 10%

---

## ⚠️ Legal Notice
Auto-betting and web scraping may violate terms of service of betting sites.
Use responsibly and in accordance with your local laws. This is for educational purposes.

---

## 🔗 Related Open Source Projects Referenced
- [playwright-python](https://github.com/microsoft/playwright-python) - Browser automation
- [football-data-api](https://github.com/diegopiraquive/FootballData-Python) - Stats API wrapper
- [kelly-criterion implementations](https://github.com/topics/kelly-criterion) - Stake sizing
