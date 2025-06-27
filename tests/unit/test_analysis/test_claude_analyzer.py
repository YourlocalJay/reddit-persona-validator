"""Unit tests for ClaudeAnalyzer implementation."""

import unittest
from unittest.mock import patch, MagicMock, ANY
import json
from datetime import datetime, timedelta
import os

from src.analysis.claude_analyzer import ClaudeAnalyzer
from src.analysis.base_analyzer import APIError, RateLimitExceeded


class TestClaudeAnalyzer(unittest.TestCase):
    """Test cases for ClaudeAnalyzer implementation."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create analyzer with mock_mode=False for testing real mode
        self.analyzer = ClaudeAnalyzer(
            api_key="test_key",
            mock_mode=False,
            model="claude-3-5-sonnet-20240620",
            max_tokens=1000,
            temperature=0.2
        )
        
        # Create analyzer with mock_mode=True for testing mock mode
        self.mock_analyzer = ClaudeAnalyzer(
            mock_mode=True
        )
        
        # Sample persona data for testing
        self.persona_data = {
            "username": "test_user",
            "karma": 10000,
            "post_karma": 3000,
            "comment_karma": 7000,
            "age_days": 730,
            "verified_email": True,
            "is_gold": True,
            "is_mod": False,
            "recent_posts": [
                {"title": "Test Post 1", "subreddit": "test_sub_1"},
                {"title": "Test Post 2", "subreddit": "test_sub_2"}
            ],
            "recent_comments": [
                {"body": "Test Comment 1", "subreddit": "test_sub_1"},
                {"body": "Test Comment 2", "subreddit": "test_sub_3"}
            ],
            "active_in_subreddits": ["test_sub_1", "test_sub_2", "test_sub_3"]
        }
        
        # Sample Claude API response
        self.claude_response_obj = MagicMock()
        self.claude_response_obj.content = json.dumps({
            "viability_score": 85,
            "best_use_case": ["CPA", "Vault"],
            "risk_factors": ["limited post history"],
            "maintenance_notes": "Verify email access before use."
        })
    
    def test_init(self):
        """Test initialization of ClaudeAnalyzer."""
        # Test with explicit API key
        analyzer = ClaudeAnalyzer(api_key="explicit_key")
        self.assertEqual(analyzer.api_key, "explicit_key")
        
        # Test with environment variable
        with patch.dict(os.environ, {"CLAUDE_API_KEY": "env_key"}):
            analyzer = ClaudeAnalyzer()
            self.assertEqual(analyzer.api_key, "env_key")
        
        # Test model and temperature settings
        self.assertEqual(self.analyzer.model, "claude-3-5-sonnet-20240620")
        self.assertEqual(self.analyzer.temperature, 0.2)
        self.assertEqual(self.analyzer.max_tokens, 1000)
    
    def test_extract_content(self):
        """Test extract_content method."""
        extracted = self.analyzer.extract_content(self.persona_data)
        
        # Verify core fields are extracted
        self.assertEqual(extracted["username"], "test_user")
        self.assertEqual(extracted["karma"], 10000)
        self.assertEqual(extracted["account_age_days"], 730)
        self.assertTrue(extracted["verified_email"])
        self.assertTrue(extracted["is_gold"])
        
        # Verify activity metrics are calculated
        self.assertEqual(extracted["post_frequency"], 2)
        self.assertEqual(set(extracted["post_subreddits"]), {"test_sub_1", "test_sub_2"})
        self.assertEqual(extracted["comment_frequency"], 2)
        self.assertEqual(set(extracted["comment_subreddits"]), {"test_sub_1", "test_sub_3"})
    
    def test_analyze_content_real_mode(self):
        """Test analyze_content method in real mode."""
        with patch.object(self.analyzer, 'client') as mock_client:
            mock_client.messages.create.return_value = self.claude_response_obj
            
            content = self.analyzer.extract_content(self.persona_data)
            result = self.analyzer.analyze_content(content)
            
            # Verify Claude API was called with correct parameters
            mock_client.messages.create.assert_called_with(
                model=self.analyzer.model,
                max_tokens=self.analyzer.max_tokens,
                temperature=self.analyzer.temperature,
                system=ANY,
                messages=ANY
            )
            
            # Verify result was parsed correctly
            self.assertEqual(result["viability_score"], 85)
            self.assertEqual(result["best_use_case"], ["CPA", "Vault"])
            self.assertIn("risk_factors", result)
            self.assertIn("maintenance_notes", result)
            self.assertIn("next_review_date", result)
    
    def test_analyze_content_mock_mode(self):
        """Test analyze_content method in mock mode."""
        content = self.mock_analyzer.extract_content(self.persona_data)
        result = self.mock_analyzer.analyze_content(content)
        
        # Verify result is a mock result
        self.assertIn("viability_score", result)
        self.assertIn("best_use_case", result)
        self.assertIn("risk_factors", result)
        self.assertIn("maintenance_notes", result)
        self.assertIn("next_review_date", result)
    
    def test_build_prompt(self):
        """Test _build_prompt method."""
        content = {"username": "test_user", "karma": 1000}
        prompt = self.analyzer._build_prompt(content)
        
        # Verify prompt contains expected sections
        self.assertIn("Analyze the following Reddit persona data", prompt)
        self.assertIn(json.dumps(content, indent=2), prompt)
        self.assertIn("viability_score", prompt)
        self.assertIn("best_use_case", prompt)
        self.assertIn("risk_factors", prompt)
        self.assertIn("maintenance_notes", prompt)
    
    def test_parse_response_valid_json(self):
        """Test _parse_response method with valid JSON."""
        response = json.dumps({
            "viability_score": 75,
            "best_use_case": ["Community Building"],
            "risk_factors": ["inconsistent posting pattern"],
            "maintenance_notes": "Build more comment history."
        })
        
        result = self.analyzer._parse_response(response)
        
        # Verify JSON was parsed correctly
        self.assertEqual(result["viability_score"], 75)
        self.assertEqual(result["best_use_case"], ["Community Building"])
        self.assertEqual(result["risk_factors"], ["inconsistent posting pattern"])
        self.assertEqual(result["maintenance_notes"], "Build more comment history.")
        self.assertIn("next_review_date", result)
    
    def test_parse_response_json_with_text(self):
        """Test _parse_response method with JSON embedded in text."""
        response = """
        Here's my analysis:
        
        {
            "viability_score": 65,
            "best_use_case": ["Monitoring Only"],
            "risk_factors": ["suspicious activity pattern"],
            "maintenance_notes": "Not recommended for primary operations."
        }
        
        Hope this helps!
        """
        
        result = self.analyzer._parse_response(response)
        
        # Verify JSON was extracted and parsed correctly
        self.assertEqual(result["viability_score"], 65)
        self.assertEqual(result["best_use_case"], ["Monitoring Only"])
    
    def test_parse_response_invalid_json(self):
        """Test _parse_response method with invalid JSON."""
        response = "This is not JSON"
        
        result = self.analyzer._parse_response(response)
        
        # Verify error handling
        self.assertIn("error", result)
        self.assertEqual(result["viability_score"], 0)
        self.assertEqual(result["best_use_case"], ["None"])
        self.assertIn("Analysis failed", result["risk_factors"])
        self.assertIn("next_review_date", result)
    
    def test_mock_analyze(self):
        """Test _mock_analyze method."""
        # Test high trust scenario
        content_high = {"karma": 10000, "account_age_days": 730, "is_mod": True}
        result_high = self.mock_analyzer._mock_analyze(content_high)
        
        self.assertGreater(result_high["viability_score"], 80)
        self.assertIn("next_review_date", result_high)
        
        # Test medium trust scenario
        content_medium = {"karma": 2000, "account_age_days": 180}
        result_medium = self.mock_analyzer._mock_analyze(content_medium)
        
        self.assertGreater(result_medium["viability_score"], 50)
        self.assertLess(result_medium["viability_score"], 80)
        
        # Test low trust scenario
        content_low = {"karma": 500, "account_age_days": 30}
        result_low = self.mock_analyzer._mock_analyze(content_low)
        
        self.assertLess(result_low["viability_score"], 50)
    
    def test_api_error_handling(self):
        """Test handling of API errors."""
        with patch.object(self.analyzer, 'client') as mock_client:
            from anthropic import RateLimitError, APIError as AnthropicAPIError
            
            # Test rate limit error
            mock_client.messages.create.side_effect = RateLimitError("Rate limit exceeded")
            
            with self.assertRaises(RateLimitExceeded):
                content = self.analyzer.extract_content(self.persona_data)
                self.analyzer.analyze_content(content)
            
            # Test API error
            mock_client.messages.create.side_effect = AnthropicAPIError("API error")
            
            with self.assertRaises(APIError):
                content = self.analyzer.extract_content(self.persona_data)
                self.analyzer.analyze_content(content)


if __name__ == '__main__':
    unittest.main()
