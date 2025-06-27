#!/usr/bin/env python3
"""
Example script for comparing multiple AI analyzers.

This script demonstrates how to:
1. Run validation with multiple AI analyzers
2. Compare results from different analyzers
3. Generate comparative analysis reports

Usage:
    python examples/comparative_analysis.py --username reddituser123
"""

import os
import sys
import argparse
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import matplotlib.pyplot as plt
from datetime import datetime

# Add the parent directory to the path to import the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.validator import RedditPersonaValidator, ValidationResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("comparative-analysis-example")

# Define available analyzers
AVAILABLE_ANALYZERS = ["deepseek", "claude", "mock"]


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Comparative Analysis of Multiple AI Analyzers")
    
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
        "--analyzers", "-a",
        nargs="+",
        choices=AVAILABLE_ANALYZERS,
        default=["deepseek", "claude", "mock"],
        help="AI analyzers to compare (space-separated list)"
    )
    parser.add_argument(
        "--detail-level", "-d",
        choices=["basic", "medium", "full"],
        default="medium",
        help="Level of AI analysis detail"
    )
    parser.add_argument(
        "--generate-report",
        action="store_true",
        help="Generate a detailed comparative report"
    )
    parser.add_argument(
        "--report-dir",
        default="reports",
        help="Directory to save report files"
    )
    
    return parser.parse_args()


def validate_with_analyzer(
    validator: RedditPersonaValidator,
    username: str,
    analyzer_type: str,
    detail_level: str
) -> ValidationResult:
    """
    Validate a Reddit username with a specific analyzer.
    
    Args:
        validator: Initialized RedditPersonaValidator instance
        username: Reddit username to validate
        analyzer_type: Type of AI analyzer to use
        detail_level: Level of AI analysis detail
        
    Returns:
        ValidationResult object
    """
    try:
        logger.info(f"Validating {username} with {analyzer_type} analyzer")
        
        result = validator.validate(
            username=username,
            perform_email_verification=False,
            perform_ai_analysis=True,
            ai_analyzer_type=analyzer_type,
            ai_detail_level=detail_level
        )
        
        logger.info(f"Validation completed with {analyzer_type} (Trust score: {result.trust_score})")
        return result
        
    except Exception as e:
        logger.error(f"Error validating with {analyzer_type}: {str(e)}")
        return ValidationResult(
            username=username,
            exists=False,
            errors=[f"Validation error with {analyzer_type}: {str(e)}"]
        )


def compare_analyzers(
    username: str,
    analyzers: List[str],
    config_path: str,
    detail_level: str
) -> Dict[str, ValidationResult]:
    """
    Compare validation results with different AI analyzers.
    
    Args:
        username: Reddit username to validate
        analyzers: List of analyzer types to compare
        config_path: Path to the configuration file
        detail_level: Level of AI analysis detail
        
    Returns:
        Dictionary mapping analyzer types to ValidationResult objects
    """
    results = {}
    
    # Initialize validator
    validator = RedditPersonaValidator(config_path=config_path)
    
    # Run validation with each analyzer
    for analyzer in analyzers:
        result = validate_with_analyzer(
            validator=validator,
            username=username,
            analyzer_type=analyzer,
            detail_level=detail_level
        )
        results[analyzer] = result
    
    return results


def print_comparison_summary(results: Dict[str, ValidationResult]) -> None:
    """
    Print a summary comparison of results from different analyzers.
    
    Args:
        results: Dictionary mapping analyzer types to ValidationResult objects
    """
    print("\n===== ANALYZER COMPARISON SUMMARY =====")
    print(f"Username: {next(iter(results.values())).username}")
    print("\nTrust Scores:")
    
    for analyzer, result in results.items():
        trust_score = result.trust_score if result.trust_score is not None else "N/A"
        print(f"  - {analyzer:10s}: {trust_score}")
    
    print("\nAI Analysis Scores:")
    
    # Get all metrics from all analyzers
    all_metrics = set()
    for result in results.values():
        if result.ai_analysis:
            all_metrics.update(result.ai_analysis.keys())
    
    # Filter out non-score metrics
    excluded_keys = {'analyzer', 'analysis_time', 'analysis_timestamp', 'error', 
                     'mock', 'fallback', 'best_use_case', 'risk_factors', 
                     'maintenance_notes'}
    score_metrics = [m for m in all_metrics if m not in excluded_keys and not m.startswith('_')]
    
    # Print comparison of each metric
    for metric in sorted(score_metrics):
        print(f"\n  {metric.replace('_', ' ').title()}:")
        for analyzer, result in results.items():
            value = "N/A"
            if result.ai_analysis and metric in result.ai_analysis:
                value = result.ai_analysis[metric]
            print(f"    - {analyzer:10s}: {value}")
    
    print("\nBest Use Cases:")
    for analyzer, result in results.items():
        use_cases = []
        if result.ai_analysis and 'best_use_case' in result.ai_analysis:
            use_cases = result.ai_analysis['best_use_case']
        print(f"  - {analyzer}:")
        for case in use_cases:
            print(f"    * {case}")
    
    print("\nRisk Factors:")
    for analyzer, result in results.items():
        risks = []
        if result.ai_analysis and 'risk_factors' in result.ai_analysis:
            risks = result.ai_analysis['risk_factors']
        print(f"  - {analyzer}:")
        for risk in risks:
            print(f"    * {risk}")
    
    print("=======================================\n")


def generate_comparative_report(
    results: Dict[str, ValidationResult],
    report_dir: str,
    detail_level: str
) -> Tuple[str, str]:
    """
    Generate a detailed comparative report with visualizations.
    
    Args:
        results: Dictionary mapping analyzer types to ValidationResult objects
        report_dir: Directory to save report files
        detail_level: Level of AI analysis detail used
        
    Returns:
        Tuple of (report_path, chart_path)
    """
    # Create report directory
    report_path = Path(report_dir)
    report_path.mkdir(parents=True, exist_ok=True)
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    username = next(iter(results.values())).username
    
    # Create filenames
    report_file = report_path / f"comparative_report_{username}_{timestamp}.txt"
    chart_file = report_path / f"comparative_chart_{username}_{timestamp}.png"
    
    # Extract metrics for comparison
    metrics = {}
    for analyzer, result in results.items():
        if result.ai_analysis:
            # Filter out non-score metrics
            excluded_keys = {'analyzer', 'analysis_time', 'analysis_timestamp', 'error', 
                           'mock', 'fallback', 'best_use_case', 'risk_factors', 
                           'maintenance_notes'}
            metrics[analyzer] = {k: v for k, v in result.ai_analysis.items() 
                                if k not in excluded_keys and not k.startswith('_') 
                                and isinstance(v, (int, float))}
    
    # Generate report text
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"=== COMPARATIVE ANALYSIS REPORT ===\n")
        f.write(f"Username: {username}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Detail Level: {detail_level}\n\n")
        
        # Trust scores
        f.write("== TRUST SCORES ==\n")
        for analyzer, result in results.items():
            trust_score = result.trust_score if result.trust_score is not None else "N/A"
            f.write(f"{analyzer:10s}: {trust_score}\n")
        f.write("\n")
        
        # Account details
        first_result = next(iter(results.values()))
        if first_result.account_details:
            f.write("== ACCOUNT DETAILS ==\n")
            for key, value in first_result.account_details.items():
                if key != "warnings":  # Skip warnings
                    f.write(f"{key:15s}: {value}\n")
            f.write("\n")
        
        # Detailed metrics comparison
        f.write("== DETAILED METRICS COMPARISON ==\n")
        common_metrics = set.intersection(*(set(m.keys()) for m in metrics.values())) if metrics else set()
        
        for metric in sorted(common_metrics):
            f.write(f"\n{metric.replace('_', ' ').title()}:\n")
            for analyzer, scores in metrics.items():
                f.write(f"  {analyzer:10s}: {scores.get(metric, 'N/A')}\n")
        f.write("\n")
        
        # Analysis recommendations
        f.write("== ANALYZER RECOMMENDATIONS ==\n")
        for analyzer, result in results.items():
            f.write(f"\n{analyzer.upper()} RECOMMENDATIONS:\n")
            
            # Best use cases
            use_cases = []
            if result.ai_analysis and 'best_use_case' in result.ai_analysis:
                use_cases = result.ai_analysis['best_use_case']
            f.write(f"Best Use Cases:\n")
            for case in use_cases:
                f.write(f"  * {case}\n")
            
            # Risk factors
            risks = []
            if result.ai_analysis and 'risk_factors' in result.ai_analysis:
                risks = result.ai_analysis['risk_factors']
            f.write(f"Risk Factors:\n")
            for risk in risks:
                f.write(f"  * {risk}\n")
            
            # Maintenance notes
            if result.ai_analysis and 'maintenance_notes' in result.ai_analysis:
                f.write(f"Maintenance Notes:\n")
                f.write(f"  {result.ai_analysis['maintenance_notes']}\n")
        
    # Generate comparison chart
    if metrics:
        common_metrics = set.intersection(*(set(m.keys()) for m in metrics.values()))
        if common_metrics:
            # Prepare data for chart
            labels = sorted(common_metrics)
            analyzer_data = {}
            
            for analyzer, scores in metrics.items():
                analyzer_data[analyzer] = [scores.get(metric, 0) for metric in labels]
            
            # Create chart
            plt.figure(figsize=(12, 8))
            
            # Set width of bars
            bar_width = 0.2
            positions = range(len(labels))
            
            # Create bars
            for i, (analyzer, data) in enumerate(analyzer_data.items()):
                offset = (i - len(analyzer_data) / 2 + 0.5) * bar_width
                plt.bar([p + offset for p in positions], data, bar_width, 
                        label=analyzer, alpha=0.7)
            
            # Add labels and title
            plt.xlabel('Metrics')
            plt.ylabel('Score')
            plt.title(f'Comparative Analysis for {username}')
            plt.xticks([p for p in positions], [l.replace('_', ' ').title() for l in labels], rotation=45, ha='right')
            plt.legend()
            plt.tight_layout()
            
            # Save chart
            plt.savefig(chart_file)
            plt.close()
    
    logger.info(f"Comparative report saved to {report_file}")
    if metrics and common_metrics:
        logger.info(f"Comparative chart saved to {chart_file}")
    
    return str(report_file), str(chart_file) if metrics and common_metrics else ""


def save_results(results: Dict[str, ValidationResult], output_file: str) -> None:
    """
    Save comparison results to a JSON file.
    
    Args:
        results: Dictionary mapping analyzer types to ValidationResult objects
        output_file: Path to the output file
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert results to dictionaries
    results_dict = {analyzer: result.to_dict() for analyzer, result in results.items()}
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results_dict, f, indent=2)
        
    logger.info(f"Results saved to {output_file}")


def main() -> None:
    """Main entry point for the script."""
    # Parse arguments
    args = parse_arguments()
    
    try:
        # Run comparative analysis
        results = compare_analyzers(
            username=args.username,
            analyzers=args.analyzers,
            config_path=args.config,
            detail_level=args.detail_level
        )
        
        # Print comparison summary
        print_comparison_summary(results)
        
        # Generate detailed report if requested
        if args.generate_report:
            report_file, chart_file = generate_comparative_report(
                results=results,
                report_dir=args.report_dir,
                detail_level=args.detail_level
            )
            
            print(f"Detailed report saved to: {report_file}")
            if chart_file:
                print(f"Comparison chart saved to: {chart_file}")
        
        # Save results if output file specified
        if args.output:
            save_results(results, args.output)
            
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
