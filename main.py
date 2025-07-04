#!/usr/bin/env python3
"""
Main entry point for Reddit Persona Validator.

This script provides a command-line entry point for the validator,
allowing users to run it in CLI, API, GUI mode, or visualization dashboard.

Examples:
    # Run in CLI mode (default)
    python -m main --cli

    # Run in API mode
    python -m main --api

    # Run in GUI mode
    python -m main --gui

    # Run the visualization dashboard
    python -m main --dashboard
"""

import sys
import argparse
import logging
from typing import Optional, List
import os

# Import interfaces
from src.interfaces.cli import PersonaValidatorCLI
from src.interfaces.api import run_app as run_api
from src.interfaces.gui import RedditPersonaValidatorGUI
from src.visualization.dashboard import run_dashboard

logger = logging.getLogger(__name__)


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Reddit Persona Validator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--cli", action="store_true", help="Run in CLI mode")
    mode_group.add_argument("--api", action="store_true", help="Run in API mode")
    mode_group.add_argument("--gui", action="store_true", help="Run in GUI mode")
    mode_group.add_argument("--dashboard", action="store_true", help="Run the visualization dashboard")

    parser.add_argument(
        "--config", "-c",
        default="config/config.yaml",
        help="Path to configuration file"
    )

    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Logging level"
    )

    parsed_args = parser.parse_args(args)

    # Default to CLI mode if no mode specified
    if not (parsed_args.cli or parsed_args.api or parsed_args.gui or parsed_args.dashboard):
        parsed_args.cli = True

    return parsed_args


def setup_logging(level: str) -> None:
    """
    Set up logging configuration.

    Args:
        level: Logging level (debug, info, warning, error, critical)
    """
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.setLevel(getattr(logging, level.upper()))
    logger.addHandler(handler)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Set up logging
    setup_logging(args.log_level)

    if not os.path.isfile(args.config):
        logger.error(f"Config file not found: {args.config}")
        sys.exit(1)

    # Run in appropriate mode
    if args.cli:
        try:
            cli = PersonaValidatorCLI(config_path=args.config)
            cli.run()
        except Exception as e:
            logger.exception("CLI mode failed")
    elif args.api:
        try:
            run_api()
        except Exception as e:
            logger.exception("API mode failed")
    elif args.gui:
        try:
            gui = RedditPersonaValidatorGUI()
            gui.run()
        except Exception as e:
            logger.exception("GUI mode failed")
    elif args.dashboard:
        try:
            run_dashboard()
        except Exception as e:
            logger.exception("Dashboard mode failed")


if __name__ == "__main__":
    main()
