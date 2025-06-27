"""Unit tests for CookieManager."""

import unittest
import os
import tempfile
import json
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.utils.cookie_manager import CookieManager


class TestCookieManager(unittest.TestCase):
    """Test suite for the CookieManager class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Set up a fixed encryption key for testing
        self.test_key = "dGVzdGtleWZvcmNvb2tpZW1hbmFnZXJ0ZXN0aW5n"
        self.test_salt = b'testsaltfortesting'
        
        # Test cookie data
        self.test_cookies = [
            {
                "name": "session_id",
                "value": "abc123",
                "domain": "reddit.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "expiry": 1722222222
            },
            {
                "name": "user_id",
                "value": "user_12345",
                "domain": "reddit.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "expiry": 1722222222
            }
        ]
        
        # Create a cookie manager with test key
        self.cookie_manager = CookieManager(
            encryption_key=self.test_key,
            salt=self.test_salt
        )
        
        # Override cookies directory to use temp dir
        self.cookie_manager.cookies_dir = Path(self.temp_dir.name)
    
    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()
    
    def test_initialization(self):
        """Test cookie manager initialization."""
        # Test initialization with defaults
        manager1 = CookieManager()
        self.assertIsNotNone(manager1.encryption_key)
        self.assertIsNotNone(manager1.salt)
        self.assertIsNotNone(manager1.fernet)
        
        # Test initialization with provided key and salt
        manager2 = CookieManager(encryption_key=self.test_key, salt=self.test_salt)
        self.assertEqual(manager2.encryption_key, self.test_key)
        self.assertEqual(manager2.salt, self.test_salt)
    
    def test_save_and_load_cookies(self):
        """Test saving and loading cookies with encryption."""
        # Create a mock driver
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = self.test_cookies
        
        # Path for test cookie file
        cookie_path = os.path.join(self.temp_dir.name, "test_user.json")
        
        # Test saving cookies
        save_result = self.cookie_manager.save_cookies(mock_driver, cookie_path)
        self.assertTrue(save_result)
        self.assertTrue(os.path.exists(cookie_path))
        
        # Verify the saved file is encrypted (not plain JSON)
        with open(cookie_path, 'rb') as f:
            data = f.read()
            # Encrypted data should not be valid JSON
            with self.assertRaises(json.JSONDecodeError):
                json.loads(data)
        
        # Test loading cookies
        mock_driver.current_url = "data:,"
        load_result = self.cookie_manager.load_cookies(mock_driver, cookie_path)
        self.assertTrue(load_result)
        
        # Verify that add_cookie was called with correct data
        self.assertEqual(mock_driver.add_cookie.call_count, len(self.test_cookies))
        for cookie in self.test_cookies:
            mock_driver.add_cookie.assert_any_call(cookie)
    
    def test_load_cookies_with_redirect(self):
        """Test loading cookies when browser needs to redirect first."""
        # Create a mock driver
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = self.test_cookies
        
        # Path for test cookie file
        cookie_path = os.path.join(self.temp_dir.name, "test_user.json")
        
        # Save cookies
        self.cookie_manager.save_cookies(mock_driver, cookie_path)
        
        # Test loading cookies when browser is on data:, (needs redirect)
        mock_driver.current_url = "data:,"
        self.cookie_manager.load_cookies(mock_driver, cookie_path)
        
        # Verify that get was called to set the URL before adding cookies
        mock_driver.get.assert_called_with("https://www.reddit.com")
    
    def test_load_nonexistent_cookies(self):
        """Test loading cookies when file doesn't exist."""
        mock_driver = MagicMock()
        nonexistent_path = os.path.join(self.temp_dir.name, "nonexistent.json")
        
        result = self.cookie_manager.load_cookies(mock_driver, nonexistent_path)
        
        self.assertFalse(result)
        mock_driver.add_cookie.assert_not_called()
    
    def test_encryption_key_mismatch(self):
        """Test loading cookies with wrong encryption key."""
        # Save cookies with one key
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = self.test_cookies
        cookie_path = os.path.join(self.temp_dir.name, "test_user.json")
        self.cookie_manager.save_cookies(mock_driver, cookie_path)
        
        # Try to load with different key
        different_key = "ZGlmZmVyZW50a2V5Zm9ydGVzdGluZ2Nvb2tpZW1hbmFnZXI="
        manager2 = CookieManager(encryption_key=different_key, salt=self.test_salt)
        result = manager2.load_cookies(mock_driver, cookie_path)
        
        self.assertFalse(result)
        # After failure, no cookies should be added
        mock_driver.add_cookie.assert_not_called()
    
    def test_delete_cookies(self):
        """Test deleting cookie files."""
        # Create a mock driver and save cookies
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = self.test_cookies
        cookie_path = os.path.join(self.temp_dir.name, "test_user.json")
        self.cookie_manager.save_cookies(mock_driver, cookie_path)
        
        # Verify file exists
        self.assertTrue(os.path.exists(cookie_path))
        
        # Test deleting
        delete_result = self.cookie_manager.delete_cookies(cookie_path)
        self.assertTrue(delete_result)
        self.assertFalse(os.path.exists(cookie_path))
        
        # Test deleting nonexistent file
        delete_result2 = self.cookie_manager.delete_cookies(cookie_path)
        self.assertFalse(delete_result2)
    
    def test_list_saved_cookies(self):
        """Test listing saved cookie files."""
        # Create some test cookie files
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = self.test_cookies
        
        paths = [
            os.path.join(self.temp_dir.name, "user1.json"),
            os.path.join(self.temp_dir.name, "user2.json"),
            os.path.join(self.temp_dir.name, "user3.json")
        ]
        
        for path in paths:
            self.cookie_manager.save_cookies(mock_driver, path)
        
        # Test listing
        with patch.object(self.cookie_manager, 'cookies_dir', Path(self.temp_dir.name)):
            cookie_files = self.cookie_manager.list_saved_cookies()
            
            self.assertEqual(len(cookie_files), 3)
            self.assertIn("user1.json", cookie_files)
            self.assertIn("user2.json", cookie_files)
            self.assertIn("user3.json", cookie_files)
    
    def test_clear_all_cookies(self):
        """Test clearing all cookie files."""
        # Create some test cookie files
        mock_driver = MagicMock()
        mock_driver.get_cookies.return_value = self.test_cookies
        
        paths = [
            os.path.join(self.temp_dir.name, "user1.json"),
            os.path.join(self.temp_dir.name, "user2.json")
        ]
        
        for path in paths:
            self.cookie_manager.save_cookies(mock_driver, path)
        
        # Test clearing all
        with patch.object(self.cookie_manager, 'cookies_dir', Path(self.temp_dir.name)):
            count = self.cookie_manager.clear_all_cookies()
            
            self.assertEqual(count, 2)
            self.assertFalse(os.path.exists(paths[0]))
            self.assertFalse(os.path.exists(paths[1]))
    
    def test_exception_handling(self):
        """Test handling of exceptions during operations."""
        mock_driver = MagicMock()
        
        # Test save exception
        mock_driver.get_cookies.side_effect = Exception("Cookies error")
        result = self.cookie_manager.save_cookies(mock_driver, "test.json")
        self.assertFalse(result)
        
        # Test load exception
        mock_driver.get_cookies.side_effect = None
        mock_driver.add_cookie.side_effect = Exception("Add cookie error")
        
        # First save some cookies normally
        cookie_path = os.path.join(self.temp_dir.name, "test_user.json")
        mock_driver.get_cookies.return_value = self.test_cookies
        self.cookie_manager.save_cookies(mock_driver, cookie_path)
        
        # Then test loading with exception
        result = self.cookie_manager.load_cookies(mock_driver, cookie_path)
        self.assertTrue(result)  # Should still return True even if some cookies fail
        
        # Test delete exception
        with patch('pathlib.Path.unlink', side_effect=Exception("Delete error")):
            result = self.cookie_manager.delete_cookies(cookie_path)
            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
