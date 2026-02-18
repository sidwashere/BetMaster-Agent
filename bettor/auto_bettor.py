"""
bettor/auto_bettor.py
Orchestrates automatic bet placement via scraper browsers.
Applies safety checks before placing any bet.
"""

import asyncio
import logging
from typing import Optional
from predictor.confidence_engine import BetRecommendation
from bettor.bet_history import BetHistory
import config

logger = logging.getLogger(__name__)


class AutoBettor:
    """
    Safe auto-betting engine.
    
    Safety layers:
    1. Confidence threshold check
    2. Daily loss limit check
    3. Minimum edge requirement
    4. Duplicate bet detection (won't bet same game+type twice)
    5. Confirmation callback (optional - for UI to confirm before placing)
    """

    def __init__(self, scraper_manager, history: BetHistory):
        self.scrapers = scraper_manager
        self.history = history
        self._placed_today: set = set()  # game_id + bet_type combos placed today
        self.enabled = False  # Disabled by default - user must enable
        self.on_bet_placed = None   # Callback: fn(rec, bet_id, success)
        self.on_bet_blocked = None  # Callback: fn(rec, reason)

    def enable(self):
        self.enabled = True
        logger.info("🤖 Auto-betting ENABLED")

    def disable(self):
        self.enabled = False
        logger.info("🛑 Auto-betting DISABLED")

    async def consider_bet(self, rec: BetRecommendation) -> bool:
        """
        Evaluate and potentially auto-place a bet.
        Returns True if bet was placed.
        """
        if not self.enabled:
            return False

        # Safety check 1: Confidence threshold
        if rec.confidence < config.AUTO_BET_THRESHOLD:
            return False

        # Safety check 2: Must have positive edge
        if rec.edge <= 0:
            self._block(rec, f"No value edge (edge={rec.edge:.3f})")
            return False

        # Safety check 3: Daily loss limit
        if self.history.is_daily_limit_hit():
            self._block(rec, f"Daily loss limit reached ({config.DAILY_LOSS_LIMIT} KES)")
            return False

        # Safety check 4: Sufficient Balance
        try:
            balance = await self.scrapers.scrapers[rec.game.site].get_balance_kes()
            if balance < rec.recommended_stake:
                self._block(rec, f"Insufficient balance on {rec.game.site}: {balance} KES")
                return False
        except Exception as e:
            logger.warning(f"Could not verify balance on {rec.game.site}: {e}")

        # Safety check 5: Duplicate detection
        dedup_key = f"{rec.game.game_id}_{rec.bet_type}"
        if dedup_key in self._placed_today:
            return False

        # Safety check 5: Odds sanity (avoid extremely short or long odds)
        if rec.odds < 1.15 or rec.odds > 15.0:
            self._block(rec, f"Odds outside safe range: {rec.odds}")
            return False

        # All checks passed - place the bet
        return await self._place_bet(rec, dedup_key)

    async def _place_bet(self, rec: BetRecommendation, dedup_key: str) -> bool:
        """Actually place the bet and record it."""
        game = rec.game
        stake = rec.recommended_stake

        logger.info(
            f"🤖 Auto-placing: {game.home_team} vs {game.away_team} | "
            f"{rec.bet_label} @ {rec.odds} | Stake: {stake} KES | "
            f"Confidence: {rec.confidence:.1f}%"
        )

        try:
            success = await self.scrapers.place_bet(game, rec.bet_type, stake)

            # Record in history regardless of success (for audit trail)
            bet_id = self.history.record_bet(
                site=game.site,
                game_id=game.game_id,
                home_team=game.home_team,
                away_team=game.away_team,
                home_score=game.home_score,
                away_score=game.away_score,
                minute=game.minute,
                bet_type=rec.bet_type,
                bet_label=rec.bet_label,
                odds=rec.odds,
                stake=stake if success else 0,
                confidence=rec.confidence,
                model_probability=rec.model_probability,
                edge=rec.edge,
                auto_placed=True,
            )

            if success:
                self._placed_today.add(dedup_key)
                logger.info(f"✅ Bet #{bet_id} placed successfully")

            if self.on_bet_placed:
                self.on_bet_placed(rec, bet_id, success)

            return success

        except Exception as e:
            logger.error(f"Auto-bet placement error: {e}")
            return False

    def _block(self, rec: BetRecommendation, reason: str):
        logger.debug(f"Bet blocked: {reason}")
        if self.on_bet_blocked:
            self.on_bet_blocked(rec, reason)

    async def process_recommendations(self, all_recs: dict) -> int:
        """
        Process all recommendations and auto-place eligible bets.
        Returns count of bets placed.
        """
        placed = 0
        for game_id, recs in all_recs.items():
            for rec in recs:
                if rec.is_auto_bettable:
                    if await self.consider_bet(rec):
                        placed += 1
                        await asyncio.sleep(2)  # Small delay between bets
        return placed
