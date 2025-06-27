"""Unit tests for BaseAnalyzer abstract class."""

import unittest
from unittest.mock import patch, MagicMock
import logging
from abc import ABC, abstractmethod
import time
from datetime import datetime

from src.analysis.base_analyzer import BaseAnalyzer, RateLimitExceeded, APIError


class ConcreteAnalyzer(BaseAnalyzer):
    """Concrete implementation of BaseAnalyzer for testing abstract methods."""
    
    def extract_content(self, persona_data):
        return {"extracted": True, "data": persona_data}
    
    def analyze_content(self, content):
        if self.mock_mode:
            return self._mock_analyze(content)
        return {"analyzed": True, "content": content}
    
    def _build_prompt(self, content):
        return f"Test prompt for {content}"
    
    def _parse_response(self, response):
        return {"parsed": True, "response": response}
    
    def _mock_analyze(self, content):
        return {"mocked": True, "content": content}


class TestBaseAnalyzer(unittest.TestCase):
    """Test cases for BaseAnalyzer abstract base class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.analyzer = ConcreteAnalyzer(
            api_key="test_key",
            mock_mode=False,
            rate_limit_calls=10,
            rate_limit_period=60,
            max_retries=3
        )
        
        self.mock_analyzer = ConcreteAnalyzer(
            api_key="test_key",
            mock_mode=True,
            rate_limit_calls=10,
            rate_limit_period=60,
            max_retries=3
        )
        
        self.persona_data = {
            "username": "test_user",
            "karma": 1000,
            "age_days": 365,
            "recent_posts": [{"title": "Test Post", "subreddit": "test"}],
            "recent_comments": [{"body": "Test Comment", "subreddit": "test"}]
        }
    
    def test_init(self):
        """Test initialization of BaseAnalyzer."""
        self.assertEqual(self.analyzer.api_key, "test_key")
        self.assertFalse(self.analyzer.mock_mode)
        self.assertEqual(self.analyzer.rate_limit_calls, 10)
        self.assertEqual(self.analyzer.rate_limit_period, 60)
        self.assertEqual(self.analyzer.max_retries, 3)
    
    def test_analyze_real_mode(self):
        """Test analyze method in real mode."""
        with patch.object(self.analyzer, 'analyze_content') as mock_analyze_content:
            mock_analyze_content.return_value = {"test": "result"}
            
            result = self.analyzer.analyze(self.persona_data)
            
            # Verify correct methods were called
            mock_analyze_content.assert_called_once()
            
            # Verify result includes metadata
            self.assertEqual(result["test"], "result")
            self.assertIn("analysis_time", result)
            self.assertIn("analysis_timestamp", result)
            self.assertIn("analyzer", result)
            self.assertEqual(result["analyzer"], "ConcreteAnalyzer")
    
    def test_analyze_mock_mode(self):
        """Test analyze method in mock mode."""
        with patch.object(self.mock_analyzer, '_mock_analyze') as mock_analyze:
            mock_analyze.return_value = {"mock": "result"}
            
            result = self.mock_analyzer.analyze(self.persona_data)
            
            # Verify correct methods were called
            mock_analyze.assert_called_once()
            
            # Verify result includes metadata
            self.assertEqual(result["mock"], "result")
            self.assertIn("analysis_time", result)
            self.assertTrue(result.get("mock", False))
    
    def test_analyze_with_exception(self):
        """Test analyze method with exception in real mode."""
        with patch.object(self.analyzer, 'analyze_content') as mock_analyze_content:
            mock_analyze_content.side_effect = Exception("Test error")
            
            result = self.analyzer.analyze(self.persona_data)
            
            # Verify fallback to mock analysis
            self.assertIn("error", result)
            self.assertEqual(result["error"], "Test error")
            self.assertTrue(result.get("fallback", False))
            self.assertIn("analysis_time", result)
    
    def test_api_call_with_retry(self):
        """Test _api_call_with_retry method."""
        mock_func = MagicMock()
        mock_func.side_effect = [Exception("First error"), Exception("Second error"), "success"]
        
        # Should succeed on third try
        result = self.analyzer._api_call_with_retry(mock_func, "arg1", kwarg1="kwarg1")
        
        self.assertEqual(result, "success")
        self.assertEqual(mock_func.call_count, 3)
        
        # Reset mock and test permanent failure
        mock_func.reset_mock()
        mock_func.side_effect = Exception("Permanent error")
        
        with self.assertRaises(Exception):
            self.analyzer._api_call_with_retry(mock_func, "arg1", kwarg1="kwarg1")
        
        self.assertEqual(mock_func.call_count, 3)  # Max retries
    
    def test_rate_limit_configuration(self):
        """Test rate limit configuration."""
        # This is more of a check that the configuration doesn't error
        analyzer = ConcreteAnalyzer(
            rate_limit_calls=5,
            rate_limit_period=10
        )
        
        self.assertEqual(analyzer.rate_limit_calls, 5)
        self.assertEqual(analyzer.rate_limit_period, 10)


if __name__ == '__main__':
    unittest.main()
