import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
from ..utils.config_loader import config

class DeepSeekAnalyzer:
    def __init__(self, mock_mode: bool = False):
        self.base_url = config.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.mock_mode = mock_mode
        self.mock_responses = {
            "high_trust": {
                "viability_score": 92,
                "best_use_case": ["CPA", "Influence Ops"],
                "risk_factors": ["none detected"],
                "maintenance_notes": "Prime for immediate use"
            },
            "medium_trust": {
                "viability_score": 68,
                "best_use_case": ["Community Building"],
                "risk_factors": ["low comment karma"],
                "maintenance_notes": "Needs 10+ comments before CPA deployment"
            }
        }

    def analyze(self, persona_data: Dict) -> Dict:
        """Analyze persona data using DeepSeek API or mock"""
        if self.mock_mode:
            return self._mock_analyze(persona_data)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = self._build_prompt(persona_data)
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3
                },
                timeout=10
            )
            response.raise_for_status()
            return self._parse_response(response.json())
        except Exception as e:
            print(f"DeepSeek API Error: {str(e)}")
            return self._mock_analyze(persona_data)  # Fallback to mock

    def _build_prompt(self, data: Dict) -> str:
        return f"""
        Analyze this Reddit persona and provide JSON output with:
        - viability_score (1-100)
        - best_use_case (CPA/Community/Influence/Vault)
        - top 3 risk_factors
        - maintenance_notes
        
        Data:
        {json.dumps(data, indent=2)}
        """

    def _parse_response(self, response: Dict) -> Dict:
        try:
            content = json.loads(response["choices"][0]["message"]["content"])
            content["next_review_date"] = (
                datetime.now() + 
                timedelta(days=30 if content["viability_score"] > 80 else 7)
            ).strftime('%Y-%m-%d')
            return content
        except (KeyError, json.JSONDecodeError) as e:
            print(f"Response parsing error: {str(e)}")
            return {"error": "Analysis failed"}

    def _mock_analyze(self, data: Dict) -> Dict:
        """Mock analysis for testing"""
        trust_level = "high_trust" if int(data.get("Karma", 0)) > 3000 else "medium_trust"
        result = self.mock_responses[trust_level].copy()
        result["next_review_date"] = (
            datetime.now() + 
            timedelta(days=30 if result["viability_score"] > 80 else 7)
        ).strftime('%Y-%m-%d')
        return result
