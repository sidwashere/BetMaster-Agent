"""
bettor/strategic_bettor.py
Strategic betting engine with Conservative and Aggressive modes
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

import config

logger = logging.getLogger(__name__)


class StrategyMode(Enum):
    CONSERVATIVE = "conservative"
    AGGRESSIVE = "aggressive"


@dataclass
class StrategySettings:
    """Settings for a betting strategy"""
    min_confidence: int = 85
    min_edge: float = 0.08  # 8%
    max_daily_bets: int = 3
    max_stake: float = 500
    min_odds: float = 1.3
    max_odds: float = 5.0
    kelly_fraction: float = 0.25
    max_hourly_bets: int = 2
    min_minute: int = 10  # Don't bet in first 10 minutes
    max_minute: int = 80  # Don't bet after 80 minutes


# Strategy configurations
STRATEGIES = {
    StrategyMode.CONSERVATIVE: StrategySettings(
        min_confidence=85,
        min_edge=0.08,
        max_daily_bets=3,
        max_stake=500,
        min_odds=1.4,
        max_odds=4.0,
        kelly_fraction=0.20,
        max_hourly_bets=1,
        min_minute=15,
        max_minute=75
    ),
    StrategyMode.AGGRESSIVE: StrategySettings(
        min_confidence=70,
        min_edge=0.05,
        max_daily_bets=10,
        max_stake=1000,
        min_odds=1.2,
        max_odds=6.0,
        kelly_fraction=0.30,
        max_hourly_bets=3,
        min_minute=5,
        max_minute=85
    ),
}


@dataclass
class BetCandidate:
    """A potential bet that passed initial filters"""
    game_id: str
    home_team: str
    away_team: str
    bet_type: str
    bet_label: str
    odds: float
    stake: float
    confidence: float
    edge: float
    model_probability: float
    minute: int
    reasoning: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


class StrategicBettor:
    """
    Strategic betting engine with configurable strategies.
    Handles risk management, bet sizing, and timing.
    """
    
    def __init__(self, mode: StrategyMode = StrategyMode.CONSERVATIVE):
        self.mode = mode
        self.settings = STRATEGIES[mode]
        
        # Track placed bets
        self._today_bets: List[BetCandidate] = []
        self._hourly_bets: List[BetCandidate] = []
        self._last_reset: Optional[datetime] = None
        self._session_pnl: float = 0.0
        self._session_wins: int = 0
        self._session_losses: int = 0
        
        # Daily tracking
        self._daily_loss: float = 0.0
        self._daily_bet_count: int = 0
    
    @property
    def mode_name(self) -> str:
        return self.mode.value
    
    def set_strategy(self, mode: StrategyMode):
        """Switch betting strategy"""
        old_mode = self.mode
        self.mode = mode
        self.settings = STRATEGIES[mode]
        logger.info(f"Strategy changed: {old_mode.value} -> {mode.value}")
        logger.info(f"New settings: confidence>={self.settings.min%, edge>_confidence}={self.settings.min_edge*100}%")
    
    def evaluate_bet(
        self,
        game_id: str,
        home_team: str,
        away_team: str,
        bet_type: str,
        bet_label: str,
        odds: float,
        confidence: float,
        edge: float,
        model_probability: float,
        minute: int,
        reasoning: List[str] = None
    ) -> BetCandidate:
        """
        Evaluate if a bet meets our criteria.
        Returns BetCandidate if approved, None if rejected.
        """
        
        # Reset daily counters if needed
        self._check_daily_reset()
        self._check_hourly_reset()
        
        # Check daily loss limit
        if self._daily_loss <= -config.DAILY_LOSS_LIMIT:
            logger.warning(f"Daily loss limit reached: {self._daily_loss} KES")
            return None
        
        # Strategy filters
        if confidence < self.settings.min_confidence:
            logger.debug(f"Rejected: confidence {confidence} < {self.settings.min_confidence}")
            return None
        
        if edge < self.settings.min_edge:
            logger.debug(f"Rejected: edge {edge:.2%} < {self.settings.min_edge:.2%}")
            return None
        
        if odds < self.settings.min_odds or odds > self.settings.max_odds:
            logger.debug(f"Rejected: odds {odds} outside range")
            return None
        
        if minute < self.settings.min_minute:
            logger.debug(f"Rejected: minute {minute} < {self.settings.min_minute}")
            return None
        
        if minute > self.settings.max_minute:
            logger.debug(f"Rejected: minute {minute} > {self.settings.max_minute}")
            return None
        
        # Check daily bet limit
        if self._daily_bet_count >= self.settings.max_daily_bets:
            logger.warning(f"Daily bet limit reached: {self._daily_bet_count}")
            return None
        
        # Check hourly limit
        if len(self._hourly_bets) >= self.settings.max_hourly_bets:
            logger.warning(f"Hourly bet limit reached")
            return None
        
        # Calculate stake using Kelly Criterion
        stake = self._calculate_stake(odds, model_probability, confidence)
        
        # Ensure stake is within limits
        stake = min(stake, self.settings.max_stake)
        
        candidate = BetCandidate(
            game_id=game_id,
            home_team=home_team,
            away_team=away_team,
            bet_type=bet_type,
            bet_label=bet_label,
            odds=odds,
            stake=stake,
            confidence=confidence,
            edge=edge,
            model_probability=model_probability,
            minute=minute,
            reasoning=reasoning or []
        )
        
        logger.info(f"✅ Bet approved: {home_team} vs {away_team} | {bet_label} @ {odds} | "
                   f"Stake: {stake} KES | Confidence: {confidence}% | Edge: {edge:.2%}")
        
        return candidate
    
    def _calculate_stake(self, odds: float, probability: float, confidence: float) -> float:
        """
        Calculate stake using Kelly Criterion with adjustments.
        """
        # Base Kelly calculation
        b = odds - 1  # net odds
        p = probability
        q = 1 - p
        
        if b <= 0:
            return 0
        
        kelly = (b * p - q) / b
        
        # Apply Kelly fraction
        kelly *= self.settings.kelly_fraction
        
        # Scale by confidence (higher confidence = higher stake)
        confidence_factor = (confidence - 50) / 50  # 0 to 1 range
        kelly *= (0.5 + 0.5 * confidence_factor)
        
        # Convert to KES (assuming 10000 KES bankroll - make configurable)
        bankroll = 10000
        stake = kelly * bankroll
        
        # Ensure minimum stake
        stake = max(stake, 100)
        
        # Round to nearest 10
        stake = round(stake / 10) * 10
        
        return stake
    
    def record_bet_placed(self, candidate: BetCandidate):
        """Record a bet that was placed"""
        self._today_bets.append(candidate)
        self._hourly_bets.append(candidate)
        self._daily_bet_count += 1
        logger.info(f"Bet recorded: {candidate.bet_label} @ {candidate.odds} for {candidate.stake} KES")
    
    def record_bet_result(self, candidate: BetCandidate, won: bool, profit: float):
        """Record the result of a bet"""
        if won:
            self._session_wins += 1
            self._session_pnl += profit
            self._daily_loss += profit
            logger.info(f"✅ WIN: {candidate.bet_label} | Profit: +{profit:.2f} KES")
        else:
            self._session_losses += 1
            self._session_pnl -= candidate.stake
            self._daily_loss -= candidate.stake
            logger.info(f"❌ LOSS: {candidate.bet_label} | Loss: -{candidate.stake} KES")
    
    def _check_daily_reset(self):
        """Reset daily counters if it's a new day"""
        now = datetime.now()
        
        if self._last_reset is None or now.date() > self._last_reset.date():
            self._today_bets.clear()
            self._hourly_bets.clear()
            self._daily_loss = 0.0
            self._daily_bet_count = 0
            self._last_reset = now
            logger.info("Daily counters reset")
    
    def _check_hourly_reset(self):
        """Reset hourly counters if it's a new hour"""
        now = datetime.now()
        
        if not self._hourly_bets:
            return
        
        last_bet_time = self._hourly_bets[-1].timestamp
        if now - last_bet_time > timedelta(hours=1):
            self._hourly_bets.clear()
            logger.debug("Hourly counters reset")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics"""
        total_bets = self._session_wins + self._session_losses
        win_rate = (self._session_wins / total_bets * 100) if total_bets > 0 else 0
        
        return {
            "mode": self.mode.value,
            "total_bets": total_bets,
            "wins": self._session_wins,
            "losses": self._session_losses,
            "win_rate": win_rate,
            "pnl": self._session_pnl,
            "daily_loss": self._daily_loss,
            "daily_bets": self._daily_bet_count,
            "hourly_bets": len(self._hourly_bets),
        }
    def get_recommendations_summary(self, recommendations: Dict) -> Dict[str, Any]:
        """Get summary of current recommendations"""
        total = sum(len(recs) for recs in recommendations.values())
        
        high_conf = 0
        for recs in recommendations.values():
            for r in recs:
                if r.confidence >= 85:
                    high_conf += 1
        
        return {
            "total_opportunities": total,
            "high_confidence": high_conf,
            "can_bet": self._daily_bet_count < self.settings.max_daily_bets,
            "loss_limit_hit": self._daily_loss <= -config.DAILY_LOSS_LIMIT,
        }


# Singleton
_strategic_bettor: Optional[StrategicBettor] = None

def get_strategic_bettor(mode: StrategyMode = None) -> StrategicBettor:
    """Get the global strategic bettor instance"""
    global _strategic_bettor
    
    if mode is None and _strategic_bettor is None:
        # Default to conservative
        mode = StrategyMode.CONSERVATIVE
    
    if _strategic_bettor is None:
        _strategic_bettor = StrategicBettor(mode)
    elif mode is not None:
        _strategic_bettor.set_strategy(mode)
    
    return _strategic_bettor
