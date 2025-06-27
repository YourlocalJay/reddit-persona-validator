"""Interface initialization module for Reddit Persona Validator."""

from typing import Dict, Optional, Any

# Import interfaces
from .cli import PersonaValidatorCLI
from .api import app as api_app
from .gui import RedditPersonaValidatorGUI

__all__ = ["PersonaValidatorCLI", "api_app", "RedditPersonaValidatorGUI"]
