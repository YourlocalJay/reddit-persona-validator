"""Unit tests for PersonaScorer implementation."""

import unittest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime

from src.analysis.scorer import PersonaScorer
from src.analysis.base_analyzer import BaseAnalyzer
from src.analysis.mock_analyzer import MockAnalyzer
from src.analysis.claude_analyzer import ClaudeAnalyzer
from src.analysis.deepseek_analyzer import DeepSeekAnalyzer


class TestPersonaScorer(unittest.TestCase):
    """Test cases for PersonaScorer implementation."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create default scorer with mock_mode enabled
        self.scorer = PersonaScorer(
            analyzer_type="deepseek",
            mock_mode=True,
            fallback_analyzer="mock"
        )
        
        # Create scorer with custom weights
        self.custom_scorer = PersonaScorer(
            analyzer_type="claude",
            mock_mode=True,
            fallback_analyzer="mock",
            scoring_weights={
                "account_age": 0.4,
                "karma": 0.1,
                "ai_analysis": 0.5
            }
        )
        
        # Sample persona data for testing
        self.persona_data = {
            "username": "test_user",
            "karma": 5000,
            "post_karma": 1500,
            "comment_karma": 3500,
            "age_days": 365,
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
        
        # Sample AI analysis result
        self.sample_analysis = {
            "viability_score": 85,
            "best_use_case": ["CPA", "Vault"],
            "risk_factors": ["limited post history"],
            "maintenance_notes": "Verify email access before use."
        }
    
    def test_init(self):
        """Test initialization of PersonaScorer."""
        # Test default values
        scorer = PersonaScorer()
        self.assertEqual(scorer.analyzer_type, "deepseek")
        self.assertFalse(scorer.mock_mode)
        self.assertEqual(scorer._fallback_analyzer_type, "mock")
        
        # Test with explicit values
        scorer = PersonaScorer(
            analyzer_type="claude",
            mock_mode=True,
            fallback_analyzer="deepseek"
        )
        self.assertEqual(scorer.analyzer_type, "claude")
        self.assertTrue(scorer.mock_mode)
        self.assertEqual(scorer._fallback_analyzer_type, "deepseek")
        
        # Test weight normalization
        scorer = PersonaScorer(
            scoring_weights={
                "account_age": 1.0,
                "karma": 2.0,
                "ai_analysis": 3.0
            }
        )
        self.assertAlmostEqual(scorer.scoring_weights["account_age"], 1/6)
        self.assertAlmostEqual(scorer.scoring_weights["karma"], 2/6)
        self.assertAlmostEqual(scorer.scoring_weights["ai_analysis"], 3/6)
        self.assertAlmostEqual(sum(scorer.scoring_weights.values()), 1.0)
    
    def test_analyzer_property(self):
        """Test the analyzer property (lazy loading)."""
        # Initial analyzer should be None
        self.assertIsNone(self.scorer._analyzer)
        
        # Accessing the property should initialize the analyzer
        analyzer = self.scorer.analyzer
        self.assertIsNotNone(analyzer)
        self.assertIsInstance(analyzer, DeepSeekAnalyzer)
        self.assertTrue(analyzer.mock_mode)
        
        # Second access should use the same instance
        analyzer2 = self.scorer.analyzer
        self.assertIs(analyzer, analyzer2)
    
    def test_fallback_analyzer_property(self):
        """Test the fallback_analyzer property (lazy loading)."""
        # Initial fallback analyzer should be None
        self.assertIsNone(self.scorer._fallback_analyzer)
        
        # Accessing the property should initialize the fallback analyzer
        fallback = self.scorer.fallback_analyzer
        self.assertIsNotNone(fallback)
        self.assertIsInstance(fallback, MockAnalyzer)
        
        # Second access should use the same instance
        fallback2 = self.scorer.fallback_analyzer
        self.assertIs(fallback, fallback2)
        
        # Setting a new fallback type should reset the instance
        self.scorer.fallback_analyzer = "claude"
        self.assertEqual(self.scorer._fallback_analyzer_type, "claude")
        self.assertIsNone(self.scorer._fallback_analyzer)
        
        # Accessing again should create a new instance of the new type
        new_fallback = self.scorer.fallback_analyzer
        self.assertIsInstance(new_fallback, ClaudeAnalyzer)
    
    def test_init_analyzer(self):
        """Test _init_analyzer method."""
        # Test with valid analyzer type
        with patch.dict(PersonaScorer.ANALYZER_TYPES, {"test": MagicMock}):
            scorer = PersonaScorer(analyzer_type="test")
            scorer._init_analyzer()
            self.assertIsInstance(scorer._analyzer, MagicMock)
        
        # Test with invalid analyzer type
        scorer = PersonaScorer(analyzer_type="invalid")
        scorer._init_analyzer()
        self.assertEqual(scorer.analyzer_type, "mock")
        self.assertIsInstance(scorer._analyzer, MockAnalyzer)
        
        # Test with initialization error
        with patch.dict(PersonaScorer.ANALYZER_TYPES, {"error": MagicMock}):
            with patch.object(MagicMock, '__call__', side_effect=Exception("Init error")):
                scorer = PersonaScorer(analyzer_type="error")
                scorer._init_analyzer()
                self.assertEqual(scorer.analyzer_type, "mock")
                self.assertIsInstance(scorer._analyzer, MockAnalyzer)
    
    def test_init_fallback_analyzer(self):
        """Test _init_fallback_analyzer method."""
        # Test with same type as primary (should skip)
        scorer = PersonaScorer(analyzer_type="mock", fallback_analyzer="mock")
        scorer._init_analyzer()
        scorer._init_fallback_analyzer()
        self.assertIsNone(scorer._fallback_analyzer)
        
        # Test with different valid type
        with patch.dict(PersonaScorer.ANALYZER_TYPES, {"test": MagicMock}):
            scorer = PersonaScorer(analyzer_type="mock", fallback_analyzer="test")
            scorer._init_fallback_analyzer()
            self.assertIsInstance(scorer._fallback_analyzer, MagicMock)
        
        # Test with invalid type
        scorer = PersonaScorer(analyzer_type="mock", fallback_analyzer="invalid")
        scorer._init_fallback_analyzer()
        self.assertEqual(scorer._fallback_analyzer_type, "mock")
        
        # Test with initialization error
        with patch.dict(PersonaScorer.ANALYZER_TYPES, {"error": MagicMock}):
            with patch.object(MagicMock, '__call__', side_effect=Exception("Init error")):
                scorer = PersonaScorer(analyzer_type="mock", fallback_analyzer="error")
                scorer._init_fallback_analyzer()
                self.assertIsNone(scorer._fallback_analyzer)
    
    def test_calculate_trust_score(self):
        """Test calculate_trust_score method."""
        with patch.object(self.scorer, '_perform_analysis') as mock_perform_analysis, \
             patch.object(self.scorer, '_calculate_base_scores') as mock_calculate_base_scores, \
             patch.object(self.scorer, '_calculate_combined_score') as mock_calculate_combined_score:
            
            # Setup mocks
            mock_calculate_base_scores.return_value = {"age_score": 75, "karma_score": 60}
            mock_perform_analysis.return_value = self.sample_analysis
            mock_calculate_combined_score.return_value = 80.5
            
            # Call the method
            result = self.scorer.calculate_trust_score(self.persona_data)
            
            # Verify method calls
            mock_calculate_base_scores.assert_called_once_with(self.persona_data)
            mock_perform_analysis.assert_called_once_with(self.persona_data)
            mock_calculate_combined_score.assert_called_once_with(
                {"age_score": 75, "karma_score": 60},
                self.sample_analysis
            )
            
            # Verify result structure
            self.assertEqual(result["trust_score"], 80.5)
            self.assertEqual(result["component_scores"], {"age_score": 75, "karma_score": 60})
            self.assertEqual(result["ai_analysis"], self.sample_analysis)
            self.assertIn("analysis_timestamp", result)
            self.assertIn("analyzer_used", result)
    
    def test_calculate_base_scores(self):
        """Test _calculate_base_scores method."""
        # Test with normal values
        scores = self.scorer._calculate_base_scores(self.persona_data)
        
        self.assertIn("age_score", scores)
        self.assertIn("karma_score", scores)
        self.assertIn("karma_distribution_score", scores)
        self.assertIn("email_verified_score", scores)
        
        # Age score should be proportional to 3 years max
        self.assertAlmostEqual(scores["age_score"], (365 / 1095) * 100, places=0)
        
        # Karma score should be proportional to 50000 max
        self.assertAlmostEqual(scores["karma_score"], (5000 / 50000) * 100, places=0)
        
        # Verified email score should be 100
        self.assertEqual(scores["email_verified_score"], 100)
        
        # Test with zero values
        zero_data = {
            "karma": 0,
            "post_karma": 0,
            "comment_karma": 0,
            "age_days": 0,
            "verified_email": False
        }
        
        zero_scores = self.scorer._calculate_base_scores(zero_data)
        self.assertEqual(zero_scores["age_score"], 0)
        self.assertEqual(zero_scores["karma_score"], 0)
        self.assertEqual(zero_scores["email_verified_score"], 0)
    
    def test_perform_analysis(self):
        """Test _perform_analysis method."""
        # Test successful primary analysis
        with patch.object(self.scorer, 'analyzer') as mock_analyzer:
            mock_analyzer.analyze.return_value = self.sample_analysis
            
            result = self.scorer._perform_analysis(self.persona_data)
            
            mock_analyzer.analyze.assert_called_once_with(self.persona_data)
            self.assertEqual(result, self.sample_analysis)
        
        # Test failed primary analysis with successful fallback
        with patch.object(self.scorer, 'analyzer') as mock_analyzer, \
             patch.object(self.scorer, 'fallback_analyzer') as mock_fallback:
            
            mock_analyzer.analyze.return_value = {"error": "Primary failed"}
            mock_fallback.analyze.return_value = self.sample_analysis
            
            result = self.scorer._perform_analysis(self.persona_data)
            
            mock_analyzer.analyze.assert_called_once_with(self.persona_data)
            mock_fallback.analyze.assert_called_once_with(self.persona_data)
            self.assertEqual(result, self.sample_analysis)
        
        # Test exception in primary with successful fallback
        with patch.object(self.scorer, 'analyzer') as mock_analyzer, \
             patch.object(self.scorer, 'fallback_analyzer') as mock_fallback:
            
            mock_analyzer.analyze.side_effect = Exception("Test error")
            mock_fallback.analyze.return_value = self.sample_analysis
            
            result = self.scorer._perform_analysis(self.persona_data)
            
            mock_analyzer.analyze.assert_called_once_with(self.persona_data)
            mock_fallback.analyze.assert_called_once_with(self.persona_data)
            self.assertEqual(result, self.sample_analysis)
        
        # Test both analyzers failing
        with patch.object(self.scorer, 'analyzer') as mock_analyzer, \
             patch.object(self.scorer, 'fallback_analyzer') as mock_fallback:
            
            mock_analyzer.analyze.side_effect = Exception("Primary error")
            mock_fallback.analyze.side_effect = Exception("Fallback error")
            
            result = self.scorer._perform_analysis(self.persona_data)
            
            mock_analyzer.analyze.assert_called_once_with(self.persona_data)
            mock_fallback.analyze.assert_called_once_with(self.persona_data)
            
            self.assertIn("error", result)
            self.assertEqual(result["viability_score"], 0)
            self.assertEqual(result["best_use_case"], ["Analysis Failed"])
            self.assertIn("Analysis error", result["risk_factors"])
    
    def test_calculate_combined_score(self):
        """Test _calculate_combined_score method."""
        # Test with standard weights
        base_scores = {
            "age_score": 80,
            "karma_score": 60,
            "karma_distribution_score": 90,
            "email_verified_score": 100
        }
        
        ai_analysis = {
            "viability_score": 70
        }
        
        score = self.scorer._calculate_combined_score(base_scores, ai_analysis)
        
        # Default weights: 0.25 age, 0.25 karma, 0.5 AI
        expected = 80 * 0.25 + 60 * 0.25 + 70 * 0.5
        self.assertAlmostEqual(score, expected, places=1)
        
        # Test with custom weights
        score_custom = self.custom_scorer._calculate_combined_score(base_scores, ai_analysis)
        
        # Custom weights: 0.4 age, 0.1 karma, 0.5 AI
        expected_custom = 80 * 0.4 + 60 * 0.1 + 70 * 0.5
        self.assertAlmostEqual(score_custom, expected_custom, places=1)
        
        # Test with error penalty
        ai_analysis_error = {
            "viability_score": 70,
            "error": "Analysis error"
        }
        
        score_with_error = self.scorer._calculate_combined_score(base_scores, ai_analysis_error)
        
        # Should apply 10% penalty
        expected_with_error = (80 * 0.25 + 60 * 0.25 + 70 * 0.5) * 0.9
        self.assertAlmostEqual(score_with_error, expected_with_error, places=1)
        
        # Test score clamping
        base_scores_high = {
            "age_score": 100,
            "karma_score": 100
        }
        
        ai_analysis_high = {
            "viability_score": 120  # Over 100
        }
        
        score_high = self.scorer._calculate_combined_score(base_scores_high, ai_analysis_high)
        self.assertEqual(score_high, 100.0)  # Clamped to 100
        
        base_scores_low = {
            "age_score": -10,
            "karma_score": -20
        }
        
        ai_analysis_low = {
            "viability_score": -30  # Below 0
        }
        
        score_low = self.scorer._calculate_combined_score(base_scores_low, ai_analysis_low)
        self.assertEqual(score_low, 0.0)  # Clamped to 0
    
    def test_end_to_end(self):
        """Test end-to-end scoring process with real analyzer implementations."""
        # Create a scorer with MockAnalyzer for predictable results
        end_to_end_scorer = PersonaScorer(
            analyzer_type="mock",
            mock_mode=True,
            fallback_analyzer=None
        )
        
        # Run the complete trust score calculation
        result = end_to_end_scorer.calculate_trust_score(self.persona_data)
        
        # Verify the result has all expected components
        self.assertIn("trust_score", result)
        self.assertIn("component_scores", result)
        self.assertIn("ai_analysis", result)
        self.assertIn("analysis_timestamp", result)
        self.assertIn("analyzer_used", result)
        
        # Verify score is within expected range
        self.assertGreaterEqual(result["trust_score"], 0)
        self.assertLessEqual(result["trust_score"], 100)
        
        # Verify AI analysis has expected fields
        ai_analysis = result["ai_analysis"]
        self.assertIn("viability_score", ai_analysis)
        self.assertIn("best_use_case", ai_analysis)
        self.assertIn("risk_factors", ai_analysis)
        self.assertIn("maintenance_notes", ai_analysis)
        self.assertIn("next_review_date", ai_analysis)
        
        # Verify component scores have expected fields
        component_scores = result["component_scores"]
        self.assertIn("age_score", component_scores)
        self.assertIn("karma_score", component_scores)
        self.assertIn("karma_distribution_score", component_scores)
        self.assertIn("email_verified_score", component_scores)


if __name__ == '__main__':
    unittest.main()
