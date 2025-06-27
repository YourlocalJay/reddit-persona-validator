"""Persona scoring module for Reddit account validation."""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union, Type

from .base_analyzer import BaseAnalyzer
from .deepseek_analyzer import DeepSeekAnalyzer
from .claude_analyzer import ClaudeAnalyzer
from .mock_analyzer import MockAnalyzer
from ..utils.config_loader import config

# Configure module logger
logger = logging.getLogger(__name__)

class PersonaScorer:
    """
    Orchestrates the AI analysis and scoring process for Reddit personas.
    
    This class manages analyzer selection, data processing, and score calculation,
    combining signals from multiple sources into a unified trust score.
    """
    
    # Define available analyzer types
    ANALYZER_TYPES = {
        "deepseek": DeepSeekAnalyzer,
        "claude": ClaudeAnalyzer,
        "mock": MockAnalyzer
    }
    
    def __init__(self, 
                analyzer_type: str = "deepseek", 
                mock_mode: bool = False,
                fallback_analyzer: Optional[str] = "mock",
                scoring_weights: Optional[Dict[str, float]] = None):
        """
        Initialize the persona scorer.
        
        Args:
            analyzer_type: Type of analyzer to use ('deepseek', 'claude', 'mock')
            mock_mode: Whether to run in mock mode (no actual API calls)
            fallback_analyzer: Analyzer type to use if primary fails
            scoring_weights: Custom weights for scoring components
        """
        self.analyzer_type = analyzer_type.lower()
        self.mock_mode = mock_mode
        self.fallback_analyzer = fallback_analyzer
        
        # Load configuration
        self.analysis_config = config.get("analysis", {})
        
        # Set up scoring weights (default or custom)
        self.scoring_weights = scoring_weights or {
            "account_age": 0.25,
            "karma": 0.25,
            "ai_analysis": 0.5
        }
        
        # Normalize weights to sum to 1.0
        weight_sum = sum(self.scoring_weights.values())
        if weight_sum > 0:
            self.scoring_weights = {k: v / weight_sum for k, v in self.scoring_weights.items()}
        
        # Initialize analyzer (lazy loading)
        self._analyzer = None
        self._fallback_analyzer = None
        
        logger.info(f"Initialized PersonaScorer with {analyzer_type} analyzer (mock_mode={mock_mode})")
    
    @property
    def analyzer(self) -> BaseAnalyzer:
        """Lazy-loaded primary analyzer instance."""
        if self._analyzer is None:
            self._init_analyzer()
        return self._analyzer
    
    @property
    def fallback_analyzer(self) -> Optional[BaseAnalyzer]:
        """Lazy-loaded fallback analyzer instance."""
        if self._fallback_analyzer is None and self._fallback_analyzer_type:
            self._init_fallback_analyzer()
        return self._fallback_analyzer
    
    @fallback_analyzer.setter
    def fallback_analyzer(self, analyzer_type: Optional[str]) -> None:
        """Set the fallback analyzer type."""
        self._fallback_analyzer_type = analyzer_type
        self._fallback_analyzer = None  # Reset to trigger lazy loading
    
    def _init_analyzer(self) -> None:
        """Initialize the primary analyzer based on configuration."""
        try:
            # Validate analyzer type
            if self.analyzer_type not in self.ANALYZER_TYPES:
                logger.warning(f"Invalid analyzer type '{self.analyzer_type}', falling back to 'mock'")
                self.analyzer_type = "mock"
            
            # Get analyzer class
            analyzer_class = self.ANALYZER_TYPES[self.analyzer_type]
            
            # Get analyzer-specific configuration
            analyzer_config = self.analysis_config.get(f"{self.analyzer_type}_config", {})
            
            # Initialize analyzer with configuration
            self._analyzer = analyzer_class(
                mock_mode=self.mock_mode,
                **analyzer_config
            )
            
            logger.info(f"Initialized {self.analyzer_type} analyzer")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.analyzer_type} analyzer: {str(e)}")
            logger.info("Falling back to mock analyzer")
            
            # Fall back to mock analyzer
            self.analyzer_type = "mock"
            self._analyzer = MockAnalyzer(deterministic=True)
    
    def _init_fallback_analyzer(self) -> None:
        """Initialize the fallback analyzer based on configuration."""
        if not self._fallback_analyzer_type:
            return
        
        try:
            # Skip if fallback is same as primary
            if self._fallback_analyzer_type == self.analyzer_type:
                logger.debug("Fallback analyzer is same as primary, skipping initialization")
                return
            
            # Validate analyzer type
            if self._fallback_analyzer_type not in self.ANALYZER_TYPES:
                logger.warning(f"Invalid fallback analyzer type '{self._fallback_analyzer_type}', using 'mock'")
                self._fallback_analyzer_type = "mock"
            
            # Get analyzer class
            analyzer_class = self.ANALYZER_TYPES[self._fallback_analyzer_type]
            
            # Get analyzer-specific configuration
            analyzer_config = self.analysis_config.get(f"{self._fallback_analyzer_type}_config", {})
            
            # Initialize analyzer with configuration
            self._fallback_analyzer = analyzer_class(
                mock_mode=self.mock_mode,
                **analyzer_config
            )
            
            logger.info(f"Initialized {self._fallback_analyzer_type} fallback analyzer")
            
        except Exception as e:
            logger.error(f"Failed to initialize fallback analyzer: {str(e)}")
            self._fallback_analyzer = None
    
    def calculate_trust_score(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive trust score for a Reddit persona.
        
        This method:
        1. Performs AI analysis using the configured analyzer
        2. Calculates component scores based on account properties
        3. Combines scores using weighted formula
        4. Returns complete results with detailed breakdown
        
        Args:
            persona_data: Dictionary containing Reddit persona data
            
        Returns:
            Dictionary with trust score and analysis results
        """
        logger.info(f"Calculating trust score for {persona_data.get('username', 'unknown')}")
        
        # Calculate base scores from account properties
        base_scores = self._calculate_base_scores(persona_data)
        
        # Perform AI analysis
        ai_analysis = self._perform_analysis(persona_data)
        
        # Calculate combined trust score
        trust_score = self._calculate_combined_score(base_scores, ai_analysis)
        
        # Prepare full result
        result = {
            **persona_data,  # Include original data
            "trust_score": trust_score,
            "component_scores": base_scores,
            "ai_analysis": ai_analysis,
            "analysis_timestamp": datetime.now().isoformat(),
            "analyzer_used": self.analyzer.__class__.__name__
        }
        
        logger.info(f"Trust score calculation complete: {trust_score}")
        return result
    
    def _calculate_base_scores(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate base component scores from account properties.
        
        Args:
            persona_data: Dictionary containing Reddit persona data
            
        Returns:
            Dictionary with component scores
        """
        # Extract relevant metrics
        age_days = persona_data.get("age_days", 0)
        age_years = persona_data.get("Account Age (yrs)", age_days / 365 if age_days else 0)
        karma = int(persona_data.get("Karma", persona_data.get("karma", 0)))
        post_karma = int(persona_data.get("post_karma", 0))
        comment_karma = int(persona_data.get("comment_karma", 0))
        verified_email = persona_data.get("verified_email", False)
        
        # Calculate age score: 100 if >= 3 years, proportional otherwise
        age_score = min(100, (age_days / 1095) * 100) if age_days else min(100, age_years * 33.3)
        
        # Calculate karma score: 100 if >= 50000, proportional otherwise
        karma_score = min(100, (karma / 50000) * 100)
        
        # Calculate karma distribution score
        karma_distribution_score = 0
        if post_karma > 0 and comment_karma > 0:
            # Ideal ratio is around 30% post, 70% comment
            post_ratio = post_karma / (post_karma + comment_karma)
            karma_distribution_score = 100 - min(100, abs(post_ratio - 0.3) * 200)
        
        # Bonus for verified email
        email_verified_score = 100 if verified_email else 0
        
        return {
            "age_score": round(age_score, 1),
            "karma_score": round(karma_score, 1),
            "karma_distribution_score": round(karma_distribution_score, 1),
            "email_verified_score": email_verified_score
        }
    
    def _perform_analysis(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform AI analysis of persona data.
        
        Args:
            persona_data: Dictionary containing Reddit persona data
            
        Returns:
            Dictionary with AI analysis results
        """
        try:
            # Use primary analyzer
            analysis_result = self.analyzer.analyze(persona_data)
            
            # Check if analysis succeeded
            if "error" in analysis_result and self.fallback_analyzer:
                logger.warning(f"Primary analyzer failed: {analysis_result.get('error')}")
                logger.info(f"Trying fallback analyzer: {self._fallback_analyzer_type}")
                
                # Try fallback analyzer
                analysis_result = self.fallback_analyzer.analyze(persona_data)
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            
            # Try fallback analyzer
            if self.fallback_analyzer:
                try:
                    logger.info(f"Trying fallback analyzer: {self._fallback_analyzer_type}")
                    return self.fallback_analyzer.analyze(persona_data)
                except Exception as fallback_error:
                    logger.error(f"Fallback analyzer failed: {str(fallback_error)}")
            
            # Return error details if all analyzers fail
            return {
                "error": str(e),
                "viability_score": 0,
                "best_use_case": ["Analysis Failed"],
                "risk_factors": ["Analysis error", str(e)],
                "maintenance_notes": "Please verify account manually"
            }
    
    def _calculate_combined_score(self, 
                                 base_scores: Dict[str, float], 
                                 ai_analysis: Dict[str, Any]) -> float:
        """
        Calculate combined trust score from component scores.
        
        Args:
            base_scores: Dictionary with base component scores
            ai_analysis: Dictionary with AI analysis results
            
        Returns:
            Combined trust score (0-100)
        """
        # Get viability score from AI analysis
        ai_score = ai_analysis.get("viability_score", 0)
        
        # Calculate weighted score
        account_age_weight = self.scoring_weights.get("account_age", 0.25)
        karma_weight = self.scoring_weights.get("karma", 0.25)
        ai_weight = self.scoring_weights.get("ai_analysis", 0.5)
        
        combined_score = (
            base_scores["age_score"] * account_age_weight +
            base_scores["karma_score"] * karma_weight +
            ai_score * ai_weight
        )
        
        # Apply penalties
        if "error" in ai_analysis:
            # Apply penalty for analysis error
            combined_score *= 0.9
        
        # Clamp score to 0-100 range
        combined_score = max(0, min(100, combined_score))
        
        return round(combined_score, 1)
