import pytest
from src.analysis.scorer import PersonaScorer

@pytest.fixture
def mock_scorer():
    return PersonaScorer(mock_mode=True)

def test_scoring(mock_scorer):
    result = mock_scorer.calculate_trust_score({
        "Karma": "1000",
        "Account Age (yrs)": "1.5"
    })
    assert 0 <= result["trust_score"] <= 100
