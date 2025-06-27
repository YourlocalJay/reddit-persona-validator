#!/usr/bin/env python3
"""
Example script demonstrating how to customize scoring weights.

This script shows how to:
1. Create a custom scoring configuration
2. Apply different weight profiles for different use cases
3. Compare results with different scoring configurations

Usage:
    python examples/customize_scoring_weights.py --username reddituser123
"""

import os
import sys
import argparse
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pprint

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.validator import RedditPersonaValidator, ValidationResult
from src.analysis.scorer import PersonaScorer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("custom-scoring-example")


# Define different scoring weight profiles for different use cases
SCORING_PROFILES = {
    "balanced": {
        "account_age": 0.25,
        "karma": 0.25,
        "ai_analysis": 0.5
    },
    "age_priority": {
        "account_age": 0.5,
        "karma": 0.2,
        "ai_analysis": 0.3
    },
    "ai_priority": {
        "account_age": 0.15,
        "karma": 0.15,
        "ai_analysis": 0.7
    },
    "karma_priority": {
        "account_age": 0.2,
        "karma": 0.6,
        "ai_analysis": 0.2
    }
}

# Define AI analysis component weights for different use cases
AI_COMPONENT_WEIGHTS = {
    "standard": {
        "content_coherence": 0.25,
        "language_quality": 0.20,
        "account_consistency": 0.25,
        "behavioral_patterns": 0.30
    },
    "authenticity_focus": {
        "content_coherence": 0.35,
        "language_quality": 0.15,
        "account_consistency": 0.35,
        "behavioral_patterns": 0.15
    },
    "behavior_focus": {
        "content_coherence": 0.15,
        "language_quality": 0.15,
        "account_consistency": 0.30,
        "behavioral_patterns": 0.40
    }
}


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Custom Scoring Weights Example")
    
    parser.add_argument(
        "--username", "-u", 
        required=True,
        help="Reddit username to validate"
    )
    parser.add_argument(
        "--output", "-o", 
        help="Output file path for results (JSON format)"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--analyzer", "-a",
        choices=["deepseek", "claude", "mock"],
        default="deepseek",
        help="AI analyzer to use"
    )
    parser.add_argument(
        "--profile", "-p",
        choices=list(SCORING_PROFILES.keys()),
        default="balanced",
        help="Scoring weight profile to use"
    )
    parser.add_argument(
        "--ai-weights", "-w",
        choices=list(AI_COMPONENT_WEIGHTS.keys()),
        default="standard",
        help="AI component weight profile to use"
    )
    parser.add_argument(
        "--compare-all",
        action="store_true",
        help="Compare all scoring profiles"
    )
    
    return parser.parse_args()


def create_custom_validator(
    config_path: str,
    scoring_weights: Dict[str, float],
    ai_component_weights: Dict[str, float],
    analyzer_type: str
) -> RedditPersonaValidator:
    """
    Create a RedditPersonaValidator with custom scoring configuration.
    
    Args:
        config_path: Path to the configuration file
        scoring_weights: Dictionary of scoring weights
        ai_component_weights: Dictionary of AI component weights
        analyzer_type: Type of AI analyzer to use
        
    Returns:
        Customized RedditPersonaValidator instance
    """
    # Initialize the validator with the standard config
    validator = RedditPersonaValidator(config_path=config_path)
    
    # Create a custom PersonaScorer with the specified weights
    custom_scorer = PersonaScorer(
        analyzer_type=analyzer_type,
        mock_mode=False,
        fallback_analyzer="mock",
        scoring_weights=scoring_weights
    )
    
    # Apply AI component weights if the analyzer supports it
    if hasattr(custom_scorer, "set_component_weights") and callable(getattr(custom_scorer, "set_component_weights")):
        custom_scorer.set_component_weights(ai_component_weights)
    else:
        logger.warning("AI component weights cannot be set on this scorer implementation")
    
    # Replace the validator's scorer with our custom one
    validator.persona_scorer = custom_scorer
    
    return validator


def validate_with_custom_weights(
    username: str,
    config_path: str,
    scoring_profile: str,
    ai_weights_profile: str,
    analyzer_type: str
) -> Dict[str, Any]:
    """
    Validate a Reddit username with custom scoring weights.
    
    Args:
        username: Reddit username to validate
        config_path: Path to the configuration file
        scoring_profile: Name of the scoring profile to use
        ai_weights_profile: Name of the AI component weights profile to use
        analyzer_type: Type of AI analyzer to use
        
    Returns:
        Dictionary with validation results and metadata
    """
    # Get scoring weights from profile
    scoring_weights = SCORING_PROFILES.get(scoring_profile, SCORING_PROFILES["balanced"])
    ai_component_weights = AI_COMPONENT_WEIGHTS.get(ai_weights_profile, AI_COMPONENT_WEIGHTS["standard"])
    
    logger.info(f"Validating {username} with {scoring_profile} scoring profile and {ai_weights_profile} AI weights")
    logger.info(f"Scoring weights: {scoring_weights}")
    logger.info(f"AI component weights: {ai_component_weights}")
    
    # Create custom validator
    validator = create_custom_validator(
        config_path=config_path,
        scoring_weights=scoring_weights,
        ai_component_weights=ai_component_weights,
        analyzer_type=analyzer_type
    )
    
    # Validate the username
    result = validator.validate(
        username=username,
        perform_email_verification=False,
        perform_ai_analysis=True,
        ai_analyzer_type=analyzer_type,
        ai_detail_level="medium"
    )
    
    # Add metadata about the scoring configuration
    result_dict = result.to_dict()
    result_dict["_metadata"] = {
        "scoring_profile": scoring_profile,
        "ai_weights_profile": ai_weights_profile,
        "scoring_weights": scoring_weights,
        "ai_component_weights": ai_component_weights,
        "analyzer_type": analyzer_type
    }
    
    return result_dict


def compare_scoring_profiles(
    username: str,
    config_path: str,
    analyzer_type: str,
    ai_weights_profile: str
) -> Dict[str, Dict[str, Any]]:
    """
    Compare validation results with different scoring profiles.
    
    Args:
        username: Reddit username to validate
        config_path: Path to the configuration file
        analyzer_type: Type of AI analyzer to use
        ai_weights_profile: Name of the AI component weights profile to use
        
    Returns:
        Dictionary with results for each scoring profile
    """
    results = {}
    
    for profile_name in SCORING_PROFILES.keys():
        results[profile_name] = validate_with_custom_weights(
            username=username,
            config_path=config_path,
            scoring_profile=profile_name,
            ai_weights_profile=ai_weights_profile,
            analyzer_type=analyzer_type
        )
    
    return results


def print_results_comparison(results: Dict[str, Dict[str, Any]]) -> None:
    """
    Print a comparison of validation results with different scoring profiles.
    
    Args:
        results: Dictionary with results for each scoring profile
    """
    print("\n===== SCORING PROFILE COMPARISON =====")
    print(f"Username: {next(iter(results.values()))['username']}")
    print("\nTrust Scores:")
    
    for profile, result in results.items():
        trust_score = result.get("trust_score", "N/A")
        weights = result.get("_metadata", {}).get("scoring_weights", {})
        weights_str = ", ".join(f"{k}={v}" for k, v in weights.items())
        print(f"  - {profile:15s}: {trust_score:5.1f}  (weights: {weights_str})")
    
    print("\nScore Components:")
    
    # Extract account details from the first result
    first_result = next(iter(results.values()))
    account_details = first_result.get("account_details", {})
    ai_analysis = first_result.get("ai_analysis", {})
    
    print(f"  - Account Age: {account_details.get('age_days', 'N/A')} days")
    print(f"  - Karma: {account_details.get('karma', 'N/A')}")
    
    # Print AI analysis scores if available
    if ai_analysis:
        print(f"  - AI Viability Score: {ai_analysis.get('viability_score', 'N/A')}")
        for key in ['content_coherence', 'language_quality', 'account_consistency', 'behavioral_patterns']:
            if key in ai_analysis:
                print(f"  - AI {key.replace('_', ' ').title()}: {ai_analysis.get(key, 'N/A')}")
    
    print("=====================================\n")


def save_results(results: Dict[str, Dict[str, Any]], output_file: str) -> None:
    """
    Save comparison results to a JSON file.
    
    Args:
        results: Dictionary with results for each scoring profile
        output_file: Path to the output file
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    logger.info(f"Results saved to {output_file}")


def main() -> None:
    """Main entry point for the script."""
    # Parse arguments
    args = parse_arguments()
    
    try:
        if args.compare_all:
            # Compare all scoring profiles
            results = compare_scoring_profiles(
                username=args.username,
                config_path=args.config,
                analyzer_type=args.analyzer,
                ai_weights_profile=args.ai_weights
            )
            
            # Print comparison
            print_results_comparison(results)
            
            # Save results if output file specified
            if args.output:
                save_results(results, args.output)
                
        else:
            # Validate with single custom profile
            result = validate_with_custom_weights(
                username=args.username,
                config_path=args.config,
                scoring_profile=args.profile,
                ai_weights_profile=args.ai_weights,
                analyzer_type=args.analyzer
            )
            
            # Print result
            print("\n===== VALIDATION RESULT =====")
            print(f"Username: {result['username']}")
            print(f"Trust Score: {result['trust_score']}")
            print("\nScoring Configuration:")
            print(f"  Profile: {args.profile}")
            print(f"  AI Weights: {args.ai_weights}")
            print(f"  Analyzer: {args.analyzer}")
            print("\nScore Components:")
            
            # Extract account details
            account_details = result.get("account_details", {})
            ai_analysis = result.get("ai_analysis", {})
            
            print(f"  - Account Age: {account_details.get('age_days', 'N/A')} days")
            print(f"  - Karma: {account_details.get('karma', 'N/A')}")
            
            # Print AI analysis scores if available
            if ai_analysis:
                print(f"  - AI Viability Score: {ai_analysis.get('viability_score', 'N/A')}")
                for key in ['content_coherence', 'language_quality', 'account_consistency', 'behavioral_patterns']:
                    if key in ai_analysis:
                        print(f"  - AI {key.replace('_', ' ').title()}: {ai_analysis.get(key, 'N/A')}")
            
            print("=============================\n")
            
            # Save result if output file specified
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2)
                logger.info(f"Result saved to {args.output}")
                
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
