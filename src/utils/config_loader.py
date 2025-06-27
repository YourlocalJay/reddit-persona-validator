"""Configuration loader for Reddit Persona Validator.

This module provides utility functions for loading configuration from YAML files
and environment variables with proper error handling and type validation.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# Set up logging
logger = logging.getLogger(__name__)


class ConfigLoader:
    """Utility class for loading configuration from YAML files and environment variables."""
    
    @staticmethod
    def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Dict containing configuration
            
        Raises:
            FileNotFoundError: If config file not found
            yaml.YAMLError: If config file is invalid
        """
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
                
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            raise
    
    @staticmethod
    def load_env_variables(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Override configuration with environment variables.
        
        Environment variables should be in the format:
        REDDIT_VALIDATOR_{SECTION}_{KEY}=value
        
        Example:
        REDDIT_VALIDATOR_PROXY_ROTATION_INTERVAL=300
        
        Args:
            config: Dictionary containing configuration
            
        Returns:
            Updated dictionary with environment variables
        """
        for env_var, value in os.environ.items():
            if env_var.startswith("REDDIT_VALIDATOR_"):
                parts = env_var[17:].lower().split("_")
                
                if len(parts) < 2:
                    continue
                
                section = parts[0]
                key = "_".join(parts[1:])
                
                # Create section if it doesn't exist
                if section not in config:
                    config[section] = {}
                
                # Try to convert value to appropriate type
                if value.lower() in ("true", "yes", "y", "1"):
                    config[section][key] = True
                elif value.lower() in ("false", "no", "n", "0"):
                    config[section][key] = False
                elif value.isdigit():
                    config[section][key] = int(value)
                elif value.replace(".", "", 1).isdigit() and value.count(".") <= 1:
                    config[section][key] = float(value)
                else:
                    config[section][key] = value
                
                logger.debug(f"Overriding config: {section}.{key}={value}")
        
        return config
    
    @staticmethod
    def load(config_path: str = "config/config.yaml",
             load_env: bool = True) -> Dict[str, Any]:
        """
        Load configuration from YAML file and environment variables.
        
        Args:
            config_path: Path to configuration file
            load_env: Whether to load environment variables
            
        Returns:
            Dict containing configuration
        """
        config = ConfigLoader.load_config(config_path)
        
        if load_env:
            config = ConfigLoader.load_env_variables(config)
        
        return config
