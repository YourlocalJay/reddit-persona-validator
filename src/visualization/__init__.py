"""Visualization package for Reddit Persona Validator.

This package provides visualization tools and dashboards for the Reddit Persona Validator,
including:
- Interactive dashboards for validation analytics
- Performance monitoring visualizations
- Trust score and AI analysis visualizations
- Data export utilities

Example usage:
    # Run the dashboard server
    python -m src.visualization.dashboard
"""

from .dashboard import DashboardApp, run_dashboard
