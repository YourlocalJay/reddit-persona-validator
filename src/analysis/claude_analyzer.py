"""Claude AI analyzer implementation for Reddit persona analysis."""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

from anthropic import Anthropic, RateLimitError, APIError as AnthropicAPIError

from .base_analyzer import BaseAnalyzer, APIError, RateLimitExceeded
from ..utils.config_loader import config

# Configure module logger
logger = logging.getLogger(__name__)

class ClaudeAnalyzer(BaseAnalyzer):
    """
    Claude-based analyzer for Reddit persona validation.
    
    This analyzer uses Anthropic's Claude API to analyze Reddit personas and
    provide detailed trust assessments with actionable insights.
    """
    
    def __init__(self, 
                api_key: Optional[str] = None, 
                mock_mode: bool = False,
                model: str = "claude-3-5-sonnet-20240620",
                max_tokens: int = 1000,
                temperature: float = 0.2,
                rate_limit_calls: int = 5,
                rate_limit_period: int = 60,
                max_retries: int = 3):
        """
        Initialize the Claude analyzer.
        
        Args:
            api_key: Anthropic API key (defaults to environment variable)
            mock_mode: Whether to run in mock mode (no actual API calls)
            model: Claude model to use
            max_tokens: Maximum tokens for response
            temperature: Temperature parameter for generation
            rate_limit_calls: Maximum number of API calls in the rate limit period
            rate_limit_period: Rate limit period in seconds
            max_retries: Maximum number of retries for API calls
        """
        # Get API key from environment if not provided
        if api_key is None:
            api_key = os.getenv("CLAUDE_API_KEY")
        
        super().__init__(
            api_key=api_key,
            mock_mode=mock_mode,
            rate_limit_calls=rate_limit_calls,
            rate_limit_period=rate_limit_period,
            max_retries=max_retries
        )
        
        # Claude specific configuration
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Initialize Anthropic client if not in mock mode
        if not mock_mode and api_key:
            try:
                self.client = Anthropic(api_key=api_key)
                logger.info(f"Initialized Anthropic client with model {model}")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {str(e)}")
                self.client = None
        else:
            self.client = None
        
        # Mock response templates for different trust levels
        self.mock_responses = {
            "high_trust": {
                "viability_score": 88,
                "best_use_case": ["CPA", "Vault"],
                "risk_factors": ["limited post history", "no recent emails"],
                "maintenance_notes": "Verify email access before use. High-quality account with minimal risk factors."
            },
            "medium_trust": {
                "viability_score": 62,
                "best_use_case": ["Community Building"],
                "risk_factors": ["inconsistent posting pattern", "karma distribution uneven"],
                "maintenance_notes": "Build more comment history before deployment."
            },
            "low_trust": {
                "viability_score": 29,
                "best_use_case": ["Monitoring Only"],
                "risk_factors": ["suspicious account age", "karma farming detected", "unnatural activity spikes"],
                "maintenance_notes": "Not recommended for active operations."
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
        Analyze extracted content using Claude API.
        
        Args:
            content: Extracted content dictionary
            
        Returns:
            Dictionary with analysis results
            
        Raises:
            RateLimitExceeded: If API rate limit is exceeded
            APIError: If API call fails
        """
        if self.mock_mode or not self.client:
            return self._mock_analyze(content)
        
        if not self.api_key:
            logger.error("Claude API key not provided")
            raise APIError("Claude API key not provided")
        
        prompt = self._build_prompt(content)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system="You are an expert at analyzing Reddit accounts to determine their trustworthiness and potential use cases. You provide analysis in JSON format with specific required fields.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return self._parse_response(response.content)
            
        except RateLimitError as e:
            logger.warning(f"Claude API rate limit exceeded: {str(e)}")
            raise RateLimitExceeded(f"Claude API rate limit exceeded: {str(e)}")
        except AnthropicAPIError as e:
            logger.error(f"Claude API error: {str(e)}")
            raise APIError(f"Claude API error: {str(e)}")
        except Exception as e:
            logger.error(f"Claude API request failed: {str(e)}")
            raise APIError(f"Claude API request failed: {str(e)}")
    
    def _build_prompt(self, content: Dict[str, Any]) -> str:
        """
        Build prompt for Claude API based on extracted content.
        
        Args:
            content: Extracted content dictionary
            
        Returns:
            Formatted prompt string
        """
        # Format content for the prompt
        content_str = json.dumps(content, indent=2)
        
        return f"""
        Analyze the following Reddit persona data and provide a detailed assessment as JSON.
        
        Reddit Persona Data:
        {content_str}
        
        Analyze this Reddit account for:
        1. Overall trustworthiness and authenticity
        2. Potential use cases (CPA, Community Building, Influence Ops, Vault, Monitoring)
        3. Risk factors and red flags
        4. Recommended maintenance actions
        
        Respond with ONLY a JSON object having these exact fields:
        - viability_score (1-100): Overall trustworthiness score
        - best_use_case (array of strings): Top potential use cases
        - risk_factors (array of strings): Specific concerns or vulnerabilities
        - maintenance_notes (string): Recommendations for account maintenance
        
        No introduction, explanation, or additional text - ONLY the JSON object.
        """
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse and normalize response from Claude API.
        
        Args:
            response: Raw response from Claude API
            
        Returns:
            Normalized dictionary with analysis results
        """
        try:
            # Claude might include text around the JSON, so we need to extract just the JSON part
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON object found in response")
            
            json_str = response[json_start:json_end]
            
            # Parse the JSON
            content = json.loads(json_str)
            
            # Add next review date based on viability score
            review_days = 30 if content.get("viability_score", 0) > 80 else 7
            content["next_review_date"] = (
                datetime.now() + timedelta(days=review_days)
            ).strftime('%Y-%m-%d')
            
            return content
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse Claude response: {str(e)}")
            logger.debug(f"Raw response: {response}")
            
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
        
        # Customize based on specific account properties
        if content.get("is_mod", False):
            result["viability_score"] = min(100, result["viability_score"] + 8)
            if "risk_factors" in result:
                result["risk_factors"] = [f for f in result["risk_factors"] if f != "limited post history"]
        
        if content.get("recent_posts", []) and len(content.get("recent_posts", [])) < 5:
            if "risk_factors" in result and "limited post history" not in result["risk_factors"]:
                result["risk_factors"].append("limited post history")
        
        # Add next review date
        result["next_review_date"] = (
            datetime.now() + 
            timedelta(days=30 if result["viability_score"] > 80 else 7)
        ).strftime('%Y-%m-%d')
        
        return result
