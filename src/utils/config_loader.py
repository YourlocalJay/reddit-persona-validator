"""Configuration loader supporting YAML and environment variables."""

from typing import Dict, Optional, Any
import os
import yaml
from dotenv import load_dotenv

# Config loader module - will handle configuration loading from YAML and ENV
