from typing import Dict
from .deepseek_adapter import DeepSeekAnalyzer
from .claude_adapter import ClaudeAnalyzer

class PersonaScorer:
    def __init__(self, analyzer_type: str = "deepseek", mock_mode: bool = False):
        self.analyzer = (
            DeepSeekAnalyzer(mock_mode=mock_mode) 
            if analyzer_type == "deepseek" 
            else ClaudeAnalyzer(mock_mode=mock_mode)
    
    def calculate_trust_score(self, persona_data: Dict) -> Dict:
        """Unified scoring interface"""
        base_score = min(
            int(persona_data.get("Karma", 0)) * 0.001 + 
            float(persona_data.get("Account Age (yrs)", 0)) * 1.5,
            100
        )
        
        # Enhance with AI analysis
        ai_analysis = self.analyzer.analyze(persona_data)
        
        return {
            **persona_data,
            "trust_score": round(base_score * 0.7 + ai_analysis.get("viability_score", 0) * 0.3),
            "ai_analysis": ai_analysis
        }
