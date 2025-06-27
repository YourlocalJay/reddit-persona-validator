"""Integration test for end-to-end Reddit persona validation."""

import unittest
import logging
import os
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add src directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.core.validator import RedditPersonaValidator, ValidationResult
from src.core.browser_engine import BrowserEngine
from src.core.email_verifier import EmailVerifier, VerificationResult
from src.analysis.scorer import PersonaScorer


class TestEndToEndValidation(unittest.TestCase):
    """
    Integration test for the complete Reddit persona validation process.
    Uses mocks for external dependencies to avoid actual network calls.
    """
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once for all tests."""
        # Disable logging output during tests
        logging.disable(logging.CRITICAL)
        
        # Ensure config file exists
        cls.config_path = "config/config.yaml"
        if not Path(cls.config_path).exists():
            raise FileNotFoundError(f"Config file not found: {cls.config_path}")
        
        # Sample test data
        cls.test_usernames = {
            "high_trust": "established_user",
            "medium_trust": "average_user",
            "low_trust": "new_user",
            "nonexistent": "nonexistent_user"
        }
        
        cls.test_email = "test@example.com"
    
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        # Re-enable logging
        logging.disable(logging.NOTSET)
    
    def setUp(self):
        """Set up before each test."""
        # Create mock account data
        self.account_data = {
            "established_user": {
                "username": "established_user",
                "exists": True,
                "karma": 25000,
                "age_days": 1825,  # 5 years
                "verified": True,
                "moderator": True,
                "trophies": ["5-Year Club", "Verified Email", "Moderator"],
                "communities": ["Python", "DataScience", "MachineLearning"]
            },
            "average_user": {
                "username": "average_user",
                "exists": True,
                "karma": 3500,
                "age_days": 365,  # 1 year
                "verified": True,
                "moderator": False,
                "trophies": ["1-Year Club", "Verified Email"],
                "communities": ["AskReddit", "funny", "gaming"]
            },
            "new_user": {
                "username": "new_user",
                "exists": True,
                "karma": 50,
                "age_days": 15,
                "verified": False,
                "moderator": False,
                "trophies": [],
                "communities": ["AskReddit"]
            },
            "nonexistent_user": {
                "username": "nonexistent_user",
                "exists": False,
                "error": "Account not found"
            }
        }
        
        # Create mock email verification results
        self.email_results = {
            "established_user": VerificationResult(
                verified=True,
                email=self.test_email,
                reddit_username="established_user",
                verification_time="2025-01-15T10:30:00",
                verification_id="abc123"
            ),
            "average_user": VerificationResult(
                verified=True,
                email=self.test_email,
                reddit_username="average_user",
                verification_time="2025-06-01T14:22:15",
                verification_id="def456"
            ),
            "new_user": VerificationResult(
                verified=False,
                email=self.test_email,
                reddit_username="new_user",
                error="No verification email found"
            )
        }
        
        # Create mock AI analysis results
        self.ai_results = {
            "established_user": {
                "trust_score": 92,
                "ai_analysis": {
                    "viability_score": 95,
                    "best_use_case": ["CPA", "Influence Ops", "Vault"],
                    "risk_factors": ["none detected"],
                    "maintenance_notes": "Prime for immediate use",
                    "next_review_date": "2025-07-20"
                }
            },
            "average_user": {
                "trust_score": 75,
                "ai_analysis": {
                    "viability_score": 70,
                    "best_use_case": ["CPA", "Community Building"],
                    "risk_factors": ["medium posting frequency"],
                    "maintenance_notes": "Regular engagement required",
                    "next_review_date": "2025-07-05"
                }
            },
            "new_user": {
                "trust_score": 35,
                "ai_analysis": {
                    "viability_score": 30,
                    "best_use_case": ["Community Building"],
                    "risk_factors": ["low karma", "new account", "limited history"],
                    "maintenance_notes": "Needs significant karma building",
                    "next_review_date": "2025-06-30"
                }
            }
        }
    
    @patch('src.core.browser_engine.BrowserEngine')
    @patch('src.core.email_verifier.EmailVerifier')
    @patch('src.analysis.scorer.PersonaScorer')
    def test_high_trust_user_validation(self, mock_scorer, mock_email_verifier, mock_browser):
        """Test validation of a high-trust user with all verification steps."""
        self._setup_mocks(
            mock_browser, 
            mock_email_verifier, 
            mock_scorer, 
            "established_user"
        )
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username=self.test_usernames["high_trust"],
            email_address=self.test_email,
            perform_email_verification=True,
            perform_ai_analysis=True
        )
        
        # Verify result
        self.assertTrue(result.exists)
        self.assertTrue(result.email_verified)
        self.assertGreaterEqual(result.trust_score, 90)  # High trust score
        self.assertEqual(result.account_details["karma"], 25000)
        self.assertEqual(result.email_details["email"], self.test_email)
        self.assertEqual(result.ai_analysis["viability_score"], 95)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)
    
    @patch('src.core.browser_engine.BrowserEngine')
    @patch('src.core.email_verifier.EmailVerifier')
    @patch('src.analysis.scorer.PersonaScorer')
    def test_medium_trust_user_validation(self, mock_scorer, mock_email_verifier, mock_browser):
        """Test validation of a medium-trust user with all verification steps."""
        self._setup_mocks(
            mock_browser, 
            mock_email_verifier, 
            mock_scorer, 
            "average_user"
        )
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username=self.test_usernames["medium_trust"],
            email_address=self.test_email,
            perform_email_verification=True,
            perform_ai_analysis=True
        )
        
        # Verify result
        self.assertTrue(result.exists)
        self.assertTrue(result.email_verified)
        self.assertGreaterEqual(result.trust_score, 60)  # Medium trust score
        self.assertLess(result.trust_score, 90)  # But less than high trust
        self.assertEqual(result.account_details["karma"], 3500)
        self.assertEqual(result.email_details["email"], self.test_email)
        self.assertEqual(result.ai_analysis["viability_score"], 70)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)
    
    @patch('src.core.browser_engine.BrowserEngine')
    @patch('src.core.email_verifier.EmailVerifier')
    @patch('src.analysis.scorer.PersonaScorer')
    def test_low_trust_user_validation(self, mock_scorer, mock_email_verifier, mock_browser):
        """Test validation of a low-trust user with all verification steps."""
        self._setup_mocks(
            mock_browser, 
            mock_email_verifier, 
            mock_scorer, 
            "new_user"
        )
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username=self.test_usernames["low_trust"],
            email_address=self.test_email,
            perform_email_verification=True,
            perform_ai_analysis=True
        )
        
        # Verify result
        self.assertTrue(result.exists)
        self.assertFalse(result.email_verified)  # Email verification should fail
        self.assertLess(result.trust_score, 50)  # Low trust score
        self.assertEqual(result.account_details["karma"], 50)
        self.assertEqual(result.email_details["email"], self.test_email)
        self.assertEqual(result.ai_analysis["viability_score"], 30)
        self.assertEqual(len(result.errors), 0)
        self.assertGreater(len(result.warnings), 0)  # Should have warnings
    
    @patch('src.core.browser_engine.BrowserEngine')
    def test_nonexistent_user_validation(self, mock_browser):
        """Test validation of a nonexistent user."""
        # Setup mock for nonexistent user
        mock_instance = mock_browser.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.extract_account_info.return_value = self.account_data["nonexistent_user"]
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username=self.test_usernames["nonexistent"],
            perform_email_verification=False,
            perform_ai_analysis=False
        )
        
        # Verify result
        self.assertFalse(result.exists)
        self.assertIsNone(result.trust_score)
        self.assertIsNone(result.email_verified)
        self.assertIsNone(result.ai_analysis)
        self.assertEqual(len(result.errors), 1)
    
    @patch('src.core.browser_engine.BrowserEngine')
    def test_validation_without_email_verification(self, mock_browser):
        """Test validation without email verification step."""
        # Setup mocks
        mock_instance = mock_browser.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.extract_account_info.return_value = self.account_data["average_user"]
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        
        # Patch the analyze_persona method to return expected result
        with patch.object(validator, '_analyze_persona', return_value=self.ai_results["average_user"]):
            result = validator.validate(
                username=self.test_usernames["medium_trust"],
                perform_email_verification=False,  # Skip email verification
                perform_ai_analysis=True
            )
        
        # Verify result
        self.assertTrue(result.exists)
        self.assertIsNone(result.email_verified)  # Should be None (not performed)
        self.assertIsNotNone(result.trust_score)
        self.assertIsNotNone(result.ai_analysis)
    
    @patch('src.core.browser_engine.BrowserEngine')
    @patch('src.core.email_verifier.EmailVerifier')
    def test_validation_without_ai_analysis(self, mock_email_verifier, mock_browser):
        """Test validation without AI analysis step."""
        # Setup mocks
        browser_instance = mock_browser.return_value
        browser_instance.__enter__.return_value = browser_instance
        browser_instance.extract_account_info.return_value = self.account_data["average_user"]
        
        email_instance = mock_email_verifier.return_value
        email_instance.__enter__.return_value = email_instance
        email_instance.verify_reddit_account.return_value = self.email_results["average_user"]
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username=self.test_usernames["medium_trust"],
            email_address=self.test_email,
            perform_email_verification=True,
            perform_ai_analysis=False  # Skip AI analysis
        )
        
        # Verify result
        self.assertTrue(result.exists)
        self.assertTrue(result.email_verified)
        self.assertIsNone(result.trust_score)  # Should be None (not calculated)
        self.assertIsNone(result.ai_analysis)  # Should be None (not performed)
    
    @patch('src.core.validator.RedditPersonaValidator._extract_account_info')
    def test_validation_with_exception(self, mock_extract):
        """Test validation when an exception occurs."""
        mock_extract.side_effect = Exception("Simulated network failure")
        
        # Create validator and run validation
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username=self.test_usernames["high_trust"],
            perform_email_verification=False,
            perform_ai_analysis=False
        )
        
        # Verify result
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Simulated network failure", result.errors[0])
    
    def _setup_mocks(self, mock_browser, mock_email_verifier, mock_scorer, username):
        """Helper to set up all mocks for a specific user."""
        # Set up browser mock
        browser_instance = mock_browser.return_value
        browser_instance.__enter__.return_value = browser_instance
        browser_instance.extract_account_info.return_value = self.account_data[username]
        
        # Set up email verifier mock if username exists
        if username in self.email_results:
            email_instance = mock_email_verifier.return_value
            email_instance.__enter__.return_value = email_instance
            email_instance.verify_reddit_account.return_value = self.email_results[username]
        
        # Set up scorer mock if username exists
        if username in self.ai_results:
            scorer_instance = mock_scorer.return_value
            scorer_instance.calculate_trust_score.return_value = self.ai_results[username]


if __name__ == "__main__":
    unittest.main()
