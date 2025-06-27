"""Unit tests for MockAnalyzer implementation."""

import unittest
from unittest.mock import patch, MagicMock
import json
import random
from datetime import datetime

from src.analysis.mock_analyzer import MockAnalyzer


class TestMockAnalyzer(unittest.TestCase):
    """Test cases for MockAnalyzer implementation."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create deterministic mock analyzer
        self.deterministic_analyzer = MockAnalyzer(
            deterministic=True,
            success_rate=1.0
        )
        
        # Create non-deterministic mock analyzer with controlled randomness
        self.random_analyzer = MockAnalyzer(
            deterministic=False,
            success_rate=0.8,
            response_time_range=(0.1, 0.2)
        )
        
        # Create mock analyzer with high failure rate for testing error handling
        self.failing_analyzer = MockAnalyzer(
            deterministic=False,
            success_rate=0.0  # Always fails
        )
        
        # Sample persona data for testing
        self.persona_data = {
            "username": "test_user_123",  # Deterministic hash seed
            "karma": 5500,
            "post_karma": 1500,
            "comment_karma": 4000,
            "age_days": 400,
            "verified_email": True,
            "is_gold": True,
            "is_mod": False
        }
    
    def test_init(self):
        """Test initialization of MockAnalyzer."""
        analyzer = MockAnalyzer(
            deterministic=True,
            success_rate=0.75,
            response_time_range=(1.0, 3.0),
            rate_limit_calls=500,
            rate_limit_period=30
        )
        
        self.assertTrue(analyzer.deterministic)
        self.assertEqual(analyzer.success_rate, 0.75)
        self.assertEqual(analyzer.response_time_range, (1.0, 3.0))
        self.assertEqual(analyzer.rate_limit_calls, 500)
        self.assertEqual(analyzer.rate_limit_period, 30)
        self.assertEqual(analyzer.api_key, "mock_api_key")
        self.assertTrue(analyzer.mock_mode)
    
    def test_extract_content(self):
        """Test extract_content method."""
        extracted = self.deterministic_analyzer.extract_content(self.persona_data)
        
        # Verify core fields are extracted
        self.assertEqual(extracted["username"], "test_user_123")
        self.assertEqual(extracted["karma"], 5500)
        self.assertEqual(extracted["account_age_days"], 400)
        self.assertTrue(extracted["verified_email"])
        self.assertTrue(extracted["is_gold"])
        self.assertFalse(extracted["is_mod"])
        self.assertIn("timestamp", extracted)
    
    def test_analyze_content_deterministic(self):
        """Test analyze_content method with deterministic analyzer."""
        content = self.deterministic_analyzer.extract_content(self.persona_data)
        result = self.deterministic_analyzer.analyze_content(content)
        
        # Verify result is a deterministic mock result
        self.assertIn("viability_score", result)
        self.assertIn("best_use_case", result)
        self.assertIn("risk_factors", result)
        self.assertIn("maintenance_notes", result)
        
        # Run again to verify deterministic behavior (same result)
        result2 = self.deterministic_analyzer.analyze_content(content)
        self.assertEqual(result["viability_score"], result2["viability_score"])
        self.assertEqual(result["best_use_case"], result2["best_use_case"])
    
    def test_analyze_content_random(self):
        """Test analyze_content method with random analyzer."""
        # Patch random.uniform to return predictable values
        with patch('random.uniform', return_value=0.15), \
             patch('random.random', return_value=0.9):  # Above success_rate threshold
            
            content = self.random_analyzer.extract_content(self.persona_data)
            result = self.random_analyzer.analyze_content(content)
            
            # Verify result is a mock result
            self.assertIn("viability_score", result)
            self.assertIn("best_use_case", result)
            self.assertIn("risk_factors", result)
            self.assertIn("maintenance_notes", result)
    
    def test_analyze_content_failure(self):
        """Test analyze_content method with simulated failure."""
        with patch('random.random', return_value=0.1):  # Below success_rate threshold
            
            content = self.failing_analyzer.extract_content(self.persona_data)
            
            # Should raise an exception due to simulated failure
            with self.assertRaises(Exception):
                self.failing_analyzer.analyze_content(content)
    
    def test_build_prompt(self):
        """Test _build_prompt method."""
        content = {"username": "test_user"}
        prompt = self.deterministic_analyzer._build_prompt(content)
        
        # Verify prompt is a simple mock prompt
        self.assertEqual(prompt, "Mock prompt for test_user")
    
    def test_parse_response(self):
        """Test _parse_response method."""
        response = {"test": "response"}
        result = self.deterministic_analyzer._parse_response(response)
        
        # Verify response is passed through unchanged
        self.assertEqual(result, response)
    
    def test_mock_analyze_deterministic(self):
        """Test _mock_analyze method with deterministic analyzer."""
        # Use a fixed username to get deterministic results
        content = {"username": "stable_user", "karma": 1000, "account_age_days": 100}
        result1 = self.deterministic_analyzer._mock_analyze(content)
        
        # Run again with same content
        result2 = self.deterministic_analyzer._mock_analyze(content)
        
        # Results should be identical
        self.assertEqual(result1["viability_score"], result2["viability_score"])
        self.assertEqual(result1["best_use_case"], result2["best_use_case"])
        self.assertEqual(result1["risk_factors"], result2["risk_factors"])
        
        # Check proper metadata
        self.assertEqual(result1["analyzer"], "MockAnalyzer")
        self.assertTrue(result1["mock"])
    
    def test_mock_analyze_deterministic_trust_levels(self):
        """Test _mock_analyze method produces different trust levels based on username hash."""
        # Create users with different names to get different hash values
        usernames = ["user_low", "user_medium", "user_high", "user_very_low"]
        trust_scores = []
        
        for username in usernames:
            content = {"username": username, "karma": 1000, "account_age_days": 100}
            result = self.deterministic_analyzer._mock_analyze(content)
            trust_scores.append(result["viability_score"])
        
        # Verify we get a range of scores (not all the same)
        self.assertTrue(max(trust_scores) - min(trust_scores) > 20)
    
    def test_mock_analyze_account_properties(self):
        """Test _mock_analyze method considers account properties."""
        # High karma, old account
        content_high = {"username": "fixed", "karma": 15000, "account_age_days": 1000, "is_mod": False}
        result_high = self.deterministic_analyzer._mock_analyze(content_high)
        
        # Same username but moderator status
        content_high_mod = {"username": "fixed", "karma": 15000, "account_age_days": 1000, "is_mod": True}
        result_high_mod = self.deterministic_analyzer._mock_analyze(content_high_mod)
        
        # Low karma, new account
        content_low = {"username": "fixed", "karma": 100, "account_age_days": 30, "is_mod": False}
        result_low = self.deterministic_analyzer._mock_analyze(content_low)
        
        # Moderator status should increase score
        self.assertGreater(result_high_mod["viability_score"], result_high["viability_score"])
        
        # Higher karma and age should yield higher score when not in deterministic mode
        with patch('random.uniform', return_value=0.0):  # Ensure no random variation
            random_analyzer = MockAnalyzer(deterministic=False)
            
            high_score = random_analyzer._mock_analyze(content_high)["viability_score"]
            low_score = random_analyzer._mock_analyze(content_low)["viability_score"]
            
            self.assertGreater(high_score, low_score)
    
    def test_mock_analyze_random_variations(self):
        """Test _mock_analyze method produces variations with non-deterministic mode."""
        with patch('random.uniform', return_value=3.0), \
             patch('random.random', return_value=0.2):  # Trigger risk factor modifications
            
            content = {"username": "test_user", "karma": 5000, "account_age_days": 500}
            random_analyzer = MockAnalyzer(deterministic=False)
            
            result1 = random_analyzer._mock_analyze(content)
            
            # Patch to get different random values
            with patch('random.uniform', return_value=-3.0), \
                 patch('random.random', return_value=0.1):  # Different variations
                
                result2 = random_analyzer._mock_analyze(content)
                
                # Results should have variations
                self.assertNotEqual(result1["viability_score"], result2["viability_score"])
    
    def test_review_date_calculation(self):
        """Test next_review_date calculation based on viability score."""
        # High score - 30 day review
        high_score_content = {"username": "high_score", "karma": 20000, "account_age_days": 1000}
        high_result = self.deterministic_analyzer._mock_analyze(high_score_content)
        
        # Medium score - 14 day review
        medium_score_content = {"username": "medium_score", "karma": 3000, "account_age_days": 200}
        medium_result = self.deterministic_analyzer._mock_analyze(medium_score_content)
        
        # Low score - 7 day review
        low_score_content = {"username": "low_score", "karma": 100, "account_age_days": 30}
        low_result = self.deterministic_analyzer._mock_analyze(low_score_content)
        
        # Extract days difference
        high_days = (datetime.strptime(high_result["next_review_date"], '%Y-%m-%d') - datetime.now()).days
        medium_days = (datetime.strptime(medium_result["next_review_date"], '%Y-%m-%d') - datetime.now()).days
        low_days = (datetime.strptime(low_result["next_review_date"], '%Y-%m-%d') - datetime.now()).days
        
        # Verify review periods (allowing for day boundary changes)
        self.assertTrue(25 <= high_days <= 31)
        self.assertTrue(10 <= medium_days <= 15)
        self.assertTrue(5 <= low_days <= 8)


if __name__ == '__main__':
    unittest.main()
