"""Configuration loader supporting YAML and environment variables."""

import os
import yaml
import logging
from typing import Dict, Optional, Any
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ConfigLoader:
    """
    Configuration loader that combines YAML files and environment variables.
    Provides cascading configuration with environment variable overrides.
    """
    
    def __init__(self, config_path: str = "config/config.yaml", env_file: str = "config/.env"):
        """
        Initialize config loader.
        
        Args:
            config_path: Path to YAML config file
            env_file: Path to .env file
        """
        self.config_path = config_path
        self.env_file = env_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file and environment variables.
        Environment variables override YAML settings.
        
        Returns:
            Dict containing configuration
        """
        config = {}
        
        # 1. Load YAML config if exists
        yaml_config = self._load_yaml_config()
        if yaml_config:
            config.update(yaml_config)
        
        # 2. Load environment variables
        self._load_env_vars()
        
        # 3. Override with environment variables
        env_config = self._get_env_overrides()
        self._deep_update(config, env_config)
        
        return config
    
    def _load_yaml_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Returns:
            Dict containing YAML configuration or empty dict if file not found
        """
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(f"Config file not found: {self.config_path}")
                return {}
                
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
                return config or {}
        except Exception as e:
            logger.error(f"Failed to load YAML config: {str(e)}")
            return {}
    
    def _load_env_vars(self) -> None:
        """Load environment variables from .env file if it exists."""
        try:
            env_file = Path(self.env_file)
            if env_file.exists():
                load_dotenv(env_file)
                logger.info(f"Loaded environment variables from {self.env_file}")
        except Exception as e:
            logger.error(f"Failed to load .env file: {str(e)}")
    
    def _get_env_overrides(self) -> Dict[str, Any]:
        """
        Extract configuration from environment variables.
        Uses a naming convention to map environment variables to config keys.
        
        For example:
        - REDDIT_USER_AGENT maps to config["reddit"]["user_agent"]
        - PROXY_ROTATION_INTERVAL maps to config["proxy"]["rotation_interval"]
        
        Returns:
            Dict containing configuration from environment variables
        """
        result = {}
        
        for key, value in os.environ.items():
            # Skip non-config environment variables
            if not key.isupper() or key.startswith("_"):
                continue
                
            # Convert environment variable to config path
            parts = key.lower().split("_")
            
            # Handle special case for API keys
            if key.endswith("_API_KEY"):
                # Keep API keys at top level
                result[key] = value
                continue
                
            # Build nested dictionary structure
            current = result
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # Try to convert to appropriate type
                    current[part] = self._convert_value(value)
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
        
        return result
    
    def _convert_value(self, value: str) -> Any:
        """
        Convert string value to appropriate Python type.
        
        Args:
            value: String value to convert
            
        Returns:
            Converted value as bool, int, float, or original string
        """
        # Boolean conversion
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False
        
        # Number conversion
        try:
            if value.isdigit():
                return int(value)
            if value.replace(".", "", 1).isdigit():
                return float(value)
        except (ValueError, AttributeError):
            pass
        
        # Default to string
        return value
    
    def _deep_update(self, target: Dict, source: Dict) -> None:
        """
        Recursively update a dictionary with another dictionary.
        
        Args:
            target: Target dictionary to update
            source: Source dictionary with new values
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key with optional default.
        
        Args:
            key: Configuration key (can use dot notation for nested keys)
            default: Default value if key not found
            
        Returns:
            Configuration value or default if not found
        """
        try:
            # Handle dot notation (e.g., "reddit.user_agent")
            if "." in key:
                parts = key.split(".")
                value = self.config
                for part in parts:
                    value = value[part]
                return value
            return self.config[key]
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value.
        
        Args:
            key: Configuration key (can use dot notation for nested keys)
            value: Value to set
        """
        # Handle dot notation (e.g., "reddit.user_agent")
        if "." in key:
            parts = key.split(".")
            config = self.config
            for part in parts[:-1]:
                if part not in config:
                    config[part] = {}
                config = config[part]
            config[parts[-1]] = value
        else:
            self.config[key] = value
    
    def __getitem__(self, key: str) -> Any:
        """Dictionary-style access to configuration."""
        value = self.get(key)
        if value is None:
            raise KeyError(f"Configuration key not found: {key}")
        return value
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Dictionary-style setting of configuration values."""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """Check if configuration contains a key."""
        return self.get(key) is not None


# Create a singleton instance for global access
config = ConfigLoader().config
