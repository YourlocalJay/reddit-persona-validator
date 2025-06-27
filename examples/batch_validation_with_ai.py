#!/usr/bin/env python3
"""
Example script for batch validation with AI analysis.

This script demonstrates how to:
1. Load Reddit usernames from a file
2. Perform batch validation with AI analysis
3. Output detailed results

Usage:
    python examples/batch_validation_with_ai.py --input usernames.txt --output results.json
"""

import os
import sys
import argparse
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.validator import RedditPersonaValidator, ValidationResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("batch-validation-example")


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Batch Reddit Persona Validation with AI Analysis")
    
    parser.add_argument(
        "--input", "-i", 
        required=True,
        help="Input file with Reddit usernames (one per line)"
    )
    parser.add_argument(
        "--output", "-o", 
        default="results.json",
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
        "--detail-level", "-d",
        choices=["none", "basic", "medium", "full"],
        default="medium",
        help="Level of AI analysis detail"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=2,
        help="Number of concurrent validation workers"
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI analysis"
    )
    
    return parser.parse_args()


def load_usernames(input_file: str) -> List[str]:
    """
    Load Reddit usernames from a file.
    
    Args:
        input_file: Path to the input file
        
    Returns:
        List of usernames
        
    Raises:
        FileNotFoundError: If the input file does not exist
    """
    file_path = Path(input_file)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    
    usernames = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            username = line.strip()
            if username and not username.startswith('#'):
                usernames.append(username)
                
    return usernames


def save_results(results: List[ValidationResult], output_file: str) -> None:
    """
    Save validation results to a JSON file.
    
    Args:
        results: List of ValidationResult objects
        output_file: Path to the output file
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert results to dictionaries
    results_dict = [result.to_dict() for result in results]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results_dict, f, indent=2)
        
    logger.info(f"Results saved to {output_file}")


def validate_username(
    validator: RedditPersonaValidator,
    username: str,
    perform_ai_analysis: bool,
    ai_analyzer_type: str,
    ai_detail_level: str
) -> ValidationResult:
    """
    Validate a single Reddit username.
    
    Args:
        validator: Initialized RedditPersonaValidator instance
        username: Reddit username to validate
        perform_ai_analysis: Whether to perform AI analysis
        ai_analyzer_type: Type of AI analyzer to use
        ai_detail_level: Level of AI analysis detail
        
    Returns:
        ValidationResult object
    """
    try:
        logger.info(f"Validating username: {username}")
        
        result = validator.validate(
            username=username,
            perform_email_verification=False,
            perform_ai_analysis=perform_ai_analysis,
            ai_analyzer_type=ai_analyzer_type,
            ai_detail_level=ai_detail_level
        )
        
        logger.info(f"Validation completed for {username} (Trust score: {result.trust_score})")
        return result
        
    except Exception as e:
        logger.error(f"Error validating {username}: {str(e)}")
        return ValidationResult(
            username=username,
            exists=False,
            errors=[f"Validation error: {str(e)}"]
        )


def print_summary(results: List[ValidationResult]) -> None:
    """
    Print a summary of validation results.
    
    Args:
        results: List of ValidationResult objects
    """
    valid_count = sum(1 for r in results if r.exists)
    with_ai_count = sum(1 for r in results if r.ai_analysis is not None)
    
    high_trust = sum(1 for r in results if r.trust_score is not None and r.trust_score >= 70)
    medium_trust = sum(1 for r in results if r.trust_score is not None and 40 <= r.trust_score < 70)
    low_trust = sum(1 for r in results if r.trust_score is not None and r.trust_score < 40)
    
    print("\n===== VALIDATION SUMMARY =====")
    print(f"Total accounts processed: {len(results)}")
    print(f"Valid accounts: {valid_count} ({valid_count/len(results)*100:.1f}%)")
    print(f"With AI analysis: {with_ai_count}")
    print(f"Trust score distribution:")
    print(f"  - High (70-100): {high_trust}")
    print(f"  - Medium (40-69): {medium_trust}")
    print(f"  - Low (0-39): {low_trust}")
    print("=============================\n")


def main() -> None:
    """Main entry point for the script."""
    # Parse arguments
    args = parse_arguments()
    
    try:
        # Load usernames
        usernames = load_usernames(args.input)
        logger.info(f"Loaded {len(usernames)} usernames from {args.input}")
        
        # Initialize validator
        validator = RedditPersonaValidator(config_path=args.config)
        logger.info(f"Initialized validator with config from {args.config}")
        
        # Validate usernames in parallel
        results = []
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_username = {
                executor.submit(
                    validate_username,
                    validator,
                    username,
                    not args.skip_ai,
                    args.analyzer,
                    args.detail_level
                ): username for username in usernames
            }
            
            for future in as_completed(future_to_username):
                username = future_to_username[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing {username}: {str(e)}")
                    results.append(ValidationResult(
                        username=username,
                        exists=False,
                        errors=[f"Processing error: {str(e)}"]
                    ))
        
        # Save results
        save_results(results, args.output)
        
        # Print summary
        print_summary(results)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
