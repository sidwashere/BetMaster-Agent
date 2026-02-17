"""
analyzer/stats_fetcher.py
Fetches historical team stats to calibrate the Poisson model.

Uses football-data.org (free tier: 10 req/min, no key needed for basic data)
and optional api-football.com (RapidAPI, freemium).

Reference: github.com/diegopiraquive/FootballData-Python
"""

import aiohttp
import asyncio
import json
import logging
import os
from typing import Dict, Optional
import config

logger = logging.getLogger(__name__)

CACHE_FILE = "data/team_stats.json"


class StatsFetcher:
    """
    Fetches and caches team attack/defense ratings.
    
    Ratings are computed from recent league data:
    - Goals scored relative to league avg → attack rating
    - Goals conceded relative to league avg → defense rating
    """

    # Supported league IDs (football-data.org codes)
    SUPPORTED_LEAGUES = {
        "Premier League": "PL",
        "La Liga": "PD",
        "Bundesliga": "BL1",
        "Serie A": "SA",
        "Ligue 1": "FL1",
        "Eredivisie": "DED",
        "Primeira Liga": "PPL",
        "Champions League": "CL",
    }

    def __init__(self):
        self.api_key = config.FOOTBALL_DATA_API_KEY
        self.base_url = "https://api.football-data.org/v4"
        self._cache: Dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self):
        """Load cached stats from disk."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r") as f:
                    self._cache = json.load(f)
                logger.info(f"Loaded {len(self._cache)} cached team records")
        except Exception as e:
            logger.warning(f"Could not load cache: {e}")
            self._cache = {}

    def _save_cache(self):
        """Save stats to disk cache."""
        try:
            os.makedirs("data", exist_ok=True)
            with open(CACHE_FILE, "w") as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    async def fetch_league_teams(self, league_code: str = "PL") -> Dict[str, dict]:
        """
        Fetch team stats for a league.
        Returns: { "Team Name": { "attack": float, "defense": float } }
        """
        headers = {}
        if self.api_key and self.api_key != "YOUR_API_KEY_HERE":
            headers["X-Auth-Token"] = self.api_key

        url = f"{self.base_url}/competitions/{league_code}/standings"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ratings = self._compute_ratings(data)
                        self._cache.update(ratings)
                        self._save_cache()
                        return ratings
                    elif resp.status == 403:
                        logger.warning("API key invalid or not set - using default ratings")
                    elif resp.status == 429:
                        logger.warning("API rate limit hit - using cached data")
        except Exception as e:
            logger.warning(f"Stats fetch error: {e}")

        return self._cache

    def _compute_ratings(self, standings_data: dict) -> Dict[str, dict]:
        """
        Compute attack/defense strength from standings data.
        
        attack_rating = goals_for / games_played / league_home_avg
        defense_rating = goals_against / games_played / league_away_avg
        """
        teams = []
        try:
            for group in standings_data.get("standings", []):
                if group.get("type") == "TOTAL":
                    teams = group.get("table", [])
                    break
        except Exception:
            return {}

        if not teams:
            return {}

        # League averages
        total_gf = sum(t.get("goalsFor", 0) for t in teams)
        total_ga = sum(t.get("goalsAgainst", 0) for t in teams)
        total_played = sum(t.get("playedGames", 1) for t in teams)

        if total_played == 0:
            return {}

        league_avg_scored = total_gf / len(teams) / max(teams[0].get("playedGames", 1), 1)
        league_avg_conceded = total_ga / len(teams) / max(teams[0].get("playedGames", 1), 1)

        ratings = {}
        for team in teams:
            name = team.get("team", {}).get("name", "")
            if not name:
                continue

            played = max(team.get("playedGames", 1), 1)
            gf = team.get("goalsFor", 0)
            ga = team.get("goalsAgainst", 0)

            attack = (gf / played) / max(league_avg_scored, 0.1)
            defense = (ga / played) / max(league_avg_conceded, 0.1)

            # defense: lower = better defense (concedes less than average)
            ratings[name] = {
                "attack": round(attack, 3),
                "defense": round(defense, 3),
                "games_played": played,
                "goals_for": gf,
                "goals_against": ga,
            }

        logger.info(f"Computed ratings for {len(ratings)} teams")
        return ratings

    async def fetch_all_leagues(self):
        """Fetch stats for all major leagues."""
        tasks = [
            self.fetch_league_teams(code)
            for code in list(self.SUPPORTED_LEAGUES.values())[:5]  # Limit API calls
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Total cached teams: {len(self._cache)}")

    def get_team_rating(self, team_name: str) -> dict:
        """
        Get rating for a team by name (fuzzy match).
        Returns default 1.0/1.0 if not found.
        """
        # Direct match
        if team_name in self._cache:
            return self._cache[team_name]

        # Fuzzy match: find closest team name
        team_lower = team_name.lower()
        for cached_name, rating in self._cache.items():
            cached_lower = cached_name.lower()
            if (team_lower in cached_lower or
                cached_lower in team_lower or
                self._similarity(team_lower, cached_lower) > 0.75):
                return rating

        return {"attack": 1.0, "defense": 1.0}

    def _similarity(self, a: str, b: str) -> float:
        """Simple Jaccard similarity for team name matching."""
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    def get_head_to_head_advantage(self, home_team: str, away_team: str) -> float:
        """
        Returns a score (0.0-1.0) for home team's historical H2H advantage.
        Uses cached data if available, otherwise returns neutral 0.5.
        
        Full H2H requires a paid API - this is a placeholder.
        Could be extended with: api-football.com /fixtures/headtohead endpoint
        """
        # TODO: Implement with paid API or scrape from flashscore.com
        return 0.5  # Neutral default

    def get_recent_form(self, team_name: str, last_n: int = 5) -> float:
        """
        Returns form score (0-1) based on last N results.
        1.0 = won all N games, 0.0 = lost all N games.
        
        Requires fixtures API - returns neutral 0.5 as default.
        """
        # TODO: Fetch from /teams/{id}/matches?status=FINISHED&limit=5
        # For now returns average (0.5 = neutral form)
        return 0.5
