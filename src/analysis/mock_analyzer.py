"""Mock analyzer implementation for testing without API calls."""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from .base_analyzer import BaseAnalyzer

# Configure module logger
logger = logging.getLogger(__name__)

class MockAnalyzer(BaseAnalyzer):
    """
    Mock analyzer for testing the Reddit persona validation pipeline.

    This analyzer provides consistent, configurable results without making
    actual API calls, allowing for testing and development without using
    API quotas or requiring API keys.
    """

    def __init__(self,
                deterministic: bool = True,
                success_rate: float = 0.95,
                response_time_range: tuple = (0.5, 2.0),
                rate_limit_calls: int = 1000,
                rate_limit_period: int = 60):
        """
        Initialize the mock analyzer.

        Args:
            deterministic: Whether to produce deterministic results
            success_rate: Probability of successful analysis (0.0-1.0)
            response_time_range: Range of simulated response times (min, max) in seconds
            rate_limit_calls: Maximum number of API calls in the rate limit period
            rate_limit_period: Rate limit period in seconds
        """
        super().__init__(
            api_key="mock_api_key",
            mock_mode=True,
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            max_retries=3
        )

        self.deterministic = deterministic
        self.success_rate = max(0.0, min(1.0, success_rate))  # Clamp to [0.0, 1.0]
        self.response_time_range = response_time_range

        # Mock response templates for different trust levels
        self.mock_responses = {
            "high_trust": {
                "viability_score": 91,
                "best_use_case": ["CPA", "Influence Ops", "Vault"],
                "risk_factors": ["needs regular activity to maintain credibility"],
                "maintenance_notes": "High-value account ready for deployment"
            },
            "medium_trust": {
                "viability_score": 64,
                "best_use_case": ["Community Building", "Information Gathering"],
                "risk_factors": ["limited post history", "karma distribution uneven"],
                "maintenance_notes": "Needs additional comment activity in key subreddits"
            },
            "low_trust": {
                "viability_score": 32,
                "best_use_case": ["Monitoring Only", "Test Account"],
                "risk_factors": ["suspicious activity pattern", "potential throwaway account", "too recent"],
                "maintenance_notes": "Not recommended for primary operations"
            },
            "very_low_trust": {
                "viability_score": 14,
                "best_use_case": ["None"],
                "risk_factors": ["bot-like behavior", "karma farming detected", "suspicious creation pattern"],
                "maintenance_notes": "Avoid using this account for operations"
            }
        }

        logger.info(f"Initialized MockAnalyzer (deterministic={deterministic}, success_rate={success_rate})")

    def extract_content(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant content from persona data for analysis.

        Args:
            persona_data: Dictionary containing Reddit persona data

        Returns:
            Dictionary with extracted content ready for analysis
        """
        logger.debug(f"Extracting content from persona data: {persona_data.keys()}")

        # Extract relevant fields for analysis (similar to real analyzers)
        extracted = {
            "username": persona_data.get("username", ""),
            "account_age_days": persona_data.get("age_days", 0),
            "account_age_years": persona_data.get("Account Age (yrs)", 0),
            "karma": persona_data.get("Karma", persona_data.get("karma", 0)),
            "post_karma": persona_data.get("post_karma", 0),
            "comment_karma": persona_data.get("comment_karma", 0),
            "verified_email": persona_data.get("verified_email", False),
            "is_gold": persona_data.get("is_gold", False),
            "is_mod": persona_data.get("is_mod", False),
            "has_verified_email": persona_data.get("has_verified_email", False),
            "subreddits": persona_data.get("active_in_subreddits", []),
            "timestamp": datetime.now().isoformat()
        }

        return extracted

    def analyze_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate analyzing content with a mock AI service.

        Args:
            content: Extracted content dictionary

        Returns:
            Dictionary with mock analysis results
        """
        # Simulate API processing time
        if not self.deterministic:
            min_time, max_time = self.response_time_range
            processing_time = random.uniform(min_time, max_time)
            logger.debug(f"Simulating API processing time: {processing_time:.2f}s")

        # Simulate occasional failures
        if not self.deterministic and random.random() > self.success_rate:
            logger.warning("Simulating API failure")
            raise Exception("Simulated API failure")

        # Generate mock analysis
        return self._mock_analyze(content)

    def _build_prompt(self, content: Dict[str, Any]) -> str:
        """
        Mock prompt building (not used for actual API calls).

        Args:
            content: Extracted content dictionary

        Returns:
            Mock prompt string
        """
        return f"Mock prompt for {content.get('username', 'unknown')}"

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """
        Mock response parsing (not used for actual API responses).

        Args:
            response: Mock response

        Returns:
            Normalized mock results dictionary
        """
        # Just return the response as is (it's already in the right format)
        return response

    def _mock_analyze(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate mock analysis results based on content.

        Args:
            content: Extracted content dictionary

        Returns:
            Mock analysis results dictionary
        """
        # Determine trust level based on account properties
        username = content.get("username", "")
        karma = content.get("karma", 0)
        account_age_days = content.get("account_age_days", 0)

        # Use deterministic hash of username if deterministic mode is on
        if self.deterministic and username:
            # Simple hash function for deterministic results
            hash_value = sum(ord(c) for c in username) % 100

            if hash_value < 15:
                trust_level = "very_low_trust"
            elif hash_value < 40:
                trust_level = "low_trust"
            elif hash_value < 75:
                trust_level = "medium_trust"
            else:
                trust_level = "high_trust"
        else:
            # Otherwise use account properties
            if karma > 10000 and account_age_days > 730:  # 2+ years
                trust_level = "high_trust"
            elif karma > 3000 and account_age_days > 365:  # 1+ year
                trust_level = "medium_trust"
            elif karma > 500 and account_age_days > 90:  # 3+ months
                trust_level = "low_trust"
            else:
                trust_level = "very_low_trust"

        # Get base mock response for this trust level
        result = self.mock_responses[trust_level].copy()
        result["risk_factors"] = result.get("risk_factors", [])

        # Add small random variations if not deterministic
        if not self.deterministic:
            # Vary the viability score slightly
            score_variation = random.uniform(-5, 5)
            result["viability_score"] = max(1, min(100, int(result["viability_score"] + score_variation)))

            # Occasionally add or remove risk factors
            if random.random() < 0.3 and len(result["risk_factors"]) > 1:
                result["risk_factors"].pop(random.randrange(len(result["risk_factors"])))

            if random.random() < 0.3:
                additional_risks = [
                    "irregular posting schedule",
                    "potential dormant account",
                    "cross-posts between unrelated subreddits",
                    "unusual karma to age ratio"
                ]
                result["risk_factors"].append(random.choice(additional_risks))

        # Add deterministic behavior warnings
        if karma == 0:
            result["risk_factors"].append("zero karma")
        if account_age_days < 30:
            result["risk_factors"].append("new account (less than 30 days old)")
        if not content.get("subreddits"):
            result["risk_factors"].append("no subreddit engagement")

        # Add account-specific customizations
        if content.get("is_mod", False):
            result["viability_score"] = min(100, result["viability_score"] + 10)
            if "best_use_case" in result and "Community Building" not in result["best_use_case"]:
                result["best_use_case"].append("Community Building")

        if content.get("is_gold", False):
            result["viability_score"] = min(100, result["viability_score"] + 5)
            if "risk_factors" in result:
                if "financial investment" not in result["risk_factors"]:
                    result["risk_factors"].append("financial investment")

        # Force viability_score to int
        result["viability_score"] = int(result.get("viability_score", 0))

        # Add next review date
        result["next_review_date"] = (
            datetime.now() +
            timedelta(days=30 if result["viability_score"] > 80 else 14 if result["viability_score"] > 50 else 7)
        ).strftime('%Y-%m-%d')

        # Add mock metadata
        result["analyzer"] = "MockAnalyzer"
        result["mock"] = True

        return result
