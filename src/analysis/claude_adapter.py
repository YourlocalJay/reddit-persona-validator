import anthropic
import json
import os
from datetime import datetime, timedelta
from typing import Dict
from ..utils.config_loader import config

class ClaudeAnalyzer:
    def __init__(self, mock_mode: bool = False):
        self.client = anthropic.Client(os.getenv("CLAUDE_API_KEY"))
        self.mock_mode = mock_mode

    def analyze(self, persona_data: Dict) -> Dict:
        if self.mock_mode:
            return self._mock_analyze(persona_data)
            
        prompt = self._build_prompt(persona_data)
        
        try:
            response = self.client.completion(
                prompt=prompt,
                model="claude-2",
                max_tokens_to_sample=500
            )
            return self._parse_response(response.completion)
        except Exception as e:
            print(f"Claude API Error: {str(e)}")
            return self._mock_analyze(persona_data)

    def _build_prompt(self, data: Dict) -> str:
        return f"""
        Human: Analyze this Reddit persona and return JSON with:
        - viability_score (1-100)
        - best_use_case array
        - risk_factors array
        - maintenance_notes
        
        Data:
        {json.dumps(data, indent=2)}
        
        Assistant: {{
        """

    def _parse_response(self, response: str) -> Dict:
        try:
            # Claude tends to add text around JSON
            json_str = response[response.find("{"):response.rfind("}")+1]
            result = json.loads(json_str)
            result["next_review_date"] = (
                datetime.now() + 
                timedelta(days=30 if result["viability_score"] > 80 else 7)
            ).strftime('%Y-%m-%d')
            return result
        except json.JSONDecodeError as e:
            print(f"Failed to parse Claude response: {str(e)}")
            return {"error": "Analysis failed"}

    def _mock_analyze(self, data: Dict) -> Dict:
        return {
            "viability_score": 85,
            "best_use_case": ["CPA", "Vault"],
            "risk_factors": ["no recent emails"],
            "maintenance_notes": "Verify email access before use",
            "next_review_date": (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        }
