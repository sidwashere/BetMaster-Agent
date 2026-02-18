"""
analyzer/ollama_analyzer.py
Ollama AI analyzer optimized for gemma3:1b for live football betting analysis
"""

import json
import logging
import requests
import asyncio
import hashlib
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result from AI analysis"""
    confidence: int = 0  # 0-100
    recommended_bet: str = "None"  # "Home Win", "Away Win", "Over 2.5", etc.
    reasoning: str = ""
    key_factors: List[str] = field(default_factory=list)
    risk_level: str = "medium"  # "low", "medium", "high"
    momentum: str = "neutral"  # "home", "away", "neutral"
    raw_response: str = ""


class OllamaAnalyzer:
    """
    Local AI analyzer using Ollama with gemma3:1b.
    Optimized for fast inference on live betting decisions.
    """
    
    def __init__(
        self, 
        model_name: str = "gemma3:1b",
        base_url: str = "http://localhost:11434"
    ):
        self.model = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self._available = False
        self._check_connection()
        
        # Cache for analysis results (don't re-analyze same game state)
        self._cache: Dict[str, AnalysisResult] = {}
        self._cache_ttl = 30  # seconds
    
    def _check_connection(self):
        """Check if Ollama is available"""
        try:
            response = requests.get(self.base_url, timeout=2)
            if response.status_code == 200:
                self._available = True
                logger.info(f"✅ Ollama connected at {self.base_url} (model: {self.model})")
            else:
                logger.warning(f"⚠️ Ollama returned {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"⚠️ Ollama not found at {self.base_url}. AI analysis disabled.")
        except Exception as e:
            logger.warning(f"⚠️ Ollama check failed: {e}")
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    async def analyze_game(self, game_data: Dict[str, Any]) -> AnalysisResult:
        """
        Analyze a live game and return betting recommendation.
        Uses caching to avoid re-analyzing same game state.
        """
        if not self._available:
            return AnalysisResult()
        
        # Create cache key from game state
        cache_key = self._make_cache_key(game_data)
        
        # Check cache
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # Check if cache is still valid
            if time.time() - getattr(cached, '_cache_time', 0) < self._cache_ttl:
                logger.debug(f"Using cached analysis for {game_data.get('home_team')} vs {game_data.get('away_team')}")
                return cached
        
        # Build prompt for gemma3
        prompt = self._build_prompt(game_data)
        
        try:
            # Run blocking request in thread pool
            response = await asyncio.to_thread(self._query_ollama, prompt)
            result = self._parse_response(response)
            
            # Cache the result
            result._cache_time = time.time()
            self._cache[cache_key] = result
            
            return result
        except Exception as e:
            logger.error(f"Ollama analysis failed: {e}")
            return AnalysisResult()
    
    def _make_cache_key(self, game_data: Dict) -> str:
        """Create a cache key from game data"""
        key_parts = [
            str(game_data.get("home_team", "")),
            str(game_data.get("away_team", "")),
            str(game_data.get("home_score", 0)),
            str(game_data.get("away_score", 0)),
            str(game_data.get("minute", 0)),
            str(game_data.get("odds_home_win", 0)),
            str(game_data.get("odds_away_win", 0)),
        ]
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _query_ollama(self, prompt: str) -> str:
        """Make request to Ollama"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # Low temperature for consistent results
                "top_p": 0.8,
                "num_predict": 512,  # Limit response length for speed
            }
        }
        
        try:
            response = requests.post(
                self.api_url, 
                json=payload, 
                timeout=30  # Increased for gemma3:1b
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            else:
                logger.error(f"Ollama error {response.status_code}: {response.text}")
                return ""
        except requests.exceptions.Timeout:
            logger.warning("Ollama request timed out")
            return ""
        except Exception as e:
            logger.error(f"Ollama connection error: {e}")
            return ""
    
    def _build_prompt(self, game: Dict[str, Any]) -> str:
        """Build optimized prompt for gemma3:1b"""
        
        home = game.get("home_team", "Unknown")
        away = game.get("away_team", "Unknown")
        home_score = game.get("home_score", 0)
        away_score = game.get("away_score", 0)
        minute = game.get("minute", 0)
        
        # Format odds
        odds_info = []
        if game.get("odds_home_win"):
            odds_info.append(f"Home: {game['odds_home_win']}")
        if game.get("odds_draw"):
            odds_info.append(f"Draw: {game['odds_draw']}")
        if game.get("odds_away_win"):
            odds_info.append(f"Away: {game['odds_away_win']}")
        if game.get("odds_over_25"):
            odds_info.append(f"Over 2.5: {game['odds_over_25']}")
        if game.get("odds_under_25"):
            odds_info.append(f"Under 2.5: {game['odds_under_25']}")
        
        odds_str = ", ".join(odds_info) if odds_info else "N/A"
        
        # Build the prompt
        prompt = f"""You are a professional football betting analyst. Analyze this LIVE match and give a betting recommendation.

MATCH: {home} vs {away}
SCORE: {home_score} - {away_score}
TIME: {minute}' (live)
BOOKMAKER ODDS: {odds_str}

Your task:
1. Analyze the current game state and momentum
2. Consider: scoring rate, recent form, key events (goals, cards), time remaining
3. Identify VALUE - where odds are better than the true probability
4. Output a clear recommendation

Respond ONLY with this JSON format:
{{
  "confidence": <0-100>,
  "recommended_bet": "<Home Win | Draw | Away Win | Over 2.5 | Under 2.5 | None>",
  "reasoning": "<2-3 sentence explanation>",
  "key_factors": ["<factor1>", "<factor2>"],
  "risk_level": "<low|medium|high>",
  "momentum": "<home|away|neutral>"
}}

Consider:
- If losing team has 20+ min and strong attacks → value on them
- If game is 0-0 at 60+ min → under 2.5 has value
- If over 2.5 already hit but line moved → no more value
- Home advantage matters but not as much in live betting
- Track the game flow - who's controlling?
"""
        return prompt
    
    def _parse_response(self, response_text: str) -> AnalysisResult:
        """Parse the AI response into structured result"""
        
        # Try to extract JSON from response
        try:
            # Find JSON in response
            import re
            
            # Look for JSON block
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                json_str = response_text
            
            # Clean up and parse
            json_str = json_str.strip()
            data = json.loads(json_str)
            
            return AnalysisResult(
                confidence=int(data.get("confidence", 0)),
                recommended_bet=data.get("recommended_bet", "None"),
                reasoning=data.get("reasoning", ""),
                key_factors=data.get("key_factors", []),
                risk_level=data.get("risk_level", "medium"),
                momentum=data.get("momentum", "neutral"),
                raw_response=response_text
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI JSON: {e}")
            # Try simpler extraction
            return self._fallback_parse(response_text)
        except Exception as e:
            logger.error(f"Parse error: {e}")
            return AnalysisResult()
    
    def _fallback_parse(self, response: str) -> AnalysisResult:
        """Fallback parsing when JSON fails"""
        import re
        
        response_lower = response.lower()
        
        # Extract confidence
        conf_match = re.search(r'confidence["\s:]+(\d+)', response_lower)
        confidence = int(conf_match.group(1)) if conf_match else 50
        
        # Extract recommended bet
        recommended = "None"
        if "home win" in response_lower or '"home' in response_lower:
            recommended = "Home Win"
        elif "away win" in response_lower or '"away' in response_lower:
            recommended = "Away Win"
        elif "draw" in response_lower:
            recommended = "Draw"
        elif "over 2.5" in response_lower or "over" in response_lower:
            recommended = "Over 2.5"
        elif "under 2.5" in response_lower or "under" in response_lower:
            recommended = "Under 2.5"
        
        # Extract risk
        risk = "medium"
        if "low" in response_lower:
            risk = "low"
        elif "high" in response_lower:
            risk = "high"
        
        # Extract momentum
        momentum = "neutral"
        if "home" in response_lower and ("momentum" in response_lower or "controlling" in response_lower):
            momentum = "home"
        elif "away" in response_lower and ("momentum" in response_lower or "controlling" in response_lower):
            momentum = "away"
        
        return AnalysisResult(
            confidence=confidence,
            recommended_bet=recommended,
            reasoning=response[:200],
            risk_level=risk,
            momentum=momentum,
            raw_response=response
        )
    
    def clear_cache(self):
        """Clear the analysis cache"""
        self._cache.clear()
        logger.info("Analysis cache cleared")
    
    async def batch_analyze(
        self, 
        games: List[Dict[str, Any]]
    ) -> Dict[str, AnalysisResult]:
        """
        Analyze multiple games.
        Results are cached per game.
        """
        results = {}
        
        # Analyze all games concurrently
        tasks = [self.analyze_game(game) for game in games]
        analyses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for game, analysis in zip(games, analyses):
            if isinstance(analysis, Exception):
                logger.error(f"Analysis error: {analysis}")
                continue
            
            game_id = f"{game.get('home_team')}_{game.get('away_team')}"
            results[game_id] = analysis
        
        return results


# Singleton
_ollama_analyzer: Optional[OllamaAnalyzer] = None

def get_ollama_analyzer(
    model: str = "gemma3:1b", 
    base_url: str = "http://localhost:11434"
) -> OllamaAnalyzer:
    """Get the global Ollama analyzer instance"""
    global _ollama_analyzer
    if _ollama_analyzer is None:
        _ollama_analyzer = OllamaAnalyzer(model, base_url)
    return _ollama_analyzer
