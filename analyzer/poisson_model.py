"""
analyzer/poisson_model.py
Poisson Distribution model for football goal prediction.

This is the industry-standard approach used by quant betting firms.
Reference: Dixon-Coles (1997), "Modelling Association Football Scores"
GitHub refs:
  - github.com/Torvaney/regista (Stan-based Poisson football model)
  - github.com/tedbow/football-prediction (Python Poisson implementation)

Key insight: Goals in football follow a Poisson distribution.
Given expected goals (lambda), P(k goals) = e^(-λ) * λ^k / k!
"""

import math
import numpy as np
from scipy.stats import poisson
from typing import Tuple, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PoissonModel:
    """
    Predicts match outcomes using Poisson distribution on expected goals.
    
    Attack/defense strength ratings are derived from league averages.
    For live in-play adjustments, we factor in goals already scored.
    """

    # League average goals per game (home / away)
    # These are calibrated defaults; updated by stats_fetcher when API available
    DEFAULT_HOME_LAMBDA = 1.55
    DEFAULT_AWAY_LAMBDA = 1.15

    def __init__(self):
        # Team attack/defense strength relative to league average
        # Format: { "Team Name": {"attack": 1.2, "defense": 0.8} }
        self.team_ratings: Dict[str, Dict] = {}
        self.league_home_avg = self.DEFAULT_HOME_LAMBDA
        self.league_away_avg = self.DEFAULT_AWAY_LAMBDA

    def update_team_ratings(self, ratings: Dict):
        """Update team attack/defense ratings from stats fetcher."""
        self.team_ratings.update(ratings)

    def get_expected_goals(self, home_team: str, away_team: str) -> Tuple[float, float]:
        """
        Calculate expected goals (xG) for home and away teams.
        
        xG_home = league_home_avg * home_attack * away_defense
        xG_away = league_away_avg * away_attack * home_defense
        
        Returns: (home_xg, away_xg)
        """
        home_r = self.team_ratings.get(home_team, {"attack": 1.0, "defense": 1.0})
        away_r = self.team_ratings.get(away_team, {"attack": 1.0, "defense": 1.0})

        home_xg = self.league_home_avg * home_r["attack"] * away_r["defense"]
        away_xg = self.league_away_avg * away_r["attack"] * home_r["defense"]

        return home_xg, away_xg

    def adjust_for_live(
        self, home_xg: float, away_xg: float,
        home_score: int, away_score: int, minute: int
    ) -> Tuple[float, float]:
        """
        Adjust expected goals for in-play situation.
        
        Key factors:
        1. Remaining time fraction
        2. Current score influence (teams trailing attack more)
        3. Diminishing returns (tired legs in 80+)
        
        Returns adjusted (home_remaining_xg, away_remaining_xg)
        """
        if minute >= 90:
            return 0.0, 0.0

        remaining_fraction = (90 - minute) / 90

        # Scale xG by remaining time
        home_remaining = home_xg * remaining_fraction
        away_remaining = away_xg * remaining_fraction

        # Score influence: team losing by 1 attacks 20% more
        goal_diff = home_score - away_score
        if goal_diff < 0:  # Home team trailing
            home_remaining *= (1 + min(0.3, abs(goal_diff) * 0.15))
        elif goal_diff > 0:  # Away team trailing
            away_remaining *= (1 + min(0.3, goal_diff * 0.15))

        # Fatigue factor: slight reduction after 75 min
        if minute > 75:
            fatigue = 1 - ((minute - 75) / 90 * 0.1)
            home_remaining *= fatigue
            away_remaining *= fatigue

        return home_remaining, away_remaining

    def score_probability_matrix(
        self, home_xg: float, away_xg: float, max_goals: int = 7
    ) -> np.ndarray:
        """
        Build a matrix of P(home_goals=i, away_goals=j).
        Matrix[i][j] = probability of home scoring i, away scoring j.
        """
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                p_home = poisson.pmf(i, home_xg)
                p_away = poisson.pmf(j, away_xg)
                matrix[i][j] = p_home * p_away
        return matrix

    def get_all_probabilities(
        self,
        home_team: str,
        away_team: str,
        home_score: int = 0,
        away_score: int = 0,
        minute: int = 0,
    ) -> Dict[str, float]:
        """
        Main method: returns all bet-relevant probabilities.
        
        Returns dict with:
          - home_win, draw, away_win (1X2)
          - over_25, under_25 (total goals)
          - over_35, under_35
          - btts (both teams to score)
          - home_win_prob, draw_prob, away_win_prob (% values 0-100)
        """
        base_home_xg, base_away_xg = self.get_expected_goals(home_team, away_team)

        # Adjust for live match state
        if minute > 0:
            home_xg, away_xg = self.adjust_for_live(
                base_home_xg, base_away_xg, home_score, away_score, minute
            )
        else:
            home_xg, away_xg = base_home_xg, base_away_xg

        # Handle edge case: minimal remaining time
        if home_xg < 0.01 and away_xg < 0.01:
            # Game essentially over, go by current score
            return self._final_probabilities(home_score, away_score)

        # Build probability matrix
        matrix = self.score_probability_matrix(home_xg, away_xg)

        # Derive outcomes
        probs = {}

        # 1X2
        home_win_p = 0.0
        draw_p = 0.0
        away_win_p = 0.0
        total_goals_ge3 = 0.0
        total_goals_ge4 = 0.0
        btts_p = 0.0

        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                p = matrix[i][j]
                h_final = home_score + i
                a_final = away_score + j
                total = h_final + a_final

                if h_final > a_final:
                    home_win_p += p
                elif h_final == a_final:
                    draw_p += p
                else:
                    away_win_p += p

                if total >= 3:
                    total_goals_ge3 += p
                if total >= 4:
                    total_goals_ge4 += p
                if h_final > 0 and a_final > 0:
                    btts_p += p

        probs["home_win"] = round(home_win_p, 4)
        probs["draw"] = round(draw_p, 4)
        probs["away_win"] = round(away_win_p, 4)
        probs["over_25"] = round(total_goals_ge3, 4)
        probs["under_25"] = round(1 - total_goals_ge3, 4)
        probs["over_35"] = round(total_goals_ge4, 4)
        probs["under_35"] = round(1 - total_goals_ge4, 4)
        probs["btts"] = round(btts_p, 4)
        probs["btts_no"] = round(1 - btts_p, 4)

        # Store raw xG for UI display
        probs["home_xg"] = round(home_xg, 2)
        probs["away_xg"] = round(away_xg, 2)
        probs["base_home_xg"] = round(base_home_xg, 2)
        probs["base_away_xg"] = round(base_away_xg, 2)

        return probs

    def _final_probabilities(self, home_score: int, away_score: int) -> Dict[str, float]:
        """Return near-certain probabilities for end-of-game."""
        total = home_score + away_score
        return {
            "home_win": 0.97 if home_score > away_score else 0.01,
            "draw": 0.97 if home_score == away_score else 0.01,
            "away_win": 0.97 if away_score > home_score else 0.01,
            "over_25": 0.99 if total > 2 else 0.01,
            "under_25": 0.99 if total <= 2 else 0.01,
            "over_35": 0.99 if total > 3 else 0.01,
            "under_35": 0.99 if total <= 3 else 0.01,
            "btts": 0.99 if home_score > 0 and away_score > 0 else 0.01,
            "btts_no": 0.99 if home_score == 0 or away_score == 0 else 0.01,
            "home_xg": 0.0, "away_xg": 0.0,
            "base_home_xg": 0.0, "base_away_xg": 0.0,
        }

    def get_most_likely_final_score(
        self, home_team: str, away_team: str,
        home_score: int = 0, away_score: int = 0, minute: int = 0
    ) -> Tuple[int, int]:
        """Return the single most probable final score."""
        base_h, base_a = self.get_expected_goals(home_team, away_team)
        h_xg, a_xg = self.adjust_for_live(base_h, base_a, home_score, away_score, minute)
        
        best_p = 0
        best_score = (home_score, away_score)
        
        for add_h in range(6):
            for add_a in range(6):
                p = poisson.pmf(add_h, max(h_xg, 0.01)) * poisson.pmf(add_a, max(a_xg, 0.01))
                if p > best_p:
                    best_p = p
                    best_score = (home_score + add_h, away_score + add_a)
        
        return best_score
