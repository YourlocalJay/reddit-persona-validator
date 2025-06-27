"""Command-line interface for Reddit persona validation.

This module provides a feature-rich command-line interface for the Reddit Persona Validator
with support for:
- Single account validation
- Batch processing from input files
- Multiple output formats (JSON, CSV, table)
- Colorized and formatted output
- Progress tracking
- AI analysis with configurable options

Example usage:
    # Validate a single account
    python -m src.interfaces.cli --username reddituser123

    # Batch process accounts from a file
    python -m src.interfaces.cli --input accounts.txt --format json --output results.json

    # Validate with specific AI analyzer
    python -m src.interfaces.cli --username reddituser123 --ai-analyzer claude --ai-detail full
"""

import os
import sys
import time
import json
import argparse
import logging
import csv
from pathlib import Path
from typing import Dict, Optional, List, Any, Union, TextIO, Iterator, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Rich for beautiful terminal output
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich.syntax import Syntax

# Validator core
from ..core.validator import RedditPersonaValidator, ValidationResult

# Set up rich console
console = Console()

# Configure logger with rich handler
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)]
)

logger = logging.getLogger("persona-validator-cli")


class PersonaValidatorCLI:
    """CLI interface for the Reddit Persona Validator."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the CLI interface.

        Args:
            config_path: Optional path to the configuration file
        """
        self.config_path = config_path or "config/config.yaml"
        self.validator = None

    def _init_validator(self) -> RedditPersonaValidator:
        """
        Initialize the validator if not already initialized.

        Returns:
            Initialized RedditPersonaValidator instance
        """
        if not self.validator:
            try:
                self.validator = RedditPersonaValidator(config_path=self.config_path)
            except Exception as e:
                logger.error(f"Error initializing validator: {str(e)}")
                sys.exit(1)
        return self.validator

    def validate_single_account(self,
                               username: str,
                               email: Optional[str] = None,
                               perform_email_verification: bool = False,
                               perform_ai_analysis: bool = True,
                               ai_analyzer_type: Optional[str] = None,
                               ai_detail_level: str = "medium") -> ValidationResult:
        """
        Validate a single Reddit account.

        Args:
            username: Reddit username to validate
            email: Optional email to verify
            perform_email_verification: Whether to perform email verification
            perform_ai_analysis: Whether to perform AI analysis
            ai_analyzer_type: Type of AI analyzer to use (deepseek, claude, mock)
            ai_detail_level: Level of AI analysis detail (none, basic, medium, full)

        Returns:
            ValidationResult object containing validation results
        """
        validator = self._init_validator()

        with console.status(f"[bold green]Validating Reddit account: {username}[/bold green]", spinner="dots"):
            try:
                result = validator.validate(
                    username=username,
                    email_address=email,
                    perform_email_verification=perform_email_verification,
                    perform_ai_analysis=perform_ai_analysis,
                    ai_analyzer_type=ai_analyzer_type,
                    ai_detail_level=ai_detail_level
                )
                # Add warning if AI analysis was requested but result is None
                if perform_ai_analysis and not result.ai_analysis:
                    result.warnings.append("AI analysis failed or returned no result")
                return result
            except Exception as e:
                logger.error(f"Validation failed: {str(e)}")
                return ValidationResult(
                    username=username,
                    exists=False,
                    errors=[f"Validation error: {str(e)}"]
                )

    def _read_accounts_from_file(self, input_file: str) -> List[Dict[str, str]]:
        """
        Read account details from input file. Supports CSV and text formats.

        Args:
            input_file: Path to input file

        Returns:
            List of dictionaries with account details

        Raises:
            FileNotFoundError: If input file does not exist
            ValueError: If input file format is invalid
        """
        file_path = Path(input_file)

        if not file_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        accounts = []

        # Determine file type
        extension = file_path.suffix.lower()

        try:
            if extension == '.csv':
                with open(file_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if 'username' not in row:
                            raise ValueError("CSV file must contain a 'username' column")
                        accounts.append(row)
            else:
                # Assume it's a simple text file with one username per line
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            accounts.append({'username': line})

        except Exception as e:
            raise ValueError(f"Error reading input file: {str(e)}")

        return accounts

    def _write_results(self, results: List[ValidationResult], output_file: str,
                     output_format: str) -> None:
        """
        Write validation results to output file in the specified format.

        Args:
            results: List of ValidationResult objects
            output_file: Path to output file
            output_format: Output format (json, csv, or table)

        Raises:
            ValueError: If output format is invalid
        """
        output_path = Path(output_file)

        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_format == 'json':
            with open(output_path, 'w', encoding='utf-8') as f:
                results_dict = [r.to_dict() for r in results]
                json.dump(results_dict, f, indent=2)
        elif output_format == 'csv':
            logger.info(f"Writing CSV to {output_path}")
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                # Flatten the structure for CSV
                fieldnames = [
                    'username', 'exists', 'trust_score', 'email_verified',
                    'age_days', 'karma', 'cake_day', 'verified_email',
                    'ai_analysis_score', 'ai_analyzer_used', 'warnings', 'errors'
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for result in results:
                    row = {
                        'username': result.username,
                        'exists': result.exists,
                        'trust_score': result.trust_score,
                        'email_verified': result.email_verified,
                        'warnings': '; '.join(result.warnings or []),
                        'errors': '; '.join(result.errors or [])
                    }
                    # Add account details if available
                    if result.account_details:
                        row.update({
                            'age_days': result.account_details.get('age_days', ''),
                            'karma': result.account_details.get('karma', ''),
                            'cake_day': result.account_details.get('cake_day', ''),
                            'verified_email': result.account_details.get('verified_email', '')
                        })
                    # Add AI analysis details if available
                    if result.ai_analysis:
                        row.update({
                            'ai_analysis_score': result.ai_analysis.get('viability_score', ''),
                            'ai_analyzer_used': result.ai_analysis.get('analyzer', '')
                        })
                    writer.writerow(row)
        elif output_format == 'yaml':
            import yaml
            with open(output_path, 'w', encoding='utf-8') as f:
                results_dict = [r.to_dict() for r in results]
                yaml.dump(results_dict, f, sort_keys=False, allow_unicode=True)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")

    def _print_result_table(self, results: List[ValidationResult], show_ai_details: bool = False) -> None:
        """
        Print validation results as a formatted table in the terminal.

        Args:
            results: List of ValidationResult objects
            show_ai_details: Whether to show detailed AI analysis
        """
        logger.debug("Rendering results table to console")
        table = Table(title="Reddit Persona Validation Results")

        # Define columns
        table.add_column("Username", style="cyan")
        table.add_column("Exists", style="green")
        table.add_column("Trust Score", style="magenta")
        table.add_column("Age (days)")
        table.add_column("Karma")
        table.add_column("Email Verified")
        if show_ai_details:
            table.add_column("AI Score", style="blue")
            table.add_column("Analyzer")
        table.add_column("Status", style="yellow")

        # Add rows
        for result in results:
            # Determine status color
            status = ""
            status_style = "green"

            if result.errors and len(result.errors) > 0:
                status = "; ".join(result.errors)
                status_style = "red"
            elif result.warnings and len(result.warnings) > 0:
                status = "; ".join(result.warnings)
                status_style = "yellow"
            elif result.exists:
                status = "Valid account"

            # Format trust score with color
            trust_score = str(result.trust_score) if result.trust_score is not None else "N/A"

            # Prepare row data
            row_data = [
                result.username,
                "✓" if result.exists else "✗",
                trust_score,
                str(result.account_details.get('age_days', 'N/A')) if result.account_details else "N/A",
                str(result.account_details.get('karma', 'N/A')) if result.account_details else "N/A",
                "✓" if result.email_verified else "✗" if result.email_verified is not None else "N/A"
            ]

            # Add AI details if requested
            if show_ai_details:
                ai_score = "N/A"
                analyzer = "N/A"
                if result.ai_analysis:
                    ai_score = str(result.ai_analysis.get('viability_score', 'N/A'))
                    analyzer = result.ai_analysis.get('analyzer', 'N/A')
                row_data.extend([ai_score, analyzer])

            # Add status
            row_data.append(Text(status, style=status_style))

            # Add row to table
            table.add_row(*row_data)

        console.print(table)

        # If showing AI details and there are results with AI analysis, print detailed reports
        if show_ai_details:
            for result in results:
                if result.ai_analysis and result.exists:
                    self._print_ai_analysis_details(result)

    def _print_ai_analysis_details(self, result: ValidationResult) -> None:
        """
        Print detailed AI analysis for a validation result.

        Args:
            result: ValidationResult object containing AI analysis
        """
        if not result.ai_analysis:
            return

        ai_analysis = result.ai_analysis

        # Create a tree for structured display
        tree = Tree(f"[bold cyan]AI Analysis for {result.username}[/bold cyan]")

        # Add viability score
        viability_score = ai_analysis.get('viability_score')
        if viability_score is not None:
            score_color = "green" if viability_score >= 70 else "yellow" if viability_score >= 40 else "red"
            tree.add(f"[bold {score_color}]Viability Score: {viability_score}[/bold {score_color}]")

        # Add best use cases
        best_use_cases = ai_analysis.get('best_use_case', [])
        if best_use_cases:
            use_cases_node = tree.add("[bold blue]Best Use Cases[/bold blue]")
            for use_case in best_use_cases:
                use_cases_node.add(use_case)

        # Add risk factors
        risk_factors = ai_analysis.get('risk_factors', [])
        if risk_factors:
            risks_node = tree.add("[bold red]Risk Factors[/bold red]")
            for risk in risk_factors:
                risks_node.add(risk)

        # Add maintenance notes
        maintenance_notes = ai_analysis.get('maintenance_notes')
        if maintenance_notes:
            tree.add(f"[bold yellow]Maintenance Notes:[/bold yellow] {maintenance_notes}")

        # Add analysis timestamp
        timestamp = ai_analysis.get('analysis_timestamp')
        if timestamp:
            tree.add(f"[dim]Analysis Time: {timestamp}[/dim]")

        # Add analyzer used
        analyzer = ai_analysis.get('analyzer')
        if analyzer:
            tree.add(f"[dim]Analyzer: {analyzer}[/dim]")

        # Print the tree
        console.print()
        console.print(Panel(tree, title=f"AI Analysis Report", border_style="blue"))
        console.print()

    def validate_batch(self,
                       input_file: str,
                       output_file: Optional[str] = None,
                       output_format: str = 'table',
                       perform_email_verification: bool = False,
                       perform_ai_analysis: bool = True,
                       ai_analyzer_type: Optional[str] = None,
                       ai_detail_level: str = "medium",
                       show_ai_details: bool = False,
                       max_workers: int = 1) -> List[ValidationResult]:
        """
        Validate multiple Reddit accounts from an input file.

        Args:
            input_file: Path to input file
            output_file: Optional path to output file
            output_format: Output format (json, csv, or table)
            perform_email_verification: Whether to perform email verification
            perform_ai_analysis: Whether to perform AI analysis
            ai_analyzer_type: Type of AI analyzer to use (deepseek, claude, mock)
            ai_detail_level: Level of AI analysis detail (none, basic, medium, full)
            show_ai_details: Whether to show detailed AI analysis in terminal output
            max_workers: Maximum number of concurrent workers

        Returns:
            List of ValidationResult objects

        Raises:
            FileNotFoundError: If input file does not exist
            ValueError: If input file format is invalid
        """
        # Read accounts from input file
        accounts = self._read_accounts_from_file(input_file)

        if not accounts:
            console.print("[yellow]No accounts found in the input file.[/yellow]")
            return []

        console.print(f"[green]Found {len(accounts)} accounts to validate.[/green]")

        # Initialize validator
        self._init_validator()

        results = []

        # Set up progress bar
        with Progress(
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TaskProgressColumn(),
            TextColumn("• [bold]{task.fields[username]}[/bold]"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"[green]Validating {len(accounts)} accounts...",
                total=len(accounts),
                username="Starting..."
            )

            # Serial or parallel processing based on max_workers
            if max_workers > 1:
                # Parallel processing
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_account = {
                        executor.submit(
                            self.validate_single_account,
                            account['username'],
                            account.get('email'),
                            perform_email_verification,
                            perform_ai_analysis,
                            ai_analyzer_type,
                            ai_detail_level
                        ): account for account in accounts
                    }

                    for future in as_completed(future_to_account):
                        account = future_to_account[future]
                        try:
                            result = future.result()
                            results.append(result)
                            progress.update(task, advance=1, username=account['username'])
                        except Exception as e:
                            logger.error(f"Error validating {account['username']}: {str(e)}")
                            results.append(ValidationResult(
                                username=account['username'],
                                exists=False,
                                errors=[f"Validation error: {str(e)}"]
                            ))
                            progress.update(task, advance=1, username=account['username'])
            else:
                # Serial processing
                for account in accounts:
                    username = account['username']
                    progress.update(task, username=username)

                    try:
                        result = self.validate_single_account(
                            username=username,
                            email=account.get('email'),
                            perform_email_verification=perform_email_verification,
                            perform_ai_analysis=perform_ai_analysis,
                            ai_analyzer_type=ai_analyzer_type,
                            ai_detail_level=ai_detail_level
                        )
                        results.append(result)
                    except Exception as e:
                        logger.error(f"Error validating {username}: {str(e)}")
                        results.append(ValidationResult(
                            username=username,
                            exists=False,
                            errors=[f"Validation error: {str(e)}"]
                        ))

                    progress.update(task, advance=1)

        # Write results to output file if requested
        if output_file and output_format in ['json', 'csv']:
            try:
                self._write_results(results, output_file, output_format)
                console.print(f"[green]Results written to {output_file}[/green]")
            except Exception as e:
                console.print(f"[bold red]Error writing results:[/bold red] {str(e)}")

        # Print results as table if requested
        if output_format == 'table' or not output_file:
            self._print_result_table(results, show_ai_details=show_ai_details)

        # Optional histogram summary
        from collections import Counter
        from rich.bar import Bar
        from rich.columns import Columns

        # Optional histogram summary
        if results:
            score_bins = [0, 20, 40, 60, 80, 100]
            bin_labels = ["0–20", "21–40", "41–60", "61–80", "81–100"]
            bucket_counts = Counter()
            for r in results:
                if r.trust_score is not None:
                    score = r.trust_score
                    for i, upper in enumerate(score_bins[1:], 1):
                        if score <= upper:
                            bucket_counts[bin_labels[i - 1]] += 1
                            break
            histogram = [
                Bar(size=bucket_counts.get(label, 0), total=len(results), label=label)
                for label in bin_labels
            ]
            console.print(Panel(Columns(histogram), title="Trust Score Distribution", border_style="cyan"))

        return results

    def run(self, args: Optional[List[str]] = None) -> None:
        """
        Run the CLI with the given arguments.

        Args:
            args: Command-line arguments (defaults to sys.argv[1:])
        """
        parser = self._create_argument_parser()
        parsed_args = parser.parse_args(args if args is not None else sys.argv[1:])

        # Set log level
        log_level = getattr(logging, parsed_args.log_level.upper())
        logger.setLevel(log_level)

        # Print welcome banner
        self._print_banner()

        # Run in appropriate mode
        try:
            if parsed_args.input:
                # Batch mode
                self.validate_batch(
                    input_file=parsed_args.input,
                    output_file=parsed_args.output,
                    output_format=parsed_args.format,
                    perform_email_verification=parsed_args.verify_email,
                    perform_ai_analysis=parsed_args.ai_analysis,
                    ai_analyzer_type=parsed_args.ai_analyzer,
                    ai_detail_level=parsed_args.ai_detail,
                    show_ai_details=parsed_args.show_ai_details,
                    max_workers=parsed_args.workers
                )
            elif parsed_args.username:
                # Single account mode
                result = self.validate_single_account(
                    username=parsed_args.username,
                    email=parsed_args.email,
                    perform_email_verification=parsed_args.verify_email,
                    perform_ai_analysis=parsed_args.ai_analysis,
                    ai_analyzer_type=parsed_args.ai_analyzer,
                    ai_detail_level=parsed_args.ai_detail
                )

                # Handle output
                if parsed_args.output and parsed_args.format in ['json', 'csv']:
                    self._write_results([result], parsed_args.output, parsed_args.format)
                    console.print(f"[green]Result written to {parsed_args.output}[/green]")
                else:
                    self._print_result_table([result], show_ai_details=parsed_args.show_ai_details)
            else:
                parser.print_help()
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            if parsed_args.log_level.upper() == "DEBUG":
                import traceback
                traceback.print_exc()
            sys.exit(1)

    def _create_argument_parser(self) -> argparse.ArgumentParser:
        """
        Create the argument parser for the CLI.

        Returns:
            Configured argument parser
        """
        parser = argparse.ArgumentParser(
            description="Reddit Persona Validator - CLI",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )

        # Input options
        input_group = parser.add_argument_group("Input Options")
        input_options = input_group.add_mutually_exclusive_group(required=False)
        input_options.add_argument("--username", "-u", help="Single Reddit username to validate")
        input_options.add_argument("--input", "-i", help="Input file path (CSV or TXT)")

        # Output options
        output_group = parser.add_argument_group("Output Options")
        output_group.add_argument("--output", "-o", help="Output file path")
        output_group.add_argument(
            "--format", "-f",
            choices=["json", "csv", "yaml", "table"],
            default="table",
            help="Output format"
        )

        # Validation options
        validation_group = parser.add_argument_group("Validation Options")
        validation_group.add_argument(
            "--email", "-e",
            help="Email address to verify (for single account validation)"
        )
        validation_group.add_argument(
            "--verify-email",
            action="store_true",
            help="Perform email verification"
        )
        validation_group.add_argument(
            "--no-ai-analysis",
            dest="ai_analysis",
            action="store_false",
            help="Skip AI analysis"
        )
        validation_group.add_argument(
            "--config", "-c",
            default="config/config.yaml",
            help="Path to configuration file"
        )
        validation_group.add_argument(
            "--workers", "-w",
            type=int,
            default=1,
            help="Number of concurrent validation workers (batch mode only)"
        )

        # AI Analysis options
        ai_group = parser.add_argument_group("AI Analysis Options")
        ai_group.add_argument(
            "--ai-analyzer",
            choices=["deepseek", "claude", "mock"],
            help="AI analyzer to use (overrides config)"
        )
        ai_group.add_argument(
            "--ai-detail",
            choices=["none", "basic", "medium", "full"],
            default="medium",
            help="Level of AI analysis detail"
        )
        ai_group.add_argument(
            "--show-ai-details",
            action="store_true",
            help="Show detailed AI analysis results in terminal output"
        )

        # Logging options
        logging_group = parser.add_argument_group("Logging Options")
        logging_group.add_argument(
            "--log-level",
            choices=["debug", "info", "warning", "error", "critical"],
            default="info",
            help="Logging level"
        )

        parser.set_defaults(ai_analysis=True)

        return parser

    def _print_banner(self) -> None:
        """Print a welcome banner in the terminal."""
        banner_text = """
 ___         _    _ _ _    ___
| _ \\___ __| |__| (_) |_  | _ \\___ _ _ ___ ___ _ _  __ _
|   / -_) _` / _` | |  _| |  _/ -_) '_(_-</ _ \\ ' \\/ _` |
|_|_\\___\\__,_\\__,_|_|\\__| |_| \\___|_| /__/\\___/_||_\\__,_|
                          __   __    _ _    _       _
                          \\ \\ / /_ _| (_)__| |__ _ | |_ ___ _ _
                           \\ V / _` | | / _` / _` ||  _/ _ \\ '_|
                            \\_/\\__,_|_|_\\__,_\\__,_| \\__\\___/_|
        """
        console.print(Panel.fit(banner_text, border_style="green"))


def main():
    """Main entry point for the CLI."""
    cli = PersonaValidatorCLI()
    cli.run()


if __name__ == "__main__":
    main()
