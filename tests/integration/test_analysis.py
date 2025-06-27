import pytest
from src.analysis.deepseek_adapter import DeepSeekAnalyzer

@pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="Needs API key")
def test_real_analysis():
    analyzer = DeepSeekAnalyzer(mock_mode=False)
    result = analyzer.analyze({"Karma": "5000"})
    assert "viability_score" in result
