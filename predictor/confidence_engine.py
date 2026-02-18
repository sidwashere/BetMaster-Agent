"""
predictor/confidence_engine.py
Combines Poisson model + value detection + form data into
a final confidence score and bet recommendation.

Kelly Criterion implementation for stake sizing.
Reference: en.wikipedia.org/wiki/Kelly_criterion
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from scraper.base_scraper import LiveGame
from analyzer.poisson_model import PoissonModel
from analyzer.ollama_analyzer import OllamaAnalyzer
from analyzer.news_sentiment import NewsSentiment
import asyncio
import config

logger = logging.getLogger(__name__)


@dataclass
class BetRecommendation:
    """A single bet recommendation with all supporting data."""
    game: LiveGame
    bet_type: str               # 'home', 'draw', 'away', 'over_25', 'under_25', 'btts', 'btts_no'
    bet_label: str              # Human-readable: "Home Win", "Over 2.5 Goals", etc.
    
    # Core metrics
    model_probability: float    # Our Poisson model's estimated probability (0-1)
    implied_probability: float  # Bookmaker's implied probability (0-1)
    edge: float                 # edge = model_prob - implied_prob (positive = value bet)
    odds: float                 # The decimal odds being bet at
    
    # Confidence
    confidence: float           # 0-100 final confidence score
    confidence_label: str       # "Very High", "High", "Medium", "Low"
    
    # Stake recommendation
    recommended_stake: float    # KES amount to bet
    kelly_fraction: float       # Kelly criterion fraction
    
    # Supporting analysis
    home_xg: float = 0.0
    away_xg: float = 0.0
    predicted_score: str = ""
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def is_auto_bettable(self) -> bool:
        return self.confidence >= config.AUTO_BET_THRESHOLD and self.edge > 0


BET_LABELS = {
    "home": "Home Win",
    "draw": "Draw",
    "away": "Away Win",
    "over_25": "Over 2.5 Goals",
    "under_25": "Under 2.5 Goals",
    "over_35": "Over 3.5 Goals",
    "under_35": "Under 3.5 Goals",
    "btts": "Both Teams to Score",
    "btts_no": "Both Teams NOT to Score",
}


class ConfidenceEngine:
    """
    Core analysis engine.
    
    For each live game + odds, produces ranked bet recommendations
    with confidence scores and stake sizes.
    """

    def __init__(self):
        self.poisson = PoissonModel()
        self.ollama = OllamaAnalyzer(model_name=config.OLLAMA_MODEL, base_url=config.OLLAMA_URL)
        self.sentiment = NewsSentiment()
        self._form_cache: Dict[str, dict] = {}   # Team recent form cache

    async def analyze_game(self, game: LiveGame) -> List[BetRecommendation]:
        """
        Full analysis of a live game.
        Returns list of BetRecommendation sorted by confidence (highest first).
        """
        # ... logic ...
        recommendations = []

        # Skip very late games (unreliable in-play odds)
        # Allow pre-match (minute=0) and live games
        if game.minute > 85:
            logger.debug(f"Skipping {game.home_team} vs {game.away_team} - game too late (minute {game.minute})")
            return []
        
        logger.debug(f"Analyzing: {game.home_team} vs {game.away_team}, minute={game.minute}")

        # Get Poisson probabilities
        probs = self.poisson.get_all_probabilities(
            game.home_team, game.away_team,
            game.home_score, game.away_score, game.minute
        )

        predicted_h, predicted_a = self.poisson.get_most_likely_final_score(
            game.home_team, game.away_team,
            game.home_score, game.away_score, game.minute
        )
        predicted_score = f"{predicted_h}-{predicted_a}"

        # Get Sentiment/Momentum Score
        # We assume attacks/dangerous_attacks might be available in game object (if scraper provides it)
        # For now, we use a simple heuristic or the mock sentiment
        momentum_msg = self.sentiment.analyze_momentum(10, 5) # Placeholder values until scraper provides live stats

        # Evaluate each available market
        markets_to_check = [
            ("home", game.odds_home_win, probs.get("home_win", 0)),
            ("draw", game.odds_draw, probs.get("draw", 0)),
            ("away", game.odds_away_win, probs.get("away_win", 0)),
            ("over_25", game.odds_over_25, probs.get("over_25", 0)),
            ("under_25", game.odds_under_25, probs.get("under_25", 0)),
            ("btts", game.odds_btts_yes, probs.get("btts", 0)),
            ("btts_no", game.odds_btts_no, probs.get("btts_no", 0)),
        ]

        # Prepare AI Analysis Promise (fire once per game if needed, or lazily)
        # We only query AI if we find at least one potential bet to avoid spamming Ollama
        potential_bet_found = False
        for _, odds, model_prob in markets_to_check:
            if odds and odds > 1.0 and model_prob > 0.4: # Only if reasonable probability
                 potential_bet_found = True
                 break
        
        ai_analysis = {}
        if potential_bet_found and self.ollama.is_available:
             # Basic state for AI
             game_state = {
                 "home_team": game.home_team,
                 "away_team": game.away_team,
                 "home_score": game.home_score,
                 "away_score": game.away_score,
                 "minute": game.minute,
                 "odds_home_win": game.odds_home_win,
                 "odds_draw": game.odds_draw,
                 "odds_away_win": game.odds_away_win,
             }
             # Wait for AI analysis (or we could parallelize this outside)
             ai_analysis = await self.ollama.analyze_game(game_state)


        for bet_type, odds, model_prob in markets_to_check:
            if not odds or odds <= 1.0 or model_prob <= 0:
                continue

            implied_prob = 1.0 / odds
            edge = model_prob - implied_prob

            # Allow slightly negative edge bets too (for variety with default ratings)
            if edge < -0.15:
                continue

            # Kelly Criterion
            kelly = self._kelly_fraction(model_prob, odds)
            
            # Confidence score (weighted)
            confidence = self._calculate_confidence(
                model_prob, implied_prob, edge, kelly,
                game, bet_type, probs
            )

            # --- AI ADJUSTMENT ---
            # Skip AI for now - Ollama is timing out
            # TODO: Re-enable when Ollama is faster
            ai_reasons = []
            # if ai_analysis and hasattr(ai_analysis, 'recommended_bet'):
                # If AI recommends this specific bet type, boost confidence
                ai_rec = ai_analysis.recommended_bet.lower() if ai_analysis.recommended_bet else ""
                ai_conf = ai_analysis.confidence
                ai_reason = ai_analysis.reasoning
                
                # Simple string matching for AI recommendation
                match_ai = False
                if "home" in ai_rec and bet_type == "home": match_ai = True
                elif "away" in ai_rec and bet_type == "away": match_ai = True
                elif "over" in ai_rec and bet_type == "over_25": match_ai = True
                
                if match_ai:
                    # boost confidence by up to 15 points based on AI confidence
                    boost = (ai_conf / 100.0) * 15
                    confidence = min(100, confidence + boost)
                    ai_reasons.append(f"🤖 AI supports this: {ai_reason}")
                elif ai_rec != "none" and ai_rec != "":
                     # AI suggests something else
                     pass
            
            if confidence < config.MIN_DISPLAY_CONFIDENCE:
                continue

            # Stake recommendation
            stake = self._recommend_stake(confidence, kelly)

            # Build reasons list
            reasons, warnings = self._build_reasoning(
                game, bet_type, model_prob, implied_prob, edge, probs, confidence
            )
            reasons.extend(ai_reasons)
            reasons.append(f"Momentum: {momentum_msg}")

            rec = BetRecommendation(
                game=game,
                bet_type=bet_type,
                bet_label=BET_LABELS.get(bet_type, bet_type),
                model_probability=round(model_prob, 4),
                implied_probability=round(implied_prob, 4),
                edge=round(edge, 4),
                odds=odds,
                confidence=round(confidence, 1),
                confidence_label=self._confidence_label(confidence),
                recommended_stake=stake,
                kelly_fraction=round(kelly, 4),
                home_xg=probs.get("home_xg", 0),
                away_xg=probs.get("away_xg", 0),
                predicted_score=predicted_score,
                reasons=reasons,
                warnings=warnings,
            )
            recommendations.append(rec)

        # Sort: highest confidence first
        recommendations.sort(key=lambda r: (r.confidence, r.edge), reverse=True)
        return recommendations[:5]

    def _kelly_fraction(self, prob: float, odds: float) -> float:
        """
        Kelly Criterion: f* = (bp - q) / b
        b = odds - 1 (net odds)
        p = our win probability
        q = 1 - p (loss probability)
        
        Using fractional Kelly (config.KELLY_FRACTION) for safety.
        """
        b = odds - 1
        p = prob
        q = 1 - p
        
        if b <= 0:
            return 0.0
        
        kelly = (b * p - q) / b
        kelly = max(0, kelly)  # No negative Kelly (don't bet)
        kelly *= config.KELLY_FRACTION  # Apply fraction for conservatism
        
        return min(kelly, 0.15)  # Cap at 15% of bankroll per bet

    def _calculate_confidence(
        self, model_prob: float, implied_prob: float, edge: float,
        kelly: float, game: LiveGame, bet_type: str, probs: dict
    ) -> float:
        """
        Weighted confidence score combining multiple signals.
        
        Components:
        1. Model probability strength (35%)
        2. Value edge size (25%)
        3. Game state consistency (20%)
        4. Odds reasonableness (10%)
        5. Time factor (10%)
        """
        scores = {}

        # 1. Model probability: how strongly does our model back this?
        # 50% model prob → 0 confidence boost; 90% → high confidence
        prob_score = max(0, (model_prob - 0.45) / 0.55) * 100
        scores["model"] = min(100, prob_score) * 0.35

        # 2. Value edge: positive edge boosts confidence
        edge_score = max(0, min(1, (edge + 0.05) / 0.25)) * 100
        scores["edge"] = edge_score * 0.25

        # 3. Game state: is current score consistent with prediction?
        state_score = self._game_state_score(game, bet_type, probs)
        scores["state"] = state_score * 0.20

        # 4. Odds reasonableness: avoid extreme odds (1.1 or 50.0+)
        odds = 1.0 / implied_prob if implied_prob > 0 else 100
        if 1.3 <= odds <= 5.0:
            odds_score = 100
        elif 1.1 <= odds < 1.3 or 5.0 < odds <= 8.0:
            odds_score = 60
        else:
            odds_score = 20
        scores["odds"] = odds_score * 0.10

        # 5. Time factor: avoid last 5 minutes (chaotic) and first 10
        minute = game.minute
        if 15 <= minute <= 75:
            time_score = 100
        elif 10 <= minute < 15 or 75 < minute <= 80:
            time_score = 70
        else:
            time_score = 30
        scores["time"] = time_score * 0.10

        total = sum(scores.values())
        return max(0, min(100, total))

    def _game_state_score(self, game: LiveGame, bet_type: str, probs: dict) -> float:
        """
        Score based on whether current game state supports the bet.
        """
        h = game.home_score
        a = game.away_score
        total = h + a

        if bet_type == "over_25":
            # Already at 2 goals with 30+ min remaining = very good
            if total >= 2 and game.minute < 60:
                return 90
            elif total >= 1:
                return 70
            elif probs.get("home_xg", 0) + probs.get("away_xg", 0) > 1.2:
                return 60
            return 40

        elif bet_type == "under_25":
            # 0-0 at 65 min = good under bet
            if total == 0 and game.minute > 55:
                return 88
            elif total <= 1 and game.minute > 40:
                return 70
            elif total >= 3:
                return 5
            return 50

        elif bet_type in ("home", "away", "draw"):
            # Consistent with scoreline
            diff = h - a
            if bet_type == "home" and diff >= 1:
                return 80
            elif bet_type == "away" and diff <= -1:
                return 80
            elif bet_type == "draw" and diff == 0:
                return 75
            elif abs(diff) <= 1:
                return 55
            return 30

        elif bet_type == "btts":
            if h > 0 and a > 0:
                return 95
            elif (h > 0 or a > 0) and game.minute < 65:
                return 65
            return 40

        elif bet_type == "btts_no":
            if h == 0 and a == 0 and game.minute > 50:
                return 85
            return 40

        return 50

    def _recommend_stake(self, confidence: float, kelly: float) -> float:
        """
        Determine stake amount in KES based on confidence level.
        Uses config.STAKE_CONFIG thresholds.
        """
        for min_conf in sorted(config.STAKE_CONFIG.keys(), reverse=True):
            if confidence >= min_conf:
                min_s, max_s = config.STAKE_CONFIG[min_conf]
                # Scale within range based on confidence level above threshold
                next_threshold = min_conf + 15
                frac = min(1.0, (confidence - min_conf) / 15)
                stake = min_s + (max_s - min_s) * frac
                return min(round(stake, -1), config.MAX_BET_KES)  # Round to nearest 10

        return config.STAKE_CONFIG[0][0]  # Minimum stake

    def _confidence_label(self, confidence: float) -> str:
        if confidence >= 85:
            return "🔥 Very High"
        elif confidence >= 70:
            return "✅ High"
        elif confidence >= 55:
            return "⚡ Medium"
        else:
            return "⚠️ Low"

    def _build_reasoning(
        self, game: LiveGame, bet_type: str,
        model_prob: float, implied_prob: float, edge: float,
        probs: dict, confidence: float
    ) -> Tuple[List[str], List[str]]:
        """Build human-readable reasons and warnings for the bet."""
        reasons = []
        warnings = []

        pct = lambda p: f"{p*100:.1f}%"

        reasons.append(f"Model win probability: {pct(model_prob)} vs bookmaker's {pct(implied_prob)}")

        if edge > 0:
            reasons.append(f"Positive value edge: +{pct(edge)} (we have the mathematical edge)")
        
        h_xg = probs.get("home_xg", 0)
        a_xg = probs.get("away_xg", 0)
        reasons.append(f"Remaining xG: {game.home_team} {h_xg:.2f} | {game.away_team} {a_xg:.2f}")

        # Game state reasoning
        h = game.home_score
        a = game.away_score
        total = h + a

        if bet_type == "over_25":
            if total >= 2:
                reasons.append(f"Already {total} goals scored - over 2.5 already achieved or very near")
            elif h_xg + a_xg > 1.0:
                reasons.append(f"High-scoring game expected: combined xG = {h_xg+a_xg:.2f}")

        elif bet_type == "under_25":
            if total == 0 and game.minute > 50:
                reasons.append(f"Goalless at minute {game.minute} - under 2.5 looks likely")
            if h_xg + a_xg < 0.8:
                reasons.append(f"Low remaining xG ({h_xg+a_xg:.2f}) supports under bet")

        elif bet_type == "btts":
            if h > 0 and a > 0:
                reasons.append("Both teams have already scored ✓")
            reasons.append(f"Home xG {h_xg:.2f}, Away xG {a_xg:.2f} - both likely to score")

        # Warnings
        if game.minute > 75:
            warnings.append(f"⚠️ Only {90-game.minute} minutes remaining - odds can be volatile")
        if edge < 0:
            warnings.append("⚠️ Slight negative edge - bookmaker has marginal advantage")
        if confidence < 60:
            warnings.append("⚠️ Low confidence - consider skipping or minimum stake")

        return reasons, warnings

    async def batch_analyze(self, games: List[LiveGame]) -> Dict[str, List[BetRecommendation]]:
        """
        Analyze all games concurrently.
        """
        results = {}
        try:
            # Create tasks for all games
            tasks = [self.analyze_game(game) for game in games]
            
            # Run all analysis in parallel
            all_recs = await asyncio.gather(*tasks, return_exceptions=True)
            
            for game, recs in zip(games, all_recs):
                if isinstance(recs, Exception):
                    logger.error(f"Error analyzing {game.home_team}: {recs}")
                    continue
                if recs:
                    results[game.game_id] = recs
                    logger.info(f"Game {game.home_team} vs {game.away_team}: {len(recs)} recommendations")
                else:
                    logger.debug(f"Game {game.home_team} vs {game.away_team}: 0 recommendations")
        except Exception as e:
            logger.error(f"Batch analyze error: {e}")
        return results
