"""Main validation logic for Reddit persona verification."""

import os
import time
import logging
import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any, Union, Type
from dataclasses import dataclass

from ..utils.proxy_rotator import ProxyRotator
from ..utils.cookie_manager import CookieManager
from .browser_engine import BrowserEngine
from .email_verifier import EmailVerifier, VerificationResult
from ..analysis.scorer import PersonaScorer
from ..analysis.base_analyzer import BaseAnalyzer
from ..analysis.deepseek_analyzer import DeepSeekAnalyzer
from ..analysis.claude_analyzer import ClaudeAnalyzer
from ..analysis.mock_analyzer import MockAnalyzer

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Structured result of the validation process."""
    username: str
    exists: bool
    trust_score: Optional[float] = None
    account_details: Optional[Dict[str, Any]] = None
    email_verified: Optional[bool] = None
    email_details: Optional[Dict[str, Any]] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "username": self.username,
            "exists": self.exists,
            "trust_score": self.trust_score,
            "account_details": self.account_details,
            "email_verified": self.email_verified,
            "email_details": self.email_details,
            "ai_analysis": self.ai_analysis,
            "errors": self.errors or [],
            "warnings": self.warnings or []
        }

class RedditPersonaValidator:
    """
    Core validator module for Reddit persona validation with:
    - Reddit account analysis
    - Email verification
    - AI-powered content analysis
    - Trust score calculation

    This module orchestrates all validation components and provides
    a unified interface for validating Reddit personas.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize validator with configuration.

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)

        # Initialize dependencies
        self.proxy_rotator = self._init_proxy_rotator()
        self.browser_engine = None  # Lazy initialization
        self.email_verifier = None  # Lazy initialization
        self.persona_scorer = None  # Lazy initialization

        # Set up logging
        log_level = self.config.get("interface", {}).get("cli", {}).get("log_level", "INFO")
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        logger.info("Reddit Persona Validator initialized")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to configuration file

        Returns:
            Dict containing configuration

        Raises:
            FileNotFoundError: If config file not found
            yaml.YAMLError: If config file is invalid
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")

            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            return config
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise

    def _init_proxy_rotator(self) -> Optional[ProxyRotator]:
        """Initialize proxy rotator if configured."""
        try:
            proxy_config = self.config.get("proxy", {})
            if not proxy_config:
                logger.info("No proxy configuration found, running without proxies")
                return None

            return ProxyRotator(proxy_config)
        except Exception as e:
            logger.warning(f"Failed to initialize proxy rotator: {str(e)}")
            return None

    def _init_browser_engine(self) -> BrowserEngine:
        """Lazy initialization of browser engine."""
        if self.browser_engine is None:
            browser_config = self.config.get("reddit", {})
            self.browser_engine = BrowserEngine(
                config=browser_config,
                proxy_rotator=self.proxy_rotator
            )
        return self.browser_engine

    def _init_email_verifier(self) -> EmailVerifier:
        """Lazy initialization of email verifier."""
        if self.email_verifier is None:
            email_config = self.config.get("email", {})
            self.email_verifier = EmailVerifier(email_config)
        return self.email_verifier

    def _init_persona_scorer(self) -> PersonaScorer:
        """
        Lazy initialization of persona scorer with AI configuration.

        Returns:
            Configured PersonaScorer instance
        """
        if self.persona_scorer is None:
            # Get analysis configuration
            analysis_config = self.config.get("analysis", {})
            ai_config = self.config.get("ai", {})

            # Determine analyzer type and fallback
            analyzer_type = ai_config.get("default_analyzer") or analysis_config.get("default_analyzer", "deepseek")
            fallback_analyzer = ai_config.get("fallback_analyzer", "mock")
            mock_mode = analysis_config.get("mock_mode", False)

            # Extract scoring weights
            scoring_weights = ai_config.get("weights", {})

            # Configure caching
            cache_enabled = ai_config.get("cache_results", False) or analysis_config.get("cache_enabled", False)
            cache_expiry = ai_config.get("cache_expiry", 86400)  # Default: 24 hours

            # Initialize scorer with configuration
            self.persona_scorer = PersonaScorer(
                analyzer_type=analyzer_type,
                mock_mode=mock_mode,
                fallback_analyzer=fallback_analyzer,
                scoring_weights=scoring_weights
            )

            # Configure additional options
            if hasattr(self.persona_scorer, "set_cache_options") and callable(getattr(self.persona_scorer, "set_cache_options")):
                self.persona_scorer.set_cache_options(
                    enabled=cache_enabled,
                    expiry=cache_expiry,
                    cache_dir=analysis_config.get("cache_dir", ".cache/analysis")
                )

            logger.info(f"Initialized PersonaScorer with {analyzer_type} analyzer (fallback: {fallback_analyzer})")

        return self.persona_scorer

    def validate(self,
                username: str,
                email_address: Optional[str] = None,
                perform_email_verification: bool = False,
                perform_ai_analysis: bool = True,
                ai_analyzer_type: Optional[str] = None,
                ai_detail_level: str = "medium") -> ValidationResult:
        """
        Perform comprehensive validation of a Reddit persona.

        Args:
            username: Reddit username to validate
            email_address: Email address for verification (optional)
            perform_email_verification: Whether to verify email
            perform_ai_analysis: Whether to perform AI analysis
            ai_analyzer_type: Specific AI analyzer to use (overrides config)
            ai_detail_level: Level of AI analysis detail (none, basic, medium, full)

        Returns:
            ValidationResult containing all validation results
        """
        logger.info(f"Starting validation for username: {username}")
        if ai_analyzer_type:
            logger.info(f"Using AI analyzer override: {ai_analyzer_type}")

        result = ValidationResult(
            username=username,
            exists=False,
            errors=[],
            warnings=[]
        )

        try:
            # 1. Extract Reddit account info
            account_info = self._extract_account_info(username)

            if not account_info.get("exists", False):
                result.errors.append(f"Reddit account '{username}' does not exist")
                return result

            result.exists = True
            result.account_details = account_info
            # Add warnings from account_info if present
            if "warnings" in account_info:
                result.warnings.extend(account_info["warnings"])

            # 2. Verify email if requested
            if perform_email_verification and email_address:
                email_result = self._verify_email(username, email_address)
                result.email_verified = email_result.verified
                result.email_details = {
                    "email": email_result.email,
                    "verified": email_result.verified,
                    "verification_time": email_result.verification_time,
                    "verification_id": email_result.verification_id,
                    "error": email_result.error
                }

                if not email_result.verified:
                    result.warnings.append(f"Email verification failed: {email_result.error}")

            # 3. Perform AI analysis if requested
            ai_enabled = self.config.get("ai", {}).get("enabled", True)
            ai_analysis_result = None
            if perform_ai_analysis and ai_enabled:
                # Override analyzer type if specified
                if ai_analyzer_type:
                    if hasattr(self.persona_scorer, "analyzer_type"):
                        original_analyzer_type = self.persona_scorer.analyzer_type
                        self.persona_scorer.analyzer_type = ai_analyzer_type

                # Perform analysis with specified detail level
                analysis_result = self._analyze_persona(
                    account_info,
                    detail_level=ai_detail_level
                )
                result.ai_analysis = analysis_result.get("ai_analysis")
                ai_analysis_result = result.ai_analysis
                # If AI analysis failed, add warning
                if ai_analysis_result and "error" in ai_analysis_result:
                    result.warnings.append(f"AI analysis failed: {ai_analysis_result.get('error')}")

                # Restore original analyzer type if it was overridden
                if ai_analyzer_type and hasattr(self.persona_scorer, "analyzer_type"):
                    self.persona_scorer.analyzer_type = original_analyzer_type

            # 4. Calculate final trust score (always run, regardless of AI analysis success)
            trust_score = self._calculate_trust_score(
                account_info,
                email_verified=result.email_verified,
                ai_score=(result.ai_analysis.get("viability_score") if result.ai_analysis else None),
                ai_analysis=result.ai_analysis
            )
            result.trust_score = trust_score

            logger.info(f"Validation completed for {username}")
            return result

        except Exception as e:
            logger.error(f"Validation failed: {str(e)}", exc_info=True)
            result.errors.append(f"Validation error: {str(e)}")
            return result
        finally:
            # Clean up resources
            self._cleanup()

    def _extract_account_info(self, username: str) -> Dict[str, Any]:
        """
        Extract account information from Reddit.

        Args:
            username: Reddit username

        Returns:
            Dictionary with account metrics
        """
        logger.info(f"Extracting account info for {username}")

        try:
            browser = self._init_browser_engine()
            with browser:
                account_info = browser.extract_account_info(username)

            # Convert karma to int if possible
            if account_info.get("karma") and isinstance(account_info["karma"], str):
                try:
                    account_info["karma"] = int(account_info["karma"])
                except ValueError:
                    pass

            # Check account age against threshold
            min_age = self.config.get("scoring", {}).get("min_account_age_days", 30)
            if account_info.get("age_days", 0) < min_age:
                account_info["warnings"] = account_info.get("warnings", [])
                account_info["warnings"].append(f"Account age below threshold ({min_age} days)")

            # Check karma against threshold
            min_karma = self.config.get("scoring", {}).get("min_karma", 100)
            if account_info.get("karma", 0) < min_karma:
                account_info["warnings"] = account_info.get("warnings", [])
                account_info["warnings"].append(f"Account karma below threshold ({min_karma})")

            return account_info

        except Exception as e:
            logger.error(f"Failed to extract account info: {str(e)}", exc_info=True)
            return {"exists": False, "error": str(e)}

    def _verify_email(self, username: str, email_address: str) -> VerificationResult:
        """
        Verify email ownership using the email verifier.

        Args:
            username: Reddit username
            email_address: Email address to verify

        Returns:
            VerificationResult containing verification status
        """
        logger.info(f"Verifying email for {username}: {email_address}")

        try:
            verifier = self._init_email_verifier()
            with verifier:
                result = verifier.verify_reddit_account(
                    username=username,
                    email_address=email_address,
                    wait_for_verification=True
                )
            return result
        except Exception as e:
            logger.error(f"Email verification failed: {str(e)}", exc_info=True)
            return VerificationResult(
                verified=False,
                email=email_address,
                reddit_username=username,
                error=str(e)
            )

    def _analyze_persona(self,
                        account_info: Dict[str, Any],
                        detail_level: str = "medium") -> Dict[str, Any]:
        """
        Perform AI analysis of the persona with configurable detail level.

        Args:
            account_info: Account information dictionary
            detail_level: Level of AI analysis detail (none, basic, medium, full)

        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Performing AI analysis for {account_info.get('username')} (detail: {detail_level})")

        try:
            # Initialize the scorer
            scorer = self._init_persona_scorer()

            # Get analysis configuration
            analysis_config = self.config.get("analysis", {})

            # Extract content sample limit based on detail level
            content_samples = {
                "none": 0,
                "basic": 3,
                "medium": 10,
                "full": 25
            }.get(detail_level.lower(), 10)

            # Override with config if specified
            if analysis_config.get("content_samples") and detail_level.lower() != "none":
                content_samples = min(
                    content_samples,
                    int(analysis_config.get("content_samples", 10))
                )

            # Get user behavior metrics to analyze
            user_behavior_metrics = analysis_config.get("user_behavior_metrics", [])

            # Configure analysis options
            analysis_options = {
                "detail_level": detail_level,
                "content_samples": content_samples,
                "behavior_metrics": user_behavior_metrics,
                "sensitive_content_detection": analysis_config.get("sensitive_content_detection", True)
            }

            # Perform analysis with options
            if hasattr(scorer, "calculate_trust_score_with_options"):
                return scorer.calculate_trust_score_with_options(account_info, analysis_options)
            else:
                return scorer.calculate_trust_score(account_info)

        except Exception as e:
            logger.error(f"AI analysis failed: {str(e)}", exc_info=True)
            return {
                "error": str(e),
                "ai_analysis": {
                    "error": str(e),
                    "viability_score": 0
                }
            }

    def _calculate_trust_score(self,
                              account_info: Dict[str, Any],
                              email_verified: Optional[bool] = None,
                              ai_score: Optional[float] = None,
                              ai_analysis: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculate final trust score based on all validation factors.

        Args:
            account_info: Account information dictionary
            email_verified: Whether email was verified
            ai_score: AI analysis viability score
            ai_analysis: Complete AI analysis results

        Returns:
            Trust score between 0 and 100
        """
        # Load scoring weights from config
        scoring_config = self.config.get("scoring", {})
        email_weight = scoring_config.get("email_verification_weight", 0.3)
        age_weight = scoring_config.get("account_age_weight", 0.2)
        karma_weight = scoring_config.get("karma_weight", 0.2)
        ai_weight = scoring_config.get("ai_analysis_weight", 0.3)

        # Calculate base scores
        email_score = 100 if email_verified else 0

        # Age score: 100 if >= 365 days, proportional otherwise
        age_days = account_info.get("age_days", 0)
        age_score = min(100, (age_days / 365) * 100)

        # Karma score: 100 if >= 10000, proportional otherwise
        karma = account_info.get("karma", 0)
        karma_score = min(100, (karma / 10000) * 100)

        # Calculate AI component score if available
        ai_component_score = 0
        if ai_score is not None:
            ai_component_score = ai_score
        elif ai_analysis:
            # Extract component scores if available
            component_scores = []
            if "content_coherence" in ai_analysis:
                component_scores.append(ai_analysis["content_coherence"])
            if "language_quality" in ai_analysis:
                component_scores.append(ai_analysis["language_quality"])
            if "account_consistency" in ai_analysis:
                component_scores.append(ai_analysis["account_consistency"])
            if "behavioral_patterns" in ai_analysis:
                component_scores.append(ai_analysis["behavioral_patterns"])

            # Calculate average of available component scores
            if component_scores:
                ai_component_score = sum(component_scores) / len(component_scores)

        # Calculate weighted score
        if ai_score is not None or ai_analysis:
            # Include AI component in weighted score
            final_score = (
                email_score * email_weight +
                age_score * age_weight +
                karma_score * karma_weight +
                ai_component_score * ai_weight
            )
        else:
            # No AI analysis, adjust weights
            adjusted_email_weight = email_weight / (email_weight + age_weight + karma_weight)
            adjusted_age_weight = age_weight / (email_weight + age_weight + karma_weight)
            adjusted_karma_weight = karma_weight / (email_weight + age_weight + karma_weight)

            final_score = (
                email_score * adjusted_email_weight +
                age_score * adjusted_age_weight +
                karma_score * adjusted_karma_weight
            )

        return round(final_score, 1)

    def _cleanup(self) -> None:
        """Clean up resources after validation."""
        try:
            if self.browser_engine:
                self.browser_engine.close()

            if self.email_verifier and hasattr(self.email_verifier, 'is_connected') and self.email_verifier.is_connected:
                self.email_verifier.disconnect()

        except Exception as e:
            logger.warning(f"Cleanup error: {str(e)}")
