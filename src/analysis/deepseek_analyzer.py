"""DeepSeek AI analyzer implementation for Reddit persona analysis."""

import os
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from .base_analyzer import BaseAnalyzer, APIError, RateLimitExceeded
from ..utils.config_loader import config

# Configure module logger
logger = logging.getLogger(__name__)

class DeepSeekAnalyzer(BaseAnalyzer):
    """
    DeepSeek LLM-based analyzer for Reddit persona validation.

    This analyzer uses the DeepSeek API to analyze Reddit personas and generate
    trust assessments, usage recommendations, and risk factors.
    """

    def __init__(self,
                api_key: Optional[str] = None,
                mock_mode: bool = False,
                base_url: Optional[str] = None,
                model: str = "deepseek-chat",
                temperature: float = 0.3,
                rate_limit_calls: int = 10,
                rate_limit_period: int = 60,
                max_retries: int = 3):
        """
        Initialize the DeepSeek analyzer.

        Args:
            api_key: DeepSeek API key (defaults to environment variable)
            mock_mode: Whether to run in mock mode (no actual API calls)
            base_url: Base URL for DeepSeek API
            model: DeepSeek model to use
            temperature: Temperature parameter for generation
            rate_limit_calls: Maximum number of API calls in the rate limit period
            rate_limit_period: Rate limit period in seconds
            max_retries: Maximum number of retries for API calls
        """
        # Get API key from environment if not provided
        if api_key is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")

        super().__init__(
            api_key=api_key,
            mock_mode=mock_mode,
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            max_retries=max_retries
        )

        # DeepSeek specific configuration
        self.base_url = base_url or config.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
        self.model = model
        self.temperature = temperature

        # Mock response templates for different trust levels
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
                "risk_factors": ["low comment karma", "minimal post history"],
                "maintenance_notes": "Needs 10+ comments before CPA deployment"
            },
            "low_trust": {
                "viability_score": 34,
                "best_use_case": ["Monitoring Only"],
                "risk_factors": ["account age suspicious", "irregular activity pattern"],
                "maintenance_notes": "Not recommended for active use"
            }
        }

    def extract_content(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant content from persona data for analysis.

        Args:
            persona_data: Dictionary containing Reddit persona data

        Returns:
            Dictionary with extracted content ready for analysis
        """
        logger.debug(f"Extracting content from persona data: {persona_data.keys()}")

        # Extract relevant fields for analysis
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
            "trophies": persona_data.get("trophies", []),
            "recent_posts": persona_data.get("recent_posts", []),
            "recent_comments": persona_data.get("recent_comments", []),
            "subreddits": persona_data.get("active_in_subreddits", []),
            "timestamp": datetime.now().isoformat()
        }

        # Calculate activity metrics if available
        if extracted["recent_posts"] and isinstance(extracted["recent_posts"], list):
            extracted["post_frequency"] = len(extracted["recent_posts"])
            extracted["post_subreddits"] = list(set([p.get("subreddit", "") for p in extracted["recent_posts"] if isinstance(p, dict)]))

        if extracted["recent_comments"] and isinstance(extracted["recent_comments"], list):
            extracted["comment_frequency"] = len(extracted["recent_comments"])
            extracted["comment_subreddits"] = list(set([c.get("subreddit", "") for c in extracted["recent_comments"] if isinstance(c, dict)]))

        return extracted

    def analyze_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze extracted content using DeepSeek API.

        Args:
            content: Extracted content dictionary

        Returns:
            Dictionary with analysis results

        Raises:
            RateLimitExceeded: If API rate limit is exceeded
            APIError: If API call fails
        """
        if self.mock_mode:
            return self._mock_analyze(content)

        if not self.api_key:
            logger.error("DeepSeek API key not provided")
            raise APIError("DeepSeek API key not provided")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        prompt = self._build_prompt(content)
        timeout = config.get("deepseek_timeout", 10)

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": self.temperature
                },
                timeout=timeout
            )

            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("DeepSeek API rate limit exceeded")
                raise RateLimitExceeded("DeepSeek API rate limit exceeded")

            # Handle other errors
            if response.status_code != 200:
                logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
                raise APIError(f"DeepSeek API error: {response.status_code} - {response.text}")

            return self._parse_response(response.json())

        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API request failed: {str(e)}")
            raise APIError(f"DeepSeek API request failed: {str(e)}")

    def _build_prompt(self, content: Dict[str, Any]) -> str:
        """
        Build prompt for DeepSeek API based on extracted content.

        Args:
            content: Extracted content dictionary

        Returns:
            Formatted prompt string
        """
        # Format content for the prompt
        content_str = json.dumps(content, indent=2)

        return f"""
        You are an expert at analyzing Reddit accounts to determine their trustworthiness and potential use cases.

        Analyze the following Reddit persona data and provide a detailed assessment in JSON format.

        Consider factors like:
        - Account age and karma distribution
        - Posting patterns and frequency
        - Subreddit participation
        - Overall authenticity indicators

        Reddit Persona Data:
        {content_str}

        Respond with a JSON object having these exact fields:
        - viability_score (1-100): Overall trustworthiness score
        - best_use_case (array of strings): Top potential use cases for this account (e.g., "CPA", "Community Building", "Influence Ops", "Vault", "Monitoring Only")
        - risk_factors (array of strings): Specific concerns or vulnerabilities
        - maintenance_notes (string): Recommendations for account maintenance

        Format your response as a valid JSON object only.
        """

    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse and normalize response from DeepSeek API.

        Args:
            response: Raw response from DeepSeek API

        Returns:
            Normalized dictionary with analysis results
        """
        try:
            # Extract content from response
            content_str = response["choices"][0]["message"]["content"]

            # Parse JSON from content
            content = json.loads(content_str)

            # Coerce viability_score to int
            content["viability_score"] = int(content.get("viability_score", 0))

            # Add next review date based on viability score
            review_days = 30 if content.get("viability_score", 0) > 80 else 7
            content["next_review_date"] = (
                datetime.now() + timedelta(days=review_days)
            ).strftime('%Y-%m-%d')

            if not content.get("risk_factors"):
                content["risk_factors"] = ["no risk factors returned"]

            return content

        except (KeyError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse DeepSeek response: {str(e)}")

            # Return error details
            return {
                "error": f"Failed to parse response: {str(e)}",
                "viability_score": 0,
                "best_use_case": ["None"],
                "risk_factors": ["Analysis failed", str(e)],
                "maintenance_notes": "Retry analysis or verify account manually",
                "next_review_date": (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
            }

    def _mock_analyze(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate mock analysis results for testing.

        Args:
            content: Extracted content dictionary

        Returns:
            Mock analysis results dictionary
        """
        # Determine trust level based on account properties
        karma = content.get("karma", 0)
        account_age_days = content.get("account_age_days", 0)

        if karma > 5000 and account_age_days > 365:
            trust_level = "high_trust"
        elif karma > 1000 and account_age_days > 90:
            trust_level = "medium_trust"
        else:
            trust_level = "low_trust"

        # Get base mock response for this trust level
        result = self.mock_responses[trust_level].copy()
        result["risk_factors"] = result.get("risk_factors", [])

        # Customize based on specific account properties
        if account_age_days < 30:
            result["risk_factors"].append("new account (less than 30 days)")
        if karma == 0:
            result["risk_factors"].append("zero karma")

        if content.get("verified_email", False):
            if "risk_factors" in result and "none detected" not in result["risk_factors"]:
                result["risk_factors"].append("verified email lacking")

        if content.get("is_gold", False):
            result["viability_score"] = min(100, result["viability_score"] + 5)

        # Add next review date
        result["next_review_date"] = (
            datetime.now() +
            timedelta(days=30 if result["viability_score"] > 80 else 7)
        ).strftime('%Y-%m-%d')

        return result
