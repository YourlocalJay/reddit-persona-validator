"""Unit tests for the ConfigLoader class."""

import unittest
import os
import tempfile
import yaml
from pathlib import Path

from src.utils.config_loader import ConfigLoader


class TestConfigLoader(unittest.TestCase):
    """Test suite for the ConfigLoader class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.yaml")
        self.env_path = os.path.join(self.temp_dir.name, ".env")
        
        # Sample configuration
        self.test_config = {
            "reddit": {
                "user_agent": "TestAgent/1.0",
                "timeout": 30
            },
            "proxy": {
                "enabled": True,
                "rotation_interval": 60
            },
            "scoring": {
                "min_karma": 100,
                "trust_threshold": 0.7
            }
        }
        
        # Write test configuration to file
        with open(self.config_path, 'w') as f:
            yaml.dump(self.test_config, f)
        
        # Sample environment variables
        self.env_content = """
        # Test environment variables
        REDDIT_TIMEOUT=45
        PROXY_ENABLED=false
        NEW_SECTION_VALUE=test
        """
        
        # Write environment variables to file
        with open(self.env_path, 'w') as f:
            f.write(self.env_content)
    
    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()
        
        # Clean up environment variables set during tests
        for key in ['REDDIT_TIMEOUT', 'PROXY_ENABLED', 'NEW_SECTION_VALUE']:
            if key in os.environ:
                del os.environ[key]
    
    def test_load_yaml_config(self):
        """Test loading configuration from YAML file."""
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Check if YAML config was loaded correctly
        self.assertEqual(loader.config['reddit']['user_agent'], "TestAgent/1.0")
        self.assertEqual(loader.config['proxy']['rotation_interval'], 60)
        self.assertEqual(loader.config['scoring']['min_karma'], 100)
    
    def test_environment_variable_override(self):
        """Test that environment variables override YAML settings."""
        # Manually set environment variables
        os.environ['REDDIT_TIMEOUT'] = '45'
        os.environ['PROXY_ENABLED'] = 'false'
        
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Check if environment variables overrode YAML config
        self.assertEqual(loader.config['reddit']['timeout'], 45)  # Integer conversion
        self.assertEqual(loader.config['proxy']['enabled'], False)  # Boolean conversion
        
        # Original values should be preserved if not overridden
        self.assertEqual(loader.config['reddit']['user_agent'], "TestAgent/1.0")
    
    def test_env_file_loading(self):
        """Test loading environment variables from .env file."""
        # Create loader with our test .env file
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Check if .env variables were loaded and overrode YAML config
        self.assertEqual(loader.config['reddit']['timeout'], 45)
        self.assertEqual(loader.config['proxy']['enabled'], False)
    
    def test_missing_config_file(self):
        """Test behavior when config file is missing."""
        nonexistent_path = os.path.join(self.temp_dir.name, "nonexistent.yaml")
        loader = ConfigLoader(config_path=nonexistent_path, env_file=self.env_path)
        
        # Should not raise an error, but return empty config
        self.assertIsInstance(loader.config, dict)
        
        # Environment variables should still be loaded
        self.assertEqual(loader.config.get('reddit', {}).get('timeout'), 45)
    
    def test_dict_access_methods(self):
        """Test dictionary-style access to config values."""
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Test __getitem__
        self.assertEqual(loader['reddit']['user_agent'], "TestAgent/1.0")
        
        # Test __setitem__
        loader['reddit']['user_agent'] = "NewAgent/2.0"
        self.assertEqual(loader.config['reddit']['user_agent'], "NewAgent/2.0")
        
        # Test __contains__
        self.assertTrue('reddit' in loader)
        self.assertFalse('nonexistent' in loader)
    
    def test_get_method(self):
        """Test get method with dot notation and defaults."""
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Test with existing key
        self.assertEqual(loader.get('reddit.user_agent'), "TestAgent/1.0")
        
        # Test with default value
        self.assertEqual(loader.get('nonexistent', 'default'), 'default')
        self.assertEqual(loader.get('reddit.nonexistent', 'default'), 'default')
    
    def test_set_method(self):
        """Test setting values with dot notation."""
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Test setting existing value
        loader.set('reddit.user_agent', "NewAgent/2.0")
        self.assertEqual(loader.config['reddit']['user_agent'], "NewAgent/2.0")
        
        # Test creating new nested value
        loader.set('new_section.subsection.value', 123)
        self.assertEqual(loader.config['new_section']['subsection']['value'], 123)
    
    def test_type_conversion(self):
        """Test conversion of environment variable types."""
        # Set environment variables with different types
        os.environ['NUMERIC_INT'] = '42'
        os.environ['NUMERIC_FLOAT'] = '3.14'
        os.environ['BOOLEAN_TRUE'] = 'true'
        os.environ['BOOLEAN_FALSE'] = 'false'
        os.environ['STRING_VALUE'] = 'hello world'
        
        # Create a new loader to process these variables
        loader = ConfigLoader(config_path=self.config_path, env_file=self.env_path)
        
        # Check type conversion
        self.assertIsInstance(loader.config.get('numeric_int'), int)
        self.assertEqual(loader.config.get('numeric_int'), 42)
        
        self.assertIsInstance(loader.config.get('numeric_float'), float)
        self.assertEqual(loader.config.get('numeric_float'), 3.14)
        
        self.assertIsInstance(loader.config.get('boolean_true'), bool)
        self.assertEqual(loader.config.get('boolean_true'), True)
        
        self.assertIsInstance(loader.config.get('boolean_false'), bool)
        self.assertEqual(loader.config.get('boolean_false'), False)
        
        self.assertIsInstance(loader.config.get('string_value'), str)
        self.assertEqual(loader.config.get('string_value'), 'hello world')
        
        # Clean up
        for key in ['NUMERIC_INT', 'NUMERIC_FLOAT', 'BOOLEAN_TRUE', 'BOOLEAN_FALSE', 'STRING_VALUE']:
            if key in os.environ:
                del os.environ[key]


if __name__ == '__main__':
    unittest.main()
