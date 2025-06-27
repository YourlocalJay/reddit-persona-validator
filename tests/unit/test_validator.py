"""Unit tests for the RedditPersonaValidator."""

import unittest
from unittest.mock import patch, Mock, MagicMock
import tempfile
import os
import yaml
import json
from pathlib import Path

from src.core.validator import RedditPersonaValidator, ValidationResult
from src.core.email_verifier import VerificationResult
from src.utils.proxy_rotator import ProxyRotator
from src.core.browser_engine import BrowserEngine
from src.analysis.scorer import PersonaScorer


class TestRedditPersonaValidator(unittest.TestCase):
    """Test suite for the RedditPersonaValidator class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temporary config file
        self.temp_config_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_config_dir.name, "config.yaml")
        
        # Sample configuration for testing
        self.test_config = {
            "reddit": {
                "user_agent": "TestValidator/1.0",
                "request_timeout": 10,
                "captcha_timeout": 10
            },
            "email": {
                "imap_server": "test.example.com",
                "imap_port": 993,
                "connection_timeout": 5,
                "verification_timeout": 10
            },
            "proxy": {
                "rotation_interval": 60,
                "health_check_interval": 30
            },
            "scoring": {
                "min_account_age_days": 10,
                "min_karma": 50,
                "email_verification_weight": 0.4,
                "account_age_weight": 0.3,
                "karma_weight": 0.3,
                "trust_threshold": 0.7
            },
            "analysis": {
                "default_analyzer": "deepseek",
                "mock_mode": True
            },
            "interface": {
                "cli": {
                    "log_level": "ERROR"  # Minimize test output
                }
            }
        }
        
        with open(self.config_path, 'w') as f:
            yaml.dump(self.test_config, f)
        
        # Sample test data
        self.valid_account_info = {
            "username": "test_user",
            "exists": True,
            "karma": 5000,
            "age_days": 180,
            "verified": True,
            "moderator": False,
            "trophies": ["1-Year Club"],
            "communities": ["AskReddit", "Python"]
        }
        
        self.invalid_account_info = {
            "username": "nonexistent_user",
            "exists": False,
            "error": "Account not found"
        }
        
        self.email_verification_success = VerificationResult(
            verified=True,
            email="user@example.com",
            reddit_username="test_user",
            verification_time="2025-06-10T12:34:56",
            verification_id="abc123"
        )
        
        self.email_verification_failure = VerificationResult(
            verified=False,
            email="user@example.com",
            reddit_username="test_user",
            error="Verification timed out"
        )
        
        self.ai_analysis_result = {
            "trust_score": 75,
            "ai_analysis": {
                "viability_score": 85,
                "best_use_case": ["CPA", "Vault"],
                "risk_factors": ["no recent emails"],
                "maintenance_notes": "Verify email access before use",
                "next_review_date": "2025-07-10"
            }
        }
    
    def tearDown(self):
        """Clean up after tests."""
        self.temp_config_dir.cleanup()
    
    @patch('src.utils.proxy_rotator.ProxyRotator')
    def test_initialization(self, mock_proxy_rotator):
        """Test validator initialization and config loading."""
        validator = RedditPersonaValidator(config_path=self.config_path)
        
        # Verify config loaded correctly
        self.assertEqual(validator.config['reddit']['user_agent'], "TestValidator/1.0")
        self.assertEqual(validator.config['scoring']['min_karma'], 50)
        
        # Verify proxy rotator initialized
        mock_proxy_rotator.assert_called_once()
        
        # Verify lazy initialization (should be None until used)
        self.assertIsNone(validator.browser_engine)
        self.assertIsNone(validator.email_verifier)
        self.assertIsNone(validator.persona_scorer)
    
    def test_load_invalid_config(self):
        """Test handling of invalid config file."""
        # Non-existent config file
        with self.assertRaises(FileNotFoundError):
            RedditPersonaValidator(config_path="nonexistent_config.yaml")
        
        # Invalid YAML
        invalid_config_path = os.path.join(self.temp_config_dir.name, "invalid.yaml")
        with open(invalid_config_path, 'w') as f:
            f.write("invalid: yaml: content:")
        
        with self.assertRaises(yaml.YAMLError):
            RedditPersonaValidator(config_path=invalid_config_path)
    
    @patch('src.core.browser_engine.BrowserEngine')
    def test_extract_account_info_success(self, mock_browser):
        """Test extraction of account info when successful."""
        mock_instance = mock_browser.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.extract_account_info.return_value = self.valid_account_info
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._extract_account_info("test_user")
        
        self.assertTrue(result["exists"])
        self.assertEqual(result["karma"], 5000)
        self.assertEqual(result["username"], "test_user")
        
        # Verify browser engine was called with correct username
        mock_instance.extract_account_info.assert_called_once_with("test_user")
    
    @patch('src.core.browser_engine.BrowserEngine')
    def test_extract_account_info_failure(self, mock_browser):
        """Test extraction of account info when account doesn't exist."""
        mock_instance = mock_browser.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.extract_account_info.return_value = self.invalid_account_info
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._extract_account_info("nonexistent_user")
        
        self.assertFalse(result["exists"])
        self.assertEqual(result["error"], "Account not found")
    
    @patch('src.core.browser_engine.BrowserEngine')
    def test_extract_account_info_exception(self, mock_browser):
        """Test extraction of account info when an exception occurs."""
        mock_instance = mock_browser.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.extract_account_info.side_effect = Exception("Browser error")
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._extract_account_info("test_user")
        
        self.assertFalse(result["exists"])
        self.assertEqual(result["error"], "Browser error")
    
    @patch('src.core.email_verifier.EmailVerifier')
    def test_verify_email_success(self, mock_email_verifier):
        """Test email verification when successful."""
        mock_instance = mock_email_verifier.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.verify_reddit_account.return_value = self.email_verification_success
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._verify_email("test_user", "user@example.com")
        
        self.assertTrue(result.verified)
        self.assertEqual(result.email, "user@example.com")
        self.assertEqual(result.verification_time, "2025-06-10T12:34:56")
        
        # Verify email verifier was called with correct parameters
        mock_instance.verify_reddit_account.assert_called_once_with(
            username="test_user",
            email_address="user@example.com",
            wait_for_verification=True
        )
    
    @patch('src.core.email_verifier.EmailVerifier')
    def test_verify_email_failure(self, mock_email_verifier):
        """Test email verification when it fails."""
        mock_instance = mock_email_verifier.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.verify_reddit_account.return_value = self.email_verification_failure
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._verify_email("test_user", "user@example.com")
        
        self.assertFalse(result.verified)
        self.assertEqual(result.error, "Verification timed out")
    
    @patch('src.core.email_verifier.EmailVerifier')
    def test_verify_email_exception(self, mock_email_verifier):
        """Test email verification when an exception occurs."""
        mock_instance = mock_email_verifier.return_value
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.verify_reddit_account.side_effect = Exception("IMAP error")
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._verify_email("test_user", "user@example.com")
        
        self.assertFalse(result.verified)
        self.assertEqual(result.error, "IMAP error")
    
    @patch('src.analysis.scorer.PersonaScorer')
    def test_analyze_persona_success(self, mock_scorer):
        """Test AI analysis when successful."""
        mock_instance = mock_scorer.return_value
        mock_instance.calculate_trust_score.return_value = self.ai_analysis_result
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._analyze_persona(self.valid_account_info)
        
        self.assertEqual(result["trust_score"], 75)
        self.assertEqual(result["ai_analysis"]["viability_score"], 85)
        
        # Verify scorer was called with correct account info
        mock_instance.calculate_trust_score.assert_called_once_with(self.valid_account_info)
    
    @patch('src.analysis.scorer.PersonaScorer')
    def test_analyze_persona_exception(self, mock_scorer):
        """Test AI analysis when an exception occurs."""
        mock_instance = mock_scorer.return_value
        mock_instance.calculate_trust_score.side_effect = Exception("API error")
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator._analyze_persona(self.valid_account_info)
        
        self.assertEqual(result["error"], "API error")
        self.assertEqual(result["ai_analysis"]["viability_score"], 0)
    
    def test_calculate_trust_score(self):
        """Test trust score calculation with various inputs."""
        validator = RedditPersonaValidator(config_path=self.config_path)
        
        # Test with all factors
        score1 = validator._calculate_trust_score(
            {"karma": 5000, "age_days": 365},
            email_verified=True,
            ai_score=85
        )
        
        # Test without email verification
        score2 = validator._calculate_trust_score(
            {"karma": 5000, "age_days": 365},
            email_verified=False,
            ai_score=85
        )
        
        # Test without AI score
        score3 = validator._calculate_trust_score(
            {"karma": 5000, "age_days": 365},
            email_verified=True
        )
        
        # Score with email should be higher than without
        self.assertGreater(score1, score2)
        
        # Both scores should be reasonable values
        self.assertTrue(0 <= score1 <= 100)
        self.assertTrue(0 <= score2 <= 100)
        self.assertTrue(0 <= score3 <= 100)
    
    @patch('src.core.validator.RedditPersonaValidator._extract_account_info')
    @patch('src.core.validator.RedditPersonaValidator._verify_email')
    @patch('src.core.validator.RedditPersonaValidator._analyze_persona')
    @patch('src.core.validator.RedditPersonaValidator._calculate_trust_score')
    @patch('src.core.validator.RedditPersonaValidator._cleanup')
    def test_validate_full_process(self, mock_cleanup, mock_score, mock_analyze, 
                                mock_verify, mock_extract):
        """Test the full validation process flow."""
        # Set up our mocks
        mock_extract.return_value = self.valid_account_info
        mock_verify.return_value = self.email_verification_success
        mock_analyze.return_value = self.ai_analysis_result
        mock_score.return_value = 85.5
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(
            username="test_user",
            email_address="user@example.com",
            perform_email_verification=True,
            perform_ai_analysis=True
        )
        
        # Verify result
        self.assertTrue(result.exists)
        self.assertEqual(result.username, "test_user")
        self.assertEqual(result.trust_score, 85.5)
        self.assertTrue(result.email_verified)
        self.assertIsNotNone(result.ai_analysis)
        
        # Verify all methods were called
        mock_extract.assert_called_once_with("test_user")
        mock_verify.assert_called_once_with("test_user", "user@example.com")
        mock_analyze.assert_called_once_with(self.valid_account_info)
        mock_score.assert_called_once()
        mock_cleanup.assert_called_once()
    
    @patch('src.core.validator.RedditPersonaValidator._extract_account_info')
    @patch('src.core.validator.RedditPersonaValidator._cleanup')
    def test_validate_nonexistent_account(self, mock_cleanup, mock_extract):
        """Test validation when account doesn't exist."""
        mock_extract.return_value = self.invalid_account_info
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(username="nonexistent_user")
        
        self.assertFalse(result.exists)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("does not exist", result.errors[0])
        
        # Verify cleanup was still called
        mock_cleanup.assert_called_once()
    
    @patch('src.core.validator.RedditPersonaValidator._extract_account_info')
    @patch('src.core.validator.RedditPersonaValidator._cleanup')
    def test_validate_with_exception(self, mock_cleanup, mock_extract):
        """Test validation when an exception occurs."""
        mock_extract.side_effect = Exception("Critical error")
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        result = validator.validate(username="test_user")
        
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Critical error", result.errors[0])
        
        # Verify cleanup was still called
        mock_cleanup.assert_called_once()
    
    @patch('src.core.browser_engine.BrowserEngine')
    @patch('src.core.email_verifier.EmailVerifier')
    def test_cleanup_method(self, mock_email_verifier, mock_browser):
        """Test the cleanup method closes all resources properly."""
        # Set up mock instances
        mock_browser_instance = mock_browser.return_value
        mock_email_instance = mock_email_verifier.return_value
        mock_email_instance.is_connected = True
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        validator.browser_engine = mock_browser_instance
        validator.email_verifier = mock_email_instance
        
        # Call cleanup
        validator._cleanup()
        
        # Verify both resources were closed
        mock_browser_instance.close.assert_called_once()
        mock_email_instance.disconnect.assert_called_once()
    
    @patch('src.core.browser_engine.BrowserEngine')
    @patch('src.core.email_verifier.EmailVerifier')
    def test_cleanup_handles_exceptions(self, mock_email_verifier, mock_browser):
        """Test cleanup handles exceptions gracefully."""
        # Set up mock instances
        mock_browser_instance = mock_browser.return_value
        mock_browser_instance.close.side_effect = Exception("Browser close error")
        
        mock_email_instance = mock_email_verifier.return_value
        mock_email_instance.is_connected = True
        mock_email_instance.disconnect.side_effect = Exception("Email disconnect error")
        
        validator = RedditPersonaValidator(config_path=self.config_path)
        validator.browser_engine = mock_browser_instance
        validator.email_verifier = mock_email_instance
        
        # Call cleanup - should not raise exceptions
        validator._cleanup()
        
        # Verify both close methods were called despite exceptions
        mock_browser_instance.close.assert_called_once()
        mock_email_instance.disconnect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
