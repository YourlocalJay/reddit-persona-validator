"""PySimpleGUI-based interface for Reddit persona validation.

This module provides a user-friendly GUI interface for the Reddit Persona Validator with:
- Single account validation
- Batch processing from input files
- Visual representation of validation results
- Settings management
- Export options for results

Example usage:
    # Run the GUI application
    python -m src.interfaces.gui
"""

import os
import sys
import json
import csv
import time
import logging
import threading
import webbrowser
import queue
from pathlib import Path
from typing import Dict, Optional, List, Any, Union, Tuple, Generator
from datetime import datetime

import PySimpleGUI as sg
from rich.console import Console, ConsoleRenderable
from rich.panel import Panel
from rich.text import Text

# Import the validator
from ..core.validator import RedditPersonaValidator, ValidationResult
from ..utils.config_loader import ConfigLoader

# Set up logging
logger = logging.getLogger("persona-validator-gui")

# Rich console for string rendering
console = Console(record=True)

# Define theme settings
DEFAULT_THEME = "DarkGrey9"
AVAILABLE_THEMES = sg.theme_list()

# Define color constants
COLOR_SUCCESS = "#00B050"  # Green
COLOR_WARNING = "#FFC000"  # Yellow
COLOR_ERROR = "#FF0000"    # Red
COLOR_INFO = "#0070C0"     # Blue


class CustomConsoleHandler(logging.Handler):
    """Custom logging handler that redirects logs to PySimpleGUI multiline element."""
    
    def __init__(self, window, key):
        """
        Initialize the handler.
        
        Args:
            window: PySimpleGUI window
            key: Key of the multiline element
        """
        super().__init__()
        self.window = window
        self.key = key
    
    def emit(self, record):
        """
        Emit a log record.
        
        Args:
            record: Log record
        """
        try:
            msg = self.format(record)
            self.window.write_event_value("-LOG-", msg)
        except Exception:
            self.handleError(record)


class GuiLogger:
    """Logger for the GUI interface."""
    
    def __init__(self, window):
        """
        Initialize the logger.
        
        Args:
            window: PySimpleGUI window
        """
        self.window = window
        self.handler = CustomConsoleHandler(window, "-LOG-")
        self.handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        
        # Add handler to root logger
        logging.getLogger().addHandler(self.handler)
        logging.getLogger().setLevel(logging.INFO)
    
    def cleanup(self):
        """Remove the handler from the root logger."""
        logging.getLogger().removeHandler(self.handler)


class RedditPersonaValidatorGUI:
    """GUI interface for the Reddit Persona Validator."""
    
    def __init__(self):
        """Initialize the GUI interface."""
        self.window = None
        self.validator = None
        self.logger = None
        self.running = False
        self.settings = self.load_settings()
        self.validation_results = []
        self.batch_queue = queue.Queue()
        self.batch_thread = None
        
        # Apply theme from settings
        sg.theme(self.settings.get("theme", DEFAULT_THEME))
    
    def load_settings(self) -> Dict[str, Any]:
        """
        Load settings from file.
        
        Returns:
            Dictionary with settings
        """
        settings_file = Path("config/gui_settings.json")
        
        if settings_file.exists():
            try:
                with open(settings_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load settings: {str(e)}")
        
        # Default settings
        return {
            "theme": DEFAULT_THEME,
            "input_file": "",
            "output_folder": "results",
            "use_ai": True,
            "verify_email": False,
            "save_cookies": True,
            "max_workers": 1,
            "window_size": (800, 600)
        }
    
    def save_settings(self):
        """Save settings to file."""
        settings_file = Path("config/gui_settings.json")
        
        # Ensure directory exists
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Update settings from window values
        if self.window:
            values = self.window.read(timeout=0)[1]
            self.settings.update({
                "input_file": values.get("-INFILE-", ""),
                "output_folder": values.get("-OUTFOLDER-", "results"),
                "use_ai": values.get("-USE_AI-", True),
                "verify_email": values.get("-VERIFY_EMAIL-", False),
                "save_cookies": values.get("-SAVE_COOKIES-", True),
                "max_workers": values.get("-MAX_WORKERS-", 1),
                "window_size": self.window.size
            })
        
        try:
            with open(settings_file, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save settings: {str(e)}")
    
    def _init_validator(self) -> RedditPersonaValidator:
        """
        Initialize the validator if not already initialized.
        
        Returns:
            Initialized RedditPersonaValidator instance
        """
        if not self.validator:
            try:
                self.validator = RedditPersonaValidator(config_path="config/config.yaml")
            except Exception as e:
                sg.popup_error(f"Error initializing validator: {str(e)}")
                raise
        return self.validator
    
    def create_main_layout(self) -> List[List[Any]]:
        """
        Create the main window layout.
        
        Returns:
            List of layout rows
        """
        # Validator settings frame
        settings_frame = [
            [sg.Text("Reddit Persona Validator", font=("Helvetica", 16), justification="center", expand_x=True)],
            [sg.HorizontalSeparator()],
            [sg.Text("Input Options")],
            [
                sg.Radio("Single Account", "INPUT_MODE", key="-SINGLE_MODE-", default=True, enable_events=True),
                sg.Radio("Batch Process", "INPUT_MODE", key="-BATCH_MODE-", default=False, enable_events=True)
            ],
            # Single account input (initially visible)
            [
                sg.pin(sg.Column([
                    [sg.Text("Username:", size=(12, 1)), sg.Input(key="-USERNAME-", size=(30, 1))],
                    [sg.Text("Email (optional):", size=(12, 1)), sg.Input(key="-EMAIL-", size=(30, 1))]
                ], key="-SINGLE_INPUT-", visible=True))
            ],
            # Batch input (initially hidden)
            [
                sg.pin(sg.Column([
                    [sg.Text("Input File:", size=(12, 1)), 
                     sg.Input(key="-INFILE-", default_text=self.settings.get("input_file", ""), size=(30, 1)), 
                     sg.FileBrowse()],
                    [sg.Text("Max Workers:", size=(12, 1)), 
                     sg.Spin([i for i in range(1, 11)], initial_value=self.settings.get("max_workers", 1), key="-MAX_WORKERS-", size=(5, 1))]
                ], key="-BATCH_INPUT-", visible=False))
            ],
            [sg.HorizontalSeparator()],
            [sg.Text("Validation Options")],
            [
                sg.Checkbox("Use AI Analysis", key="-USE_AI-", default=self.settings.get("use_ai", True)),
                sg.Checkbox("Verify Email", key="-VERIFY_EMAIL-", default=self.settings.get("verify_email", False))
            ],
            [
                sg.Checkbox("Save Cookies", key="-SAVE_COOKIES-", default=self.settings.get("save_cookies", True))
            ],
            [sg.HorizontalSeparator()],
            [sg.Text("Output Options")],
            [
                sg.Text("Output Folder:", size=(12, 1)),
                sg.Input(key="-OUTFOLDER-", default_text=self.settings.get("output_folder", "results"), size=(30, 1)),
                sg.FolderBrowse()
            ],
            [
                sg.Text("Output Format:", size=(12, 1)),
                sg.Combo(["JSON", "CSV", "Both"], key="-OUT_FORMAT-", default_value="Both", size=(10, 1))
            ]
        ]
        
        # Main control buttons
        control_layout = [
            [
                sg.Button("Run Validation", key="-RUN-", size=(15, 1), button_color=("white", "#00B050")),
                sg.Button("Stop", key="-STOP-", size=(10, 1), disabled=True, button_color=("white", "#FF0000")),
                sg.Button("Clear", key="-CLEAR-", size=(10, 1)),
                sg.Button("Settings", key="-SETTINGS-", size=(10, 1))
            ]
        ]
        
        # Progress bar
        progress_layout = [
            [sg.Text("Progress:", size=(8, 1)), sg.ProgressBar(100, orientation="h", size=(30, 20), key="-PROGRESS-")]
        ]
        
        # Results tabs
        results_tabs = sg.TabGroup([
            # Log tab
            [sg.Tab("Log", [
                [sg.Multiline(size=(80, 15), key="-LOG-OUTPUT-", autoscroll=True, reroute_stdout=False, 
                              reroute_stderr=False, disabled=True, background_color="#1E1E1E", text_color="white")]
            ], key="-LOG_TAB-")],
            
            # Results table tab
            [sg.Tab("Results", [
                [sg.Table(
                    values=[],
                    headings=["Username", "Exists", "Trust Score", "Age (days)", "Karma", "Status"],
                    auto_size_columns=False,
                    col_widths=[15, 8, 12, 10, 10, 30],
                    justification="left",
                    num_rows=10,
                    key="-RESULTS_TABLE-",
                    enable_events=True,
                    tooltip="Click on a row to see details"
                )],
                [
                    sg.Button("Export Results", key="-EXPORT-", size=(15, 1), disabled=True),
                    sg.Button("Open Output Folder", key="-OPEN_OUTPUT-", size=(15, 1))
                ]
            ], key="-RESULTS_TAB-")]
        ], key="-TABS-", enable_events=True, size=(800, 300))
        
        # Combine all layouts
        layout = [
            [sg.Column([
                [sg.Frame("Configuration", settings_frame, font=("Helvetica", 12))]
            ]), sg.VerticalSeparator(), sg.Column([
                [sg.Frame("Status", progress_layout, font=("Helvetica", 12))],
                [sg.Frame("Controls", control_layout, font=("Helvetica", 12))]
            ])],
            [sg.HorizontalSeparator()],
            [results_tabs]
        ]
        
        return layout
    
    def create_settings_window(self) -> sg.Window:
        """
        Create the settings window.
        
        Returns:
            PySimpleGUI window
        """
        layout = [
            [sg.Text("Settings", font=("Helvetica", 16), justification="center", expand_x=True)],
            [sg.HorizontalSeparator()],
            [sg.Text("Theme:", size=(12, 1)), 
             sg.Combo(AVAILABLE_THEMES, default_value=self.settings.get("theme", DEFAULT_THEME), 
                      key="-THEME-", size=(20, 1), enable_events=True)],
            [sg.HorizontalSeparator()],
            [
                sg.Button("Save", key="-SAVE_SETTINGS-", size=(10, 1)),
                sg.Button("Cancel", key="-CANCEL_SETTINGS-", size=(10, 1))
            ]
        ]
        
        return sg.Window("Settings", layout, modal=True, finalize=True)
    
    def create_result_details_window(self, result: ValidationResult) -> sg.Window:
        """
        Create a window to display detailed validation results.
        
        Args:
            result: ValidationResult to display
            
        Returns:
            PySimpleGUI window
        """
        # Header with username and trust score
        header_color = COLOR_SUCCESS
        if result.errors and len(result.errors) > 0:
            header_color = COLOR_ERROR
        elif result.warnings and len(result.warnings) > 0:
            header_color = COLOR_WARNING
        
        # Basic account info
        account_layout = [
            [sg.Text(f"Username: {result.username}", font=("Helvetica", 12))],
            [sg.Text(f"Account Exists: {'Yes' if result.exists else 'No'}", text_color=COLOR_SUCCESS if result.exists else COLOR_ERROR)],
            [sg.Text(f"Trust Score: {result.trust_score if result.trust_score is not None else 'N/A'}", font=("Helvetica", 12))],
        ]
        
        # Account details
        if result.account_details:
            account_layout.extend([
                [sg.HorizontalSeparator()],
                [sg.Text("Account Details:", font=("Helvetica", 12, "bold"))],
                [sg.Text(f"Account Age: {result.account_details.get('age_days', 'N/A')} days")],
                [sg.Text(f"Karma: {result.account_details.get('karma', 'N/A')}")],
                [sg.Text(f"Cake Day: {result.account_details.get('cake_day', 'N/A')}")],
                [sg.Text(f"Verified Email: {result.account_details.get('verified_email', 'N/A')}")],
            ])
        
        # Email verification results
        email_layout = [[sg.Text("Email Verification:", font=("Helvetica", 12, "bold"))]]
        if result.email_verified is not None:
            email_status = "Verified" if result.email_verified else "Not Verified"
            email_color = COLOR_SUCCESS if result.email_verified else COLOR_ERROR
            email_layout.append([sg.Text(f"Status: {email_status}", text_color=email_color)])
            
            if result.email_details:
                email_layout.extend([
                    [sg.Text(f"Email: {result.email_details.get('email', 'N/A')}")],
                    [sg.Text(f"Verification Time: {result.email_details.get('verification_time', 'N/A')}")],
                    [sg.Text(f"Verification ID: {result.email_details.get('verification_id', 'N/A')}")],
                ])
                
                if result.email_details.get('error'):
                    email_layout.append([sg.Text(f"Error: {result.email_details.get('error')}", text_color=COLOR_ERROR)])
        else:
            email_layout.append([sg.Text("Not performed")])
        
        # AI Analysis results
        ai_layout = [[sg.Text("AI Analysis:", font=("Helvetica", 12, "bold"))]]
        if result.ai_analysis:
            viability_score = result.ai_analysis.get('viability_score')
            ai_layout.extend([
                [sg.Text(f"Viability Score: {viability_score if viability_score is not None else 'N/A'}")],
            ])
            
            if result.ai_analysis.get('analysis_summary'):
                ai_layout.append([sg.Multiline(result.ai_analysis.get('analysis_summary', ''), 
                                             size=(50, 5), disabled=True)])
        else:
            ai_layout.append([sg.Text("Not performed")])
        
        # Warnings and errors
        status_layout = []
        if result.warnings and len(result.warnings) > 0:
            status_layout.extend([
                [sg.Text("Warnings:", font=("Helvetica", 12, "bold"), text_color=COLOR_WARNING)],
                [sg.Listbox(result.warnings, size=(50, len(result.warnings)), no_scrollbar=True, disabled=True, 
                          text_color=COLOR_WARNING, background_color="#FFFFE0")]
            ])
        
        if result.errors and len(result.errors) > 0:
            status_layout.extend([
                [sg.Text("Errors:", font=("Helvetica", 12, "bold"), text_color=COLOR_ERROR)],
                [sg.Listbox(result.errors, size=(50, len(result.errors)), no_scrollbar=True, disabled=True, 
                          text_color=COLOR_ERROR, background_color="#FFE0E0")]
            ])
        
        # Combine all layouts
        layout = [
            [sg.Text(f"Validation Results for {result.username}", 
                   font=("Helvetica", 16, "bold"), text_color=header_color, justification="center", expand_x=True)],
            [sg.HorizontalSeparator()],
            
            [sg.Column(account_layout, expand_x=True, expand_y=True)],
            [sg.HorizontalSeparator()],
            
            [sg.TabGroup([
                [sg.Tab("Email Verification", email_layout)],
                [sg.Tab("AI Analysis", ai_layout)],
                [sg.Tab("Status", status_layout)]
            ], tab_location="lefttop", expand_x=True, expand_y=True)],
            
            [sg.HorizontalSeparator()],
            [sg.Button("Close", key="-CLOSE_DETAILS-", size=(10, 1))]
        ]
        
        return sg.Window("Validation Results", layout, modal=True, finalize=True)
    
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
    
    def _write_results(self, results: List[ValidationResult], output_dir: str, 
                     output_format: str) -> Dict[str, str]:
        """
        Write validation results to output files in the specified format.
        
        Args:
            results: List of ValidationResult objects
            output_dir: Output directory
            output_format: Output format (JSON, CSV, or Both)
            
        Returns:
            Dictionary with output file paths
        """
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_files = {}
        
        if output_format in ["JSON", "Both"]:
            json_path = output_dir_path / f"validation_results_{timestamp}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                results_dict = [r.to_dict() for r in results]
                json.dump(results_dict, f, indent=2)
            output_files["json"] = str(json_path)
        
        if output_format in ["CSV", "Both"]:
            csv_path = output_dir_path / f"validation_results_{timestamp}.csv"
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                # Flatten the structure for CSV
                fieldnames = [
                    'username', 'exists', 'trust_score', 'email_verified', 
                    'age_days', 'karma', 'cake_day', 'verified_email',
                    'warnings', 'errors'
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
                    
                    writer.writerow(row)
            output_files["csv"] = str(csv_path)
        
        return output_files
    
    def _validate_single_account(self, username: str, email: Optional[str] = None,
                               perform_email_verification: bool = False, 
                               perform_ai_analysis: bool = True) -> ValidationResult:
        """
        Validate a single Reddit account.
        
        Args:
            username: Reddit username to validate
            email: Optional email to verify
            perform_email_verification: Whether to perform email verification
            perform_ai_analysis: Whether to perform AI analysis
            
        Returns:
            ValidationResult object containing validation results
        """
        validator = self._init_validator()
        
        try:
            result = validator.validate(
                username=username,
                email_address=email,
                perform_email_verification=perform_email_verification,
                perform_ai_analysis=perform_ai_analysis
            )
            return result
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            return ValidationResult(
                username=username,
                exists=False,
                errors=[f"Validation error: {str(e)}"]
            )
    
    def _batch_worker(self, accounts: List[Dict[str, str]], values: Dict[str, Any]):
        """
        Worker thread for batch processing.
        
        Args:
            accounts: List of account dictionaries
            values: Window values containing validation options
        """
        try:
            validator = self._init_validator()
            total = len(accounts)
            
            # Initialize progress
            self.window.write_event_value("-PROGRESS_UPDATE-", (0, total))
            
            results = []
            for i, account in enumerate(accounts):
                if not self.running:
                    break
                
                username = account['username']
                email = account.get('email')
                
                # Update status
                self.window.write_event_value("-STATUS_UPDATE-", f"Validating {username} ({i+1}/{total})")
                
                try:
                    result = validator.validate(
                        username=username,
                        email_address=email,
                        perform_email_verification=values["-VERIFY_EMAIL-"],
                        perform_ai_analysis=values["-USE_AI-"]
                    )
                    results.append(result)
                    
                    # Update table
                    self.window.write_event_value("-RESULT-", result)
                    
                except Exception as e:
                    logger.error(f"Validation failed for {username}: {str(e)}")
                    results.append(ValidationResult(
                        username=username,
                        exists=False,
                        errors=[f"Validation error: {str(e)}"]
                    ))
                
                # Update progress
                self.window.write_event_value("-PROGRESS_UPDATE-", (i+1, total))
            
            # Export results if requested
            if values.get("-OUT_FORMAT-") != "None" and values.get("-OUTFOLDER-"):
                output_files = self._write_results(
                    results,
                    values["-OUTFOLDER-"],
                    values["-OUT_FORMAT-"]
                )
                self.window.write_event_value("-EXPORT_DONE-", output_files)
            
            # Done
            self.window.write_event_value("-BATCH_DONE-", len(results))
            
        except Exception as e:
            logger.error(f"Batch processing failed: {str(e)}")
            self.window.write_event_value("-ERROR-", str(e))
        finally:
            self.running = False
            self.window.write_event_value("-ENABLE_RUN-", None)
    
    def _update_results_table(self):
        """Update the results table with current validation results."""
        table_data = []
        
        for result in self.validation_results:
            # Determine status message
            status = ""
            if result.errors and len(result.errors) > 0:
                status = "; ".join(result.errors)
            elif result.warnings and len(result.warnings) > 0:
                status = "; ".join(result.warnings)
            elif result.exists:
                status = "Valid account"
            
            # Add row
            table_data.append([
                result.username,
                "Yes" if result.exists else "No",
                str(result.trust_score) if result.trust_score is not None else "N/A",
                str(result.account_details.get('age_days', 'N/A')) if result.account_details else "N/A",
                str(result.account_details.get('karma', 'N/A')) if result.account_details else "N/A",
                status
            ])
        
        # Update table
        self.window["-RESULTS_TABLE-"].update(values=table_data)
        
        # Enable export button if results are available
        self.window["-EXPORT-"].update(disabled=not table_data)
    
    def run(self):
        """Run the GUI application."""
        # Create the main window
        self.window = sg.Window(
            "Reddit Persona Validator",
            self.create_main_layout(),
            size=self.settings.get("window_size", (800, 600)),
            resizable=True,
            finalize=True
        )
        
        # Initialize logger
        self.logger = GuiLogger(self.window)
        
        # Main event loop
        while True:
            event, values = self.window.read()
            
            if event == sg.WIN_CLOSED:
                break
            
            # Input mode switching
            if event == "-SINGLE_MODE-":
                self.window["-SINGLE_INPUT-"].update(visible=True)
                self.window["-BATCH_INPUT-"].update(visible=False)
            
            elif event == "-BATCH_MODE-":
                self.window["-SINGLE_INPUT-"].update(visible=False)
                self.window["-BATCH_INPUT-"].update(visible=True)
            
            # Run validation
            elif event == "-RUN-":
                # Disable run button
                self.window["-RUN-"].update(disabled=True)
                self.window["-STOP-"].update(disabled=False)
                
                # Clear previous results
                self.validation_results = []
                self._update_results_table()
                
                # Set running flag
                self.running = True
                
                try:
                    if values["-SINGLE_MODE-"]:
                        # Single account validation
                        username = values["-USERNAME-"].strip()
                        email = values["-EMAIL-"].strip() if values["-EMAIL-"] else None
                        
                        if not username:
                            sg.popup_error("Username is required")
                            self.window["-RUN-"].update(disabled=False)
                            self.window["-STOP-"].update(disabled=True)
                            self.running = False
                            continue
                        
                        # Update status
                        self.window["-LOG-OUTPUT-"].update(f"Validating Reddit account: {username}\n", append=True)
                        self.window["-PROGRESS-"].update(0)
                        
                        # Run validation in a separate thread
                        threading.Thread(
                            target=lambda: self.window.write_event_value(
                                "-RESULT-", 
                                self._validate_single_account(
                                    username=username,
                                    email=email,
                                    perform_email_verification=values["-VERIFY_EMAIL-"],
                                    perform_ai_analysis=values["-USE_AI-"]
                                )
                            ),
                            daemon=True
                        ).start()
                    
                    else:
                        # Batch validation
                        input_file = values["-INFILE-"].strip()
                        
                        if not input_file:
                            sg.popup_error("Input file is required")
                            self.window["-RUN-"].update(disabled=False)
                            self.window["-STOP-"].update(disabled=True)
                            self.running = False
                            continue
                        
                        try:
                            accounts = self._read_accounts_from_file(input_file)
                            
                            if not accounts:
                                sg.popup_warning("No accounts found in the input file")
                                self.window["-RUN-"].update(disabled=False)
                                self.window["-STOP-"].update(disabled=True)
                                self.running = False
                                continue
                            
                            # Start batch processing thread
                            self.window["-LOG-OUTPUT-"].update(f"Starting batch validation of {len(accounts)} accounts\n", append=True)
                            self.window["-PROGRESS-"].update(0)
                            
                            self.batch_thread = threading.Thread(
                                target=self._batch_worker,
                                args=(accounts, values),
                                daemon=True
                            )
                            self.batch_thread.start()
                            
                        except Exception as e:
                            sg.popup_error(f"Error reading input file: {str(e)}")
                            self.window["-RUN-"].update(disabled=False)
                            self.window["-STOP-"].update(disabled=True)
                            self.running = False
                    
                except Exception as e:
                    sg.popup_error(f"Error: {str(e)}")
                    self.window["-RUN-"].update(disabled=False)
                    self.window["-STOP-"].update(disabled=True)
                    self.running = False
            
            # Stop validation
            elif event == "-STOP-":
                self.running = False
                self.window["-LOG-OUTPUT-"].update("Stopping validation...\n", append=True)
                self.window["-STOP-"].update(disabled=True)
            
            # Clear results
            elif event == "-CLEAR-":
                self.validation_results = []
                self._update_results_table()
                self.window["-LOG-OUTPUT-"].update("")
                self.window["-PROGRESS-"].update(0)
            
            # Settings
            elif event == "-SETTINGS-":
                # Open settings window
                settings_window = self.create_settings_window()
                
                while True:
                    s_event, s_values = settings_window.read()
                    
                    if s_event in (sg.WIN_CLOSED, "-CANCEL_SETTINGS-"):
                        settings_window.close()
                        break
                    
                    elif s_event == "-THEME-":
                        # Preview theme
                        sg.theme(s_values["-THEME-"])
                        settings_window.close()
                        settings_window = self.create_settings_window()
                    
                    elif s_event == "-SAVE_SETTINGS-":
                        # Save settings
                        self.settings["theme"] = s_values["-THEME-"]
                        self.save_settings()
                        
                        # Apply theme
                        sg.theme(self.settings["theme"])
                        
                        # Restart main window
                        self.window.close()
                        self.window = sg.Window(
                            "Reddit Persona Validator",
                            self.create_main_layout(),
                            size=self.settings.get("window_size", (800, 600)),
                            resizable=True,
                            finalize=True
                        )
                        
                        settings_window.close()
                        break
            
            # View result details
            elif event == "-RESULTS_TABLE-":
                if values["-RESULTS_TABLE-"]:
                    # Get selected row index
                    selected_row = values["-RESULTS_TABLE-"][0]
                    
                    if selected_row < len(self.validation_results):
                        # Get result
                        result = self.validation_results[selected_row]
                        
                        # Open details window
                        details_window = self.create_result_details_window(result)
                        
                        # Details window event loop
                        while True:
                            d_event, _ = details_window.read()
                            
                            if d_event in (sg.WIN_CLOSED, "-CLOSE_DETAILS-"):
                                details_window.close()
                                break
            
            # Export results
            elif event == "-EXPORT-":
                if self.validation_results:
                    output_format = values["-OUT_FORMAT-"]
                    output_folder = values["-OUTFOLDER-"]
                    
                    if not output_folder:
                        sg.popup_error("Output folder is required")
                        continue
                    
                    try:
                        output_files = self._write_results(
                            self.validation_results,
                            output_folder,
                            output_format
                        )
                        
                        # Show success message
                        file_list = "\n".join([f"{fmt.upper()}: {path}" for fmt, path in output_files.items()])
                        sg.popup(f"Results exported successfully:\n\n{file_list}")
                        
                    except Exception as e:
                        sg.popup_error(f"Error exporting results: {str(e)}")
            
            # Open output folder
            elif event == "-OPEN_OUTPUT-":
                output_folder = values["-OUTFOLDER-"]
                
                if not output_folder:
                    sg.popup_error("Output folder is not specified")
                    continue
                
                folder_path = Path(output_folder)
                
                try:
                    if not folder_path.exists():
                        folder_path.mkdir(parents=True, exist_ok=True)
                    
                    # Open folder in file explorer
                    if os.name == 'nt':  # Windows
                        os.startfile(folder_path)
                    elif os.name == 'posix':  # macOS, Linux
                        if sys.platform == 'darwin':  # macOS
                            os.system(f'open "{folder_path}"')
                        else:  # Linux
                            os.system(f'xdg-open "{folder_path}"')
                
                except Exception as e:
                    sg.popup_error(f"Error opening folder: {str(e)}")
            
            # Process validation result
            elif event == "-RESULT-":
                result = values["-RESULT-"]
                self.validation_results.append(result)
                self._update_results_table()
                
                # Update log
                status = "Valid account" if result.exists else "Invalid account"
                self.window["-LOG-OUTPUT-"].update(f"Validation completed for {result.username}: {status}\n", append=True)
                
                # Update progress bar
                self.window["-PROGRESS-"].update(100)
                
                # Re-enable run button
                self.window["-RUN-"].update(disabled=False)
                self.window["-STOP-"].update(disabled=True)
                self.running = False
            
            # Progress update
            elif event == "-PROGRESS_UPDATE-":
                current, total = values["-PROGRESS_UPDATE-"]
                self.window["-PROGRESS-"].update(current * 100 // total)
            
            # Status update
            elif event == "-STATUS_UPDATE-":
                self.window["-LOG-OUTPUT-"].update(f"{values['-STATUS_UPDATE-']}\n", append=True)
            
            # Batch processing done
            elif event == "-BATCH_DONE-":
                count = values["-BATCH_DONE-"]
                self.window["-LOG-OUTPUT-"].update(f"Batch validation completed. Processed {count} accounts.\n", append=True)
                self.window["-PROGRESS-"].update(100)
            
            # Export done
            elif event == "-EXPORT_DONE-":
                output_files = values["-EXPORT_DONE-"]
                file_list = "\n".join([f"{fmt.upper()}: {path}" for fmt, path in output_files.items()])
                self.window["-LOG-OUTPUT-"].update(f"Results exported to:\n{file_list}\n", append=True)
            
            # Log message
            elif event == "-LOG-":
                self.window["-LOG-OUTPUT-"].update(f"{values['-LOG-']}\n", append=True)
            
            # Enable run button
            elif event == "-ENABLE_RUN-":
                self.window["-RUN-"].update(disabled=False)
                self.window["-STOP-"].update(disabled=True)
            
            # Error message
            elif event == "-ERROR-":
                error_msg = values["-ERROR-"]
                self.window["-LOG-OUTPUT-"].update(f"Error: {error_msg}\n", append=True)
                sg.popup_error(f"Error: {error_msg}")
                self.window["-RUN-"].update(disabled=False)
                self.window["-STOP-"].update(disabled=True)
                self.running = False
        
        # Save settings before exit
        self.save_settings()
        
        # Clean up
        if self.logger:
            self.logger.cleanup()
        
        # Close window
        self.window.close()


def main():
    """Main entry point for the GUI."""
    gui = RedditPersonaValidatorGUI()
    gui.run()


if __name__ == "__main__":
    main()
