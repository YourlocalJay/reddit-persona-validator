"""Unit tests for the browser engine module."""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import time
import json
from pathlib import Path

from src.core.browser_engine import BrowserEngine
from src.utils.proxy_rotator import ProxyRotator


class TestBrowserEngine(unittest.TestCase):
    """Test cases for the BrowserEngine class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "request_timeout": 15,
            "captcha_timeout": 20,
            "user_agent": "TestUserAgent/1.0"
        }
        
        # Mock the ProxyRotator
        self.mock_proxy_rotator = MagicMock(spec=ProxyRotator)
        self.mock_proxy_rotator.get_proxy.return_value = {
            "http": "http://test:pass@127.0.0.1:8080",
            "https": "http://test:pass@127.0.0.1:8080"
        }
        
        # Patch undetected_chromedriver
        self.uc_patcher = patch('src.core.browser_engine.uc')
        self.mock_uc = self.uc_patcher.start()
        
        # Mock Chrome driver
        self.mock_driver = MagicMock()
        self.mock_uc.Chrome.return_value = self.mock_driver
        
        # Create temporary directories
        Path("./tmp").mkdir(exist_ok=True)
    
    def tearDown(self):
        """Tear down test fixtures."""
        self.uc_patcher.stop()
    
    def test_initialization(self):
        """Test browser engine initialization."""
        with patch('src.core.browser_engine.time.time', return_value=12345):
            engine = BrowserEngine(self.config, self.mock_proxy_rotator)
            engine.initialize()
            
            # Check that undetected_chromedriver was called correctly
            self.mock_uc.Chrome.assert_called_once()
            
            # Check that user data dir was created correctly
            self.assertTrue(engine.user_data_dir.name.startswith("browser_profile_"))
            
            # Check that driver is set
            self.assertEqual(engine.driver, self.mock_driver)
            
            # Check that anti-detection measures were applied
            self.mock_driver.execute_script.assert_called_once()
            
            # Verify proxy setup
            self.mock_proxy_rotator.get_proxy.assert_called_once()
            
            # Clean up
            engine.close()
    
    def test_context_manager(self):
        """Test that context manager properly initializes and closes the browser."""
        with patch.object(BrowserEngine, 'initialize') as mock_init:
            with patch.object(BrowserEngine, 'close') as mock_close:
                with BrowserEngine(self.config) as engine:
                    mock_init.assert_called_once()
                
                mock_close.assert_called_once()
    
    def test_close(self):
        """Test that close method properly cleans up resources."""
        engine = BrowserEngine(self.config)
        engine.driver = self.mock_driver
        engine.user_data_dir = Path("./tmp/test_profile")
        engine.user_data_dir.mkdir(exist_ok=True)
        
        with patch('shutil.rmtree') as mock_rmtree:
            engine.close()
            
            # Check driver was quit
            self.mock_driver.quit.assert_called_once()
            
            # Check user data dir was removed
            mock_rmtree.assert_called_once_with(engine.user_data_dir)
            
            # Check driver was set to None
            self.assertIsNone(engine.driver)
    
    def test_login_to_reddit_success(self):
        """Test successful login to Reddit."""
        engine = BrowserEngine(self.config)
        engine.driver = self.mock_driver
        
        # Mock WebDriverWait and find_element
        with patch('src.core.browser_engine.WebDriverWait') as mock_wait:
            with patch.object(engine, '_human_like_typing') as mock_typing:
                with patch.object(engine, '_check_for_captcha', return_value=False):
                    # Set up element mocks
                    mock_username = MagicMock()
                    mock_password = MagicMock()
                    mock_button = MagicMock()
                    
                    # Configure find_element to return our mocks
                    self.mock_driver.find_element.side_effect = lambda by, selector: {
                        "loginUsername": mock_username,
                        "loginPassword": mock_password,
                        "button[type='submit']": mock_button
                    }.get(selector)
                    
                    # Configure WebDriverWait to handle the first wait (for login form)
                    mock_wait_instance = mock_wait.return_value
                    mock_wait_instance.until.side_effect = [
                        mock_username,  # First call for username field
                        TimeoutException(),  # Second call (checking for error)
                        MagicMock()  # Third call (checking for successful login)
                    ]
                    
                    # Call method under test
                    result = engine.login_to_reddit("testuser", "testpass")
                    
                    # Verify method behavior
                    self.assertTrue(result)
                    self.mock_driver.get.assert_called_once_with("https://www.reddit.com/login/")
                    mock_typing.assert_any_call(mock_username, "testuser")
                    mock_typing.assert_any_call(mock_password, "testpass")
                    mock_button.click.assert_called_once()
    
    def test_login_to_reddit_with_captcha(self):
        """Test login with CAPTCHA that gets resolved."""
        engine = BrowserEngine(self.config)
        engine.driver = self.mock_driver
        
        # Mock WebDriverWait and find_element
        with patch('src.core.browser_engine.WebDriverWait') as mock_wait:
            with patch.object(engine, '_human_like_typing'):
                with patch.object(engine, '_check_for_captcha', return_value=True):
                    with patch.object(engine, '_wait_for_captcha_resolution', return_value=True):
                        # Configure WebDriverWait for successful login after CAPTCHA
                        mock_wait_instance = mock_wait.return_value
                        mock_wait_instance.until.side_effect = [
                            MagicMock(),  # First call for username field
                            TimeoutException(),  # Second call (checking for error)
                            MagicMock()  # Third call (checking for successful login)
                        ]
                        
                        # Call method under test
                        result = engine.login_to_reddit("testuser", "testpass")
                        
                        # Verify method behavior
                        self.assertTrue(result)
    
    def test_extract_account_info(self):
        """Test extracting account information."""
        engine = BrowserEngine(self.config)
        engine.driver = self.mock_driver
        
        # Mock page source
        type(self.mock_driver).page_source = PropertyMock(
            return_value="User profile content"
        )
        
        # Mock WebDriverWait
        with patch('src.core.browser_engine.WebDriverWait') as mock_wait:
            # Configure all the element mocks
            karma_elements = [MagicMock(), MagicMock()]
            karma_elements[0].text = "10.5k"
            karma_elements[1].text = "5,234"
            
            cake_day_element = MagicMock()
            cake_day_element.text = "May 5, 2018"
            
            trophy_elements = [MagicMock(), MagicMock()]
            trophy_elements[0].text = "Verified Email"
            trophy_elements[1].text = "1-Year Club"
            
            community_elements = [MagicMock(), MagicMock()]
            community_elements[0].text = "r/python"
            community_elements[1].text = "r/programming"
            
            post_elements = [MagicMock()]
            title_element = MagicMock()
            title_element.text = "My Test Post"
            time_element = MagicMock()
            time_element.text = "2 days ago"
            subreddit_element = MagicMock()
            subreddit_element.text = "r/python"
            
            post_elements[0].find_element.side_effect = lambda by, selector: {
                "h3": title_element,
                "._3jOxDPIQ0KaOWpzvSQo-1s": time_element,
                "._3ryJoIoycVkI7FtYrCFQMf": subreddit_element
            }.get(selector)
            
            # Configure find_elements to return our mocks
            self.mock_driver.find_elements.side_effect = lambda by, selector: {
                "._1hNyZSklmcC7R_IfCUcXmZ": karma_elements,
                "._2Gq3CSlw6ertQlLjXyMFaM": trophy_elements,
                "._3Qx5bBCG_O8wVZee9J-KyJ ._1Q_zPN5YtTLQVG72OwuRUQ": community_elements,
                "._1poyrkZ7g36PawDueRza-J": post_elements,
                "//a[contains(text(), 'About')]": [MagicMock()],
                "//a[contains(text(), 'Posts')]": [MagicMock()]
            }.get(selector, [])
            
            # Configure find_element for single elements
            self.mock_driver.find_element.side_effect = lambda by, selector: {
                "span._2-nsWRm39LdEhE0RuJ4T7Y": cake_day_element
            }.get(selector)
            
            # Call method under test
            with patch.object(engine, '_calculate_account_age_days', return_value=365):
                account_info = engine.extract_account_info("testuser")
                
                # Verify results
                self.assertEqual(account_info["username"], "testuser")
                self.assertEqual(account_info["exists"], True)
                self.assertEqual(account_info["karma"], 15734)  # 10.5k + 5,234
                self.assertEqual(account_info["post_karma"], 10500)
                self.assertEqual(account_info["comment_karma"], 5234)
                self.assertEqual(account_info["account_age_days"], 365)
                self.assertEqual(account_info["cake_day"], "May 5, 2018")
                self.assertTrue(account_info["has_verified_email"])
                self.assertEqual(account_info["trophies"], ["Verified Email", "1-Year Club"])
                self.assertEqual(account_info["active_communities"], ["r/python", "r/programming"])
                self.assertEqual(len(account_info["post_history"]), 1)
                self.assertEqual(account_info["post_history"][0]["title"], "My Test Post")
    
    def test_extract_number(self):
        """Test number extraction from text with suffixes."""
        engine = BrowserEngine(self.config)
        
        # Test various formats
        self.assertEqual(engine._extract_number("10.5k"), 10500)
        self.assertEqual(engine._extract_number("5,234"), 5234)
        self.assertEqual(engine._extract_number("1.2M"), 1200000)
        self.assertEqual(engine._extract_number("123"), 123)
        self.assertEqual(engine._extract_number("invalid"), 0)
    
    def test_calculate_account_age_days(self):
        """Test account age calculation."""
        engine = BrowserEngine(self.config)
        
        with patch('src.core.browser_engine.datetime') as mock_datetime:
            # Mock datetime.now() and datetime.strptime()
            mock_now = MagicMock()
            mock_datetime.now.return_value = mock_now
            
            mock_cake_day = MagicMock()
            mock_datetime.strptime.return_value = mock_cake_day
            
            # Set up the difference between now and cake_day
            mock_diff = MagicMock()
            mock_diff.days = 365
            mock_now - mock_cake_day = mock_diff
            
            # Test the calculation
            age_days = engine._calculate_account_age_days("May 5, 2018")
            self.assertEqual(age_days, 365)
            
            # Check that strptime was called with the correct format
            mock_datetime.strptime.assert_called_with("May 5, 2018", "%b %d, %Y")


if __name__ == '__main__':
    unittest.main()
