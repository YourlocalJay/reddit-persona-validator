"""Dashboard module for Reddit Persona Validator.

This module provides visualization dashboards for the Reddit Persona Validator,
including:
- Validation result analytics
- Performance monitoring
- User behavior insights
- Trust score distributions

The dashboards are built using Dash and Plotly for interactive visualizations.

Example usage:
    # Run the dashboard server
    python -m src.visualization.dashboard
"""

import os
import logging
from typing import Dict, List, Any, Optional, Union, Tuple, cast
from datetime import datetime, timedelta
from pathlib import Path

import dash
from dash import dcc, html, callback, Input, Output, State
import dash_bootstrap_components as dbc
import dash_daq as daq
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np

from ..utils.config_loader import ConfigLoader
from ..utils.database import Database, ValidationRecord, PerformanceMetric

# Setup logging
logger = logging.getLogger("persona-validator-dashboard")


class DashboardApp:
    """Dashboard application for Reddit Persona Validator."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        Initialize the dashboard application.
        
        Args:
            config_path: Path to configuration file
        """
        self.config = ConfigLoader.load_config(config_path)
        self.dashboard_config = self.config.get("visualization", {}).get("dashboard", {})
        
        # Initialize the database
        self.db = Database.from_config(config_path)
        
        # Create Dash app
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.DARKLY],
            title="Reddit Persona Validator Dashboard",
            meta_tags=[
                {"name": "viewport", "content": "width=device-width, initial-scale=1"}
            ],
        )
        
        # Set up the layout
        self.app.layout = self._create_layout()
        
        # Set up callbacks
        self._setup_callbacks()
    
    def _create_layout(self) -> dash.html.Div:
        """
        Create the dashboard layout.
        
        Returns:
            Dash layout
        """
        return html.Div([
            # Header
            html.Div([
                html.H1("Reddit Persona Validator Dashboard"),
                html.Div([
                    html.Span("Last updated: "),
                    html.Span(id="last-update-time"),
                    dbc.Button(
                        html.I(className="fas fa-sync-alt"),
                        id="refresh-button",
                        color="primary",
                        className="ms-2",
                        n_clicks=0,
                    ),
                ], className="d-flex align-items-center"),
            ], className="d-flex justify-content-between align-items-center p-3 bg-dark text-white"),
            
            # Date range selector
            dbc.Card([
                dbc.CardBody([
                    html.H5("Date Range", className="card-title"),
                    dcc.DatePickerRange(
                        id="date-range",
                        start_date=(datetime.now() - timedelta(days=30)).date(),
                        end_date=datetime.now().date(),
                        display_format="YYYY-MM-DD",
                        className="mb-3",
                    ),
                    dbc.Button(
                        "Apply",
                        id="apply-date-range",
                        color="primary",
                        n_clicks=0,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Last 7 Days",
                        id="last-7-days",
                        color="secondary",
                        n_clicks=0,
                        className="me-2",
                    ),
                    dbc.Button(
                        "Last 30 Days",
                        id="last-30-days",
                        color="secondary",
                        n_clicks=0,
                        className="me-2",
                    ),
                    dbc.Button(
                        "All Time",
                        id="all-time",
                        color="secondary",
                        n_clicks=0,
                    ),
                ]),
            ], className="m-3"),
            
            # Main content with tabs
            dbc.Card([
                dbc.CardBody([
                    dbc.Tabs([
                        dbc.Tab(
                            self._create_overview_tab(),
                            label="Overview",
                            tab_id="tab-overview",
                        ),
                        dbc.Tab(
                            self._create_validation_tab(),
                            label="Validation Results",
                            tab_id="tab-validation",
                        ),
                        dbc.Tab(
                            self._create_performance_tab(),
                            label="Performance Metrics",
                            tab_id="tab-performance",
                        ),
                        dbc.Tab(
                            self._create_ai_analysis_tab(),
                            label="AI Analysis",
                            tab_id="tab-ai-analysis",
                        ),
                    ], id="tabs", active_tab="tab-overview"),
                ]),
            ], className="m-3"),
            
            # Store for data
            dcc.Store(id="overview-data"),
            dcc.Store(id="validation-data"),
            dcc.Store(id="performance-data"),
            dcc.Store(id="ai-analysis-data"),
            
            # Interval for auto-refresh
            dcc.Interval(
                id="auto-refresh",
                interval=60 * 1000,  # 1 minute in milliseconds
                n_intervals=0,
            ),
            
            # Hidden div for storing current state
            html.Div(id="current-state", style={"display": "none"}),
            
            # Footer
            html.Footer([
                html.P([
                    "Reddit Persona Validator Dashboard ",
                    html.Small("v1.0.0"),
                ], className="mb-0"),
            ], className="p-3 bg-dark text-white text-center mt-3"),
        ])
    
    def _create_overview_tab(self) -> dash.html.Div:
        """
        Create the overview tab.
        
        Returns:
            Dash layout for overview tab
        """
        return html.Div([
            # Summary cards row
            dbc.Row([
                # Total validations card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Total Validations", className="card-title"),
                            html.H2(id="total-validations", className="card-text text-center"),
                        ]),
                    ]),
                ], width=3),
                
                # Existing accounts card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Existing Accounts", className="card-title"),
                            html.Div([
                                html.H2(id="existing-accounts", className="card-text text-center"),
                                html.Div(id="existing-accounts-percent", className="text-center text-muted"),
                            ]),
                        ]),
                    ]),
                ], width=3),
                
                # Verified emails card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Verified Emails", className="card-title"),
                            html.Div([
                                html.H2(id="verified-emails", className="card-text text-center"),
                                html.Div(id="verified-emails-percent", className="text-center text-muted"),
                            ]),
                        ]),
                    ]),
                ], width=3),
                
                # Average trust score card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Avg Trust Score", className="card-title"),
                            html.Div([
                                html.H2(id="avg-trust-score", className="card-text text-center"),
                                daq.GraduatedBar(
                                    id="trust-score-bar",
                                    color={"ranges": {
                                        "red": [0, 40],
                                        "yellow": [40, 70],
                                        "green": [70, 100]
                                    }},
                                    showCurrentValue=False,
                                    max=100,
                                    value=0,
                                ),
                            ]),
                        ]),
                    ]),
                ], width=3),
            ], className="mb-4"),
            
            # Charts row
            dbc.Row([
                # Trust score distribution
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Trust Score Distribution", className="card-title"),
                            dcc.Graph(id="trust-score-distribution"),
                        ]),
                    ]),
                ], width=6),
                
                # Validations over time
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Validations Over Time", className="card-title"),
                            dcc.Graph(id="validations-over-time"),
                        ]),
                    ]),
                ], width=6),
            ], className="mb-4"),
            
            # Recent validations
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Recent Validations", className="card-title"),
                            html.Div(id="recent-validations-table"),
                        ]),
                    ]),
                ]),
            ]),
        ])
    
    def _create_validation_tab(self) -> dash.html.Div:
        """
        Create the validation results tab.
        
        Returns:
            Dash layout for validation results tab
        """
        return html.Div([
            # Filters row
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Filters", className="card-title"),
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Trust Score Range"),
                                    dcc.RangeSlider(
                                        id="trust-score-range",
                                        min=0,
                                        max=100,
                                        step=5,
                                        marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                                        value=[0, 100],
                                    ),
                                ], width=6),
                                dbc.Col([
                                    html.Label("Account Status"),
                                    dbc.Checklist(
                                        id="account-status",
                                        options=[
                                            {"label": "Existing", "value": "existing"},
                                            {"label": "Non-existing", "value": "non-existing"},
                                        ],
                                        value=["existing", "non-existing"],
                                        inline=True,
                                    ),
                                ], width=3),
                                dbc.Col([
                                    html.Label("Email Verification"),
                                    dbc.Checklist(
                                        id="email-verification",
                                        options=[
                                            {"label": "Verified", "value": "verified"},
                                            {"label": "Not Verified", "value": "not-verified"},
                                            {"label": "Not Attempted", "value": "not-attempted"},
                                        ],
                                        value=["verified", "not-verified", "not-attempted"],
                                        inline=True,
                                    ),
                                ], width=3),
                            ]),
                        ]),
                    ]),
                ]),
            ], className="mb-4"),
            
            # Validation scatter plot
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Trust Score vs. Account Age", className="card-title"),
                            dcc.Graph(id="trust-score-vs-age"),
                        ]),
                    ]),
                ], width=6),
                
                # Validation metrics
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Validation Metrics", className="card-title"),
                            dcc.Graph(id="validation-metrics"),
                        ]),
                    ]),
                ], width=6),
            ], className="mb-4"),
            
            # Validation results table
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Validation Results", className="card-title"),
                            html.Div(id="validation-results-table"),
                        ]),
                    ]),
                ]),
            ]),
        ])
    
    def _create_performance_tab(self) -> dash.html.Div:
        """
        Create the performance metrics tab.
        
        Returns:
            Dash layout for performance metrics tab
        """
        return html.Div([
            # Filters row
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Filters", className="card-title"),
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Metric Type"),
                                    dbc.Select(
                                        id="metric-type",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {"label": "Validation", "value": "validation"},
                                            {"label": "API Request", "value": "api_request"},
                                            {"label": "Analysis", "value": "analysis"},
                                        ],
                                        value="all",
                                    ),
                                ], width=4),
                                dbc.Col([
                                    html.Label("Operation"),
                                    dbc.Select(
                                        id="operation",
                                        options=[
                                            {"label": "All", "value": "all"},
                                        ],
                                        value="all",
                                    ),
                                ], width=4),
                                dbc.Col([
                                    html.Label("Success"),
                                    dbc.Select(
                                        id="success",
                                        options=[
                                            {"label": "All", "value": "all"},
                                            {"label": "Success", "value": "success"},
                                            {"label": "Error", "value": "error"},
                                        ],
                                        value="all",
                                    ),
                                ], width=4),
                            ]),
                        ]),
                    ]),
                ]),
            ], className="mb-4"),
            
            # Performance overview
            dbc.Row([
                # Average duration card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Avg. Duration (ms)", className="card-title"),
                            html.H2(id="avg-duration", className="card-text text-center"),
                        ]),
                    ]),
                ], width=3),
                
                # Success rate card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Success Rate", className="card-title"),
                            html.Div([
                                html.H2(id="success-rate", className="card-text text-center"),
                                daq.GraduatedBar(
                                    id="success-rate-bar",
                                    color={"ranges": {
                                        "red": [0, 70],
                                        "yellow": [70, 90],
                                        "green": [90, 100]
                                    }},
                                    showCurrentValue=False,
                                    max=100,
                                    value=0,
                                ),
                            ]),
                        ]),
                    ]),
                ], width=3),
                
                # Max duration card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Max Duration (ms)", className="card-title"),
                            html.H2(id="max-duration", className="card-text text-center"),
                        ]),
                    ]),
                ], width=3),
                
                # Total operations card
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Total Operations", className="card-title"),
                            html.H2(id="total-operations", className="card-text text-center"),
                        ]),
                    ]),
                ], width=3),
            ], className="mb-4"),
            
            # Performance charts
            dbc.Row([
                # Duration over time
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Duration Over Time", className="card-title"),
                            dcc.Graph(id="duration-over-time"),
                        ]),
                    ]),
                ], width=6),
                
                # Duration by operation
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Duration by Operation", className="card-title"),
                            dcc.Graph(id="duration-by-operation"),
                        ]),
                    ]),
                ], width=6),
            ], className="mb-4"),
            
            # Performance metrics table
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Performance Metrics", className="card-title"),
                            html.Div(id="performance-metrics-table"),
                        ]),
                    ]),
                ]),
            ]),
        ])
    
    def _create_ai_analysis_tab(self) -> dash.html.Div:
        """
        Create the AI analysis tab.
        
        Returns:
            Dash layout for AI analysis tab
        """
        return html.Div([
            # AI model comparison
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("AI Model Comparison", className="card-title"),
                            dcc.Graph(id="ai-model-comparison"),
                        ]),
                    ]),
                ]),
            ], className="mb-4"),
            
            # AI analysis charts
            dbc.Row([
                # Sentiment distribution
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Sentiment Distribution", className="card-title"),
                            dcc.Graph(id="sentiment-distribution"),
                        ]),
                    ]),
                ], width=6),
                
                # Content categories
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("Content Categories", className="card-title"),
                            dcc.Graph(id="content-categories"),
                        ]),
                    ]),
                ], width=6),
            ], className="mb-4"),
            
            # AI analysis detail
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H5("AI Analysis Detail", className="card-title"),
                            dbc.Tabs([
                                dbc.Tab(
                                    html.Div(id="claude-analysis"),
                                    label="Claude Analysis",
                                    tab_id="tab-claude",
                                ),
                                dbc.Tab(
                                    html.Div(id="deepseek-analysis"),
                                    label="DeepSeek Analysis",
                                    tab_id="tab-deepseek",
                                ),
                            ], id="ai-tabs", active_tab="tab-claude"),
                        ]),
                    ]),
                ]),
            ]),
        ])
    
    def _setup_callbacks(self) -> None:
        """Set up Dash callbacks."""
        # Update last update time
        @self.app.callback(
            Output("last-update-time", "children"),
            Input("auto-refresh", "n_intervals"),
            Input("refresh-button", "n_clicks"),
        )
        def update_last_update_time(*_) -> str:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Update date range buttons
        @self.app.callback(
            Output("date-range", "start_date"),
            Output("date-range", "end_date"),
            Input("last-7-days", "n_clicks"),
            Input("last-30-days", "n_clicks"),
            Input("all-time", "n_clicks"),
            State("date-range", "start_date"),
            State("date-range", "end_date"),
            prevent_initial_call=True,
        )
        def update_date_range(n_clicks_7, n_clicks_30, n_clicks_all, start_date, end_date):
            ctx = dash.callback_context
            if not ctx.triggered:
                return start_date, end_date
            
            button_id = ctx.triggered[0]["prop_id"].split(".")[0]
            end_date = datetime.now().date()
            
            if button_id == "last-7-days":
                start_date = (datetime.now() - timedelta(days=7)).date()
            elif button_id == "last-30-days":
                start_date = (datetime.now() - timedelta(days=30)).date()
            elif button_id == "all-time":
                start_date = datetime(2000, 1, 1).date()  # Early date to get all data
            
            return start_date, end_date
        
        # Load overview data
        @self.app.callback(
            Output("overview-data", "data"),
            Input("apply-date-range", "n_clicks"),
            Input("auto-refresh", "n_intervals"),
            Input("refresh-button", "n_clicks"),
            State("date-range", "start_date"),
            State("date-range", "end_date"),
        )
        async def load_overview_data(_, __, ___, start_date, end_date):
            # Convert string dates to datetime
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) if end_date else None
            
            # Initialize the database if not already initialized
            if not self.db._initialized:
                await self.db.initialize()
            
            # Get statistics
            stats = await self.db.get_validation_statistics(start_datetime, end_datetime)
            
            # Get recent validations
            recent_validations = await self.db.get_recent_validations(limit=10)
            
            # Convert to serializable format
            recent_validations_data = []
            for val in recent_validations:
                recent_validations_data.append({
                    "id": val.id,
                    "username": val.username,
                    "exists": val.exists,
                    "trust_score": val.trust_score,
                    "email_verified": val.email_verified,
                    "created_at": val.created_at.isoformat(),
                })
            
            # Return the data
            return {
                "statistics": stats,
                "recent_validations": recent_validations_data,
            }
        
        # Update overview tab content
        @self.app.callback(
            Output("total-validations", "children"),
            Output("existing-accounts", "children"),
            Output("existing-accounts-percent", "children"),
            Output("verified-emails", "children"),
            Output("verified-emails-percent", "children"),
            Output("avg-trust-score", "children"),
            Output("trust-score-bar", "value"),
            Output("trust-score-distribution", "figure"),
            Output("validations-over-time", "figure"),
            Output("recent-validations-table", "children"),
            Input("overview-data", "data"),
        )
        def update_overview_tab(data):
            if not data:
                return "0", "0", "0%", "0", "0%", "0", 0, {}, {}, html.P("No data available")
            
            stats = data["statistics"]
            recent_validations = data["recent_validations"]
            
            # Calculate percentages
            total_validations = stats["total_validations"] or 0
            existing_accounts = stats["existing_accounts"] or 0
            verified_emails = stats["verified_emails"] or 0
            
            existing_percent = f"{(existing_accounts / total_validations * 100) if total_validations else 0:.1f}%"
            verified_percent = f"{(verified_emails / existing_accounts * 100) if existing_accounts else 0:.1f}%"
            
            # Create trust score distribution chart
            trust_dist = stats.get("trust_score_distribution", {})
            trust_dist_fig = px.bar(
                x=list(trust_dist.keys()),
                y=list(trust_dist.values()),
                labels={"x": "Trust Score Range", "y": "Count"},
                color_discrete_sequence=["#1f77b4"],
            )
            trust_dist_fig.update_layout(
                margin=dict(l=40, r=40, t=10, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            )
            
            # Create validations over time placeholder
            # In a real implementation, this would use time series data from the database
            validations_time_fig = go.Figure()
            validations_time_fig.add_trace(go.Scatter(
                x=[datetime.now() - timedelta(days=i) for i in range(30, 0, -1)],
                y=[int(np.random.poisson(5)) for _ in range(30)],  # Random data for example
                mode="lines+markers",
                name="Validations",
                line=dict(color="#1f77b4", width=2),
                marker=dict(size=6),
            ))
            validations_time_fig.update_layout(
                margin=dict(l=40, r=40, t=10, b=40),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="white"),
                xaxis=dict(showgrid=False, title="Date"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)", title="Count"),
            )
            
            # Create recent validations table
            recent_table = dbc.Table([
                html.Thead([
                    html.Tr([
                        html.Th("Username"),
                        html.Th("Exists"),
                        html.Th("Trust Score"),
                        html.Th("Email Verified"),
                        html.Th("Date"),
                    ])
                ]),
                html.Tbody([
                    html.Tr([
                        html.Td(val["username"]),
                        html.Td("✓" if val["exists"] else "✗"),
                        html.Td(f"{val['trust_score']:.1f}" if val["trust_score"] is not None else "N/A"),
                        html.Td(
                            "✓" if val["email_verified"] else 
                            "✗" if val["email_verified"] is not None else "N/A"
                        ),
                        html.Td(datetime.fromisoformat(val["created_at"]).strftime("%Y-%m-%d %H:%M")),
                    ]) for val in recent_validations
                ]),
            ], bordered=True, hover=True, striped=True, className="table-sm")
            
            # Return all the outputs
            return (
                str(total_validations),
                str(existing_accounts),
                existing_percent,
                str(verified_emails),
                verified_percent,
                f"{stats['avg_trust_score']:.1f}" if stats['avg_trust_score'] else "0.0",
                stats['avg_trust_score'] if stats['avg_trust_score'] else 0,
                trust_dist_fig,
                validations_time_fig,
                recent_table,
            )
        
        # Other callbacks would be implemented similarly
        # For validation, performance, and AI analysis tabs
    
    def run_server(self, host: str = "0.0.0.0", port: int = 8050, debug: bool = False) -> None:
        """
        Run the dashboard server.
        
        Args:
            host: Host address
            port: Port number
            debug: Whether to run in debug mode
        """
        dashboard_config = self.config.get("visualization", {}).get("dashboard", {})
        host = dashboard_config.get("host", host)
        port = dashboard_config.get("port", port)
        debug = dashboard_config.get("debug", debug)
        
        self.app.run_server(host=host, port=port, debug=debug)


async def initialize_database(config_path: str = "config/config.yaml") -> None:
    """
    Initialize the database.
    
    Args:
        config_path: Path to configuration file
    """
    db = Database.from_config(config_path)
    await db.initialize()
    logger.info("Database initialized")
    await db.close()


def run_dashboard() -> None:
    """Run the dashboard application."""
    import asyncio
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Initialize the database
    asyncio.run(initialize_database())
    
    # Create and run the dashboard
    dashboard = DashboardApp()
    dashboard.run_server()


if __name__ == "__main__":
    run_dashboard()
