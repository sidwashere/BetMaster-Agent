import json
import logging
import requests
import asyncio
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class OllamaAnalyzer:
    """
    Interface for local Ollama AI analysis.
    Connects to a running Ollama instance to provide qualitative analysis of game stats.
    """
    
    def __init__(self, model_name: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model_name
        self.base_url = base_url
        self.api_url = f"{base_url}/api/generate"
        self._available = False
        
        # Check connection on init
        try:
            requests.get(base_url, timeout=2)
            self._available = True
            logger.info(f"✅ Ollama connected at {base_url} (model: {model_name})")
        except Exception:
            logger.warning(f"⚠️ Ollama not found at {base_url}. AI analysis will be disabled.")

    @property
    def is_available(self) -> bool:
        return self._available

    async def analyze_game(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send game state to Ollama for analysis.
        Returns a dict with: {'confidence': int, 'reasoning': str, 'recommendation': str}
        """
        if not self._available:
            return {}

        prompt = self._build_prompt(game_state)
        
        try:
            # We run the blocking request in a separate thread to not block the async loop
            response = await asyncio.to_thread(self._query_ollama, prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Ollama analysis failed: {e}")
            return {}

    def _query_ollama(self, prompt: str) -> str:
        """Raw blocking request to Ollama."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json"  # Force JSON output if model supports it
        }
        
        try:
            res = requests.post(self.api_url, json=payload, timeout=10)
            if res.status_code == 200:
                return res.json().get("response", "")
            else:
                logger.error(f"Ollama error {res.status_code}: {res.text}")
                return ""
        except Exception as e:
            logger.error(f"Ollama connection error: {e}")
            return ""

    def _build_prompt(self, game: Dict[str, Any]) -> str:
        """Construct the analysis prompt."""
        return f"""
        You are a professional football (soccer) betting analyst. Analyze this live game state and provide a betting recommendation.
        
        MATCH: {game.get('home_team')} vs {game.get('away_team')}
        SCORE: {game.get('home_score')} - {game.get('away_score')}
        TIME: {game.get('minute')}'
        
        STATS (if available):
        - Attacks: {game.get('stats', {}).get('attacks', 'N/A')}
        - Dangerous Attacks: {game.get('stats', {}).get('dangerous_attacks', 'N/A')}
        - Possession: {game.get('stats', {}).get('possession', 'N/A')}
        
        MARKET ODDS:
        - Home Win: {game.get('odds_home_win')}
        - Draw: {game.get('odds_draw')}
        - Away Win: {game.get('odds_away_win')}
        
        TASK:
        Analyze the game momentum. If the favorite is losing or drawing late, is there value?
        If there are many dangerous attacks, is a goal imminent?
        
        RESPONSE FORMAT (JSON ONLY):
        {{
            "confidence": <0-100 integer representing your confidence in a bet>,
            "recommended_bet": "<Home Win / Away Win / Over 2.5 / None>",
            "reasoning": "<Short explanation, max 2 sentences. Mention momentum.>"
        }}
        """

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse strict JSON from LLM response."""
        try:
            # Clean up potential markdown code blocks
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            
            # Normalize keys
            return {
                "confidence": int(data.get("confidence", 0)),
                "recommendation": data.get("recommended_bet", "None"),
                "reasoning": data.get("reasoning", "No reasoning provided.")
            }
        except Exception as e:
            logger.warning(f"Failed to parse Ollama JSON: {e}\nRaw response: {response_text[:100]}...")
            return {}
