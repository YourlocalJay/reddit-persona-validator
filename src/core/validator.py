"""
Core validator module for Reddit persona validation.

This module contains the main validation logic and orchestrates the validation process
by integrating browser automation, email verification, and AI analysis.
"""

from typing import Dict, List, Optional, Tuple, Union
import logging
from datetime import datetime

from src.core.browser_engine import BrowserEngine
from src.core.email_verifier import EmailVerifier
from src.analysis.scorer import TrustScorer
from src.analysis.deepseek_adapter import DeepseekAnalyzer
from src.analysis.claude_adapter import ClaudeAnalyzer
from src.utils.config_loader import ConfigLoader
from src.utils.proxy_rotator import ProxyRotator
from src.utils.cookie_manager import CookieManager

logger = logging.getLogger(__name__)

class RedditPersonaValidator:
    """Main validator class for Reddit persona validation."""
    
    def __init__(
        self, 
        config_path: str = "config/config.yaml",
        use_proxy: bool = True,
        ai_engine: str = "deepseek",
        debug_mode: bool = False
    ):
        """Initialize the validator with the required components.
        
        Args:
            config_path: Path to the configuration file
            use_proxy: Whether to use proxy rotation
            ai_engine: AI engine to use for analysis ("deepseek" or "claude")
            debug_mode: Enable debug logging and mock services
        """
        self.config = ConfigLoader(config_path).load()
        self.debug_mode = debug_mode
        self._setup_logging()
        
        # Initialize components
        self.cookie_manager = CookieManager(
            encryption_key=self.config["security"]["cookie_encryption_key"]
        )
        
        if use_proxy:
            self.proxy_rotator = ProxyRotator(
                proxy_list=self.config["proxies"]["proxy_list"],
                check_interval=self.config["proxies"]["health_check_interval"]
            )
            current_proxy = self.proxy_rotator.get_next_proxy()
        else:
            current_proxy = None
        
        self.browser = BrowserEngine(
            headless=not debug_mode,
            proxy=current_proxy,
            user_agent=self.config["browser"]["user_agent"],
            cookie_manager=self.cookie_manager
        )
        
        self.email_verifier = EmailVerifier(
            imap_server=self.config["email"]["imap_server"],
            port=self.config["email"]["imap_port"],
            use_ssl=self.config["email"]["use_ssl"]
        )
        
        # Initialize the appropriate AI analyzer
        if ai_engine.lower() == "claude":
            self.analyzer = ClaudeAnalyzer(
                api_key=self.config["ai"]["claude_api_key"],
                mock_mode=debug_mode
            )
        else:
            self.analyzer = DeepseekAnalyzer(
                api_key=self.config["ai"]["deepseek_api_key"],
                mock_mode=debug_mode
            )
        
        self.scorer = TrustScorer(
            karma_weight=self.config["scoring"]["karma_weight"],
            age_weight=self.config["scoring"]["age_weight"],
            email_weight=self.config["scoring"]["email_weight"],
            content_weight=self.config["scoring"]["content_weight"]
        )
    
    def _setup_logging(self) -> None:
        """Configure logging based on current settings."""
        log_level = logging.DEBUG if self.debug_mode else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def validate_reddit_account(
        self, 
        username: str, 
        password: Optional[str] = None,
        email_address: Optional[str] = None,
        email_password: Optional[str] = None,
        full_validation: bool = True
    ) -> Dict[str, Union[bool, float, Dict]]:
        """Validate a Reddit account and return a validation report.
        
        Args:
            username: Reddit username
            password: Reddit password (optional if cookies exist)
            email_address: Associated Hotmail email (for verification)
            email_password: Email password
            full_validation: Whether to perform full validation or just basic checks
            
        Returns:
            Dict containing validation results and trust score
        """
        logger.info(f"Starting validation for Reddit user: {username}")
        
        # Initialize results dict
        results = {
            "username": username,
            "timestamp": datetime.now().isoformat(),
            "validation_success": False,
            "trust_score": 0.0,
            "account_details": {},
            "email_verification": {
                "verified": False,
                "method": None
            },
            "content_analysis": {},
            "technical_details": {}
        }
        
        try:
            # Step 1: Reddit login and basic account data collection
            account_data = self._collect_account_data(username, password)
            results["account_details"] = account_data
            
            # Step 2: Email verification if credentials provided
            if email_address and email_password and full_validation:
                email_result = self._verify_email(
                    username, email_address, email_password
                )
                results["email_verification"] = email_result
            
            # Step 3: Content analysis
            if full_validation:
                post_urls = self._get_user_content_urls(username)
                content_analysis = self._analyze_user_content(post_urls)
                results["content_analysis"] = content_analysis
            
            # Step 4: Calculate trust score
            trust_score = self.scorer.calculate_score(
                karma=account_data.get("karma", 0),
                account_age_days=account_data.get("age_days", 0),
                email_verified=results["email_verification"]["verified"],
                content_score=results["content_analysis"].get("authenticity_score", 0)
            )
            results["trust_score"] = trust_score
            results["validation_success"] = True
            
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            results["error"] = str(e)
            results["technical_details"]["error_trace"] = logging.format_exc()
        
        # Handle proxy rotation or failures
        if hasattr(self, 'proxy_rotator') and self.browser.proxy_blocked:
            self.proxy_rotator.mark_proxy_bad(self.browser.current_proxy)
            results["technical_details"]["proxy_rotated"] = True
        
        # Save cookies if available
        if self.browser.has_session_cookies:
            self.cookie_manager.save_cookies(
                username, self.browser.get_cookies()
            )
        
        logger.info(f"Validation completed for {username}. Score: {results['trust_score']}")
        return results
    
    def _collect_account_data(
        self, 
        username: str, 
        password: Optional[str]
    ) -> Dict[str, Union[int, str, float]]:
        """Collect basic account data from Reddit.
        
        Args:
            username: Reddit username
            password: Reddit password (optional if cookies exist)
            
        Returns:
            Dict with account details
        """
        logger.info(f"Collecting account data for {username}")
        
        # Try to use saved cookies first
        cookies = self.cookie_manager.load_cookies(username)
        if cookies:
            self.browser.set_cookies(cookies)
            if self.browser.check_reddit_login():
                logger.info("Using saved session cookies")
            else:
                logger.info("Saved cookies expired, will login with credentials")
                cookies = None
        
        # Login if needed
        if not cookies and password:
            self.browser.login_to_reddit(username, password)
        elif not cookies and not password:
            raise ValueError("No valid cookies and no password provided")
        
        # Scrape account details
        profile_data = self.browser.scrape_reddit_profile(username)
        
        return {
            "username": username,
            "karma": profile_data["karma"],
            "age_days": profile_data["account_age_days"],
            "verified_email": profile_data["has_verified_email"],
            "avatar_url": profile_data.get("avatar_url"),
            "is_premium": profile_data.get("is_premium", False),
            "badges": profile_data.get("badges", [])
        }
    
    def _verify_email(
        self, 
        username: str, 
        email: str, 
        password: str
    ) -> Dict[str, Union[bool, str]]:
        """Verify the association between Reddit account and email.
        
        Args:
            username: Reddit username
            email: Email address (Hotmail/Outlook)
            password: Email password
            
        Returns:
            Dict with verification results
        """
        logger.info(f"Verifying email association for {username}")
        
        # Initialize result
        result = {
            "verified": False,
            "method": None,
            "details": {}
        }
        
        # First try to find verification emails
        self.email_verifier.login(email, password)
        reddit_emails = self.email_verifier.find_emails(
            sender="noreply@reddit.com",
            days_back=30
        )
        
        if reddit_emails:
            logger.info(f"Found {len(reddit_emails)} Reddit emails")
            result["verified"] = True
            result["method"] = "existing_emails"
            result["details"]["email_count"] = len(reddit_emails)
            result["details"]["latest_email_date"] = reddit_emails[0]["date"]
            return result
        
        # If no emails found, try to trigger a password reset
        logger.info("No verification emails found, attempting password reset")
        reset_success = self.browser.trigger_password_reset(username)
        
        if reset_success:
            # Wait for the email to arrive
            reset_email = self.email_verifier.wait_for_email(
                sender="noreply@reddit.com",
                subject_contains="reset your password",
                timeout_seconds=60
            )
            
            if reset_email:
                result["verified"] = True
                result["method"] = "password_reset"
                result["details"]["reset_email_date"] = reset_email["date"]
            else:
                result["method"] = "password_reset_attempted"
                result["details"]["reset_triggered"] = True
                result["details"]["email_received"] = False
        
        self.email_verifier.logout()
        return result
    
    def _get_user_content_urls(self, username: str) -> List[str]:
        """Get URLs for the user's recent posts and comments.
        
        Args:
            username: Reddit username
            
        Returns:
            List of URLs to analyze
        """
        logger.info(f"Collecting content URLs for {username}")
        content_limit = self.config["analysis"]["content_sample_size"]
        return self.browser.get_user_content_urls(username, limit=content_limit)
    
    def _analyze_user_content(self, urls: List[str]) -> Dict[str, Union[float, Dict]]:
        """Analyze user content using the selected AI engine.
        
        Args:
            urls: List of content URLs to analyze
            
        Returns:
            Dict with analysis results
        """
        logger.info(f"Analyzing {len(urls)} content items")
        
        content_texts = []
        for url in urls:
            try:
                content = self.browser.extract_content_from_url(url)
                if content:
                    content_texts.append(content)
            except Exception as e:
                logger.warning(f"Failed to extract content from {url}: {str(e)}")
        
        if not content_texts:
            logger.warning("No content found to analyze")
            return {"authenticity_score": 0, "error": "No content available"}
        
        analysis_result = self.analyzer.analyze_content(content_texts)
        return analysis_result
    
    def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up resources")
        if self.browser:
            self.browser.close()
        if hasattr(self, 'email_verifier'):
            self.email_verifier.close()
