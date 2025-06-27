"""Undetectable Chrome driver manager for web automation."""

import os
import time
import logging
import json
import random
from typing import Dict, Optional, Any, List, Tuple
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    StaleElementReferenceException,
    ElementClickInterceptedException
)

from ..utils.proxy_rotator import ProxyRotator

logger = logging.getLogger(__name__)

class BrowserEngine:
    """
    Manages undetected Chrome browser sessions for Reddit interactions.
    Handles login, CAPTCHA detection, and data extraction with anti-detection measures.
    """
    
    def __init__(self, config: Dict[str, Any], proxy_rotator: Optional[ProxyRotator] = None):
        """
        Initialize the browser engine with configuration and optional proxy support.
        
        Args:
            config: Dictionary containing browser configuration settings
            proxy_rotator: Optional proxy rotation utility for IP rotation
        """
        self.config = config
        self.proxy_rotator = proxy_rotator
        self.driver = None
        self.user_data_dir = None
        self.request_timeout = config.get("request_timeout", 30)
        self.captcha_timeout = config.get("captcha_timeout", 45)
        self.user_agent = config.get("user_agent", "RedditPersonaValidator/0.1.0")
        
    def __enter__(self):
        """Context manager entry point that initializes the browser."""
        self.initialize()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point that closes the browser."""
        self.close()
        
    def initialize(self) -> None:
        """
        Initialize an undetected Chrome browser session with anti-detection measures.
        """
        if self.driver:
            logger.warning("Browser already initialized, closing existing session first")
            self.close()
            
        # Create a temporary user data directory for this session
        self.user_data_dir = Path(f"./tmp/browser_profile_{int(time.time())}")
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Initializing browser with profile at {self.user_data_dir}")
        
        # Configure Chrome options
        options = uc.ChromeOptions()
        
        # Add standard options to avoid detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--lang=en-US")
        options.add_argument(f"--user-agent={self.user_agent}")
        
        # Get proxy if available
        proxy = None
        if self.proxy_rotator:
            proxy = self.proxy_rotator.get_proxy()
            if proxy:
                proxy_url = proxy["http"]
                logger.info(f"Using proxy: {proxy_url}")
                options.add_argument(f"--proxy-server={proxy_url}")
                
        try:
            # Initialize the undetected Chrome driver
            self.driver = uc.Chrome(
                options=options,
                user_data_dir=str(self.user_data_dir),
                use_subprocess=True,
                headless=False,  # Headless mode is often detected, avoid for Reddit
                version_main=119  # Specify Chrome version if needed
            )
            
            # Set default timeouts
            self.driver.implicitly_wait(10)
            self.driver.set_page_load_timeout(self.request_timeout)
            
            # Execute standard anti-detection script
            self._apply_anti_detection_measures()
            
            logger.info("Browser engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            if proxy and self.proxy_rotator:
                self.proxy_rotator.mark_proxy_failure(proxy["http"])
            self.close()
            raise
    
    def _apply_anti_detection_measures(self) -> None:
        """Apply JavaScript patches to avoid automation detection."""
        # Mask automation indicators
        self.driver.execute_script("""
            // Overwrite the navigator properties used for bot detection
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            
            // Clear automation-related properties
            if (window.navigator.plugins) {
                Object.defineProperty(navigator, 'plugins', {
                    get: function() {
                        // Simulate random plugins
                        return [1, 2, 3, 4, 5];
                    }
                });
            }
            
            // Modify navigator properties
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            
            // Add random screen properties
            const screenProps = {
                availHeight: Math.floor(Math.random() * 200) + 900,
                availWidth: Math.floor(Math.random() * 400) + 1400,
                colorDepth: 24,
                height: Math.floor(Math.random() * 200) + 1000,
                width: Math.floor(Math.random() * 400) + 1500
            };
            
            for (const [key, value] of Object.entries(screenProps)) {
                Object.defineProperty(screen, key, { get: () => value });
            }
        """)
    
    def close(self) -> None:
        """Close the browser session and clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser session closed")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            finally:
                self.driver = None
                
        # Clean up the user data directory
        if self.user_data_dir and self.user_data_dir.exists():
            try:
                import shutil
                shutil.rmtree(self.user_data_dir)
                logger.info(f"Removed temporary profile: {self.user_data_dir}")
            except Exception as e:
                logger.error(f"Failed to remove profile directory: {e}")
    
    def login_to_reddit(self, username: str, password: str) -> bool:
        """
        Log in to Reddit with the provided credentials.
        Handles CAPTCHA challenges if they appear.
        
        Args:
            username: Reddit username
            password: Reddit password
            
        Returns:
            True if login successful, False otherwise
        """
        if not self.driver:
            self.initialize()
            
        try:
            # Navigate to Reddit login page
            self.driver.get("https://www.reddit.com/login/")
            
            # Wait for login form to load
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "loginUsername"))
            )
            
            # Add random delays between actions to mimic human behavior
            self._random_delay(0.5, 1.5)
            
            # Enter username with human-like typing
            self._human_like_typing(username_field, username)
            
            # Find and enter password
            password_field = self.driver.find_element(By.ID, "loginPassword")
            self._random_delay(0.5, 1.0)
            self._human_like_typing(password_field, password)
            
            # Click the login button
            self._random_delay(0.5, 1.0)
            login_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()
            
            # Check if CAPTCHA appears
            if self._check_for_captcha():
                logger.warning("CAPTCHA detected during login")
                # Wait for manual CAPTCHA resolution or timeout
                if not self._wait_for_captcha_resolution():
                    logger.error("CAPTCHA resolution timed out")
                    return False
            
            # Wait for successful login redirect or login error
            try:
                # Check for login errors
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".AnimatedForm__submitError"))
                )
                error_msg = self.driver.find_element(By.CSS_SELECTOR, ".AnimatedForm__submitError").text
                logger.error(f"Login failed: {error_msg}")
                return False
            except TimeoutException:
                # No error found, check for successful login
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "._1YWXCINvcuU7nk89fhWM5b"))
                    )
                    logger.info(f"Successfully logged in as {username}")
                    return True
                except TimeoutException:
                    logger.error("Login process timed out or failed")
                    return False
                    
        except Exception as e:
            logger.error(f"Login process failed: {e}")
            return False
    
    def _check_for_captcha(self) -> bool:
        """
        Check if a CAPTCHA challenge is present on the page.
        
        Returns:
            True if CAPTCHA detected, False otherwise
        """
        try:
            # Check for common CAPTCHA indicators
            captcha_elements = [
                "iframe[src*='recaptcha']",
                "iframe[src*='hcaptcha']",
                ".captcha",
                "#captcha",
                "[data-recaptcha]"
            ]
            
            for selector in captcha_elements:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    logger.info(f"CAPTCHA detected: {selector}")
                    return True
                    
            return False
        except Exception as e:
            logger.error(f"Error checking for CAPTCHA: {e}")
            return False
    
    def _wait_for_captcha_resolution(self) -> bool:
        """
        Wait for manual CAPTCHA resolution or timeout.
        
        Returns:
            True if CAPTCHA appears to be resolved, False if timed out
        """
        logger.info(f"Waiting up to {self.captcha_timeout} seconds for CAPTCHA resolution")
        
        end_time = time.time() + self.captcha_timeout
        while time.time() < end_time:
            try:
                # Check if we're still on the login page
                current_url = self.driver.current_url
                if "login" not in current_url:
                    logger.info("URL changed, CAPTCHA appears to be resolved")
                    return True
                    
                # Check if CAPTCHA is still present
                if not self._check_for_captcha():
                    logger.info("CAPTCHA no longer detected")
                    return True
                    
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error while waiting for CAPTCHA resolution: {e}")
                return False
                
        logger.warning("CAPTCHA resolution timed out")
        return False
    
    def extract_account_info(self, username: str) -> Dict[str, Any]:
        """
        Extract account information for a given Reddit user.
        
        Args:
            username: Reddit username to extract information for
            
        Returns:
            Dictionary containing account information
        """
        if not self.driver:
            self.initialize()
            
        account_info = {
            "username": username,
            "karma": 0,
            "account_age_days": 0,
            "has_verified_email": False,
            "is_moderator": False,
            "trophies": [],
            "active_communities": [],
            "post_history": []
        }
        
        try:
            # Navigate to user profile
            profile_url = f"https://www.reddit.com/user/{username}"
            logger.info(f"Navigating to profile: {profile_url}")
            self.driver.get(profile_url)
            
            # Check if user exists
            if "Sorry, nobody on Reddit goes by that name" in self.driver.page_source:
                logger.warning(f"User {username} does not exist")
                account_info["exists"] = False
                return account_info
                
            account_info["exists"] = True
            
            # Extract karma and account age
            try:
                # Wait for profile to load
                WebDriverWait(self.driver, self.request_timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "._1hNyZSklmcC7R_IfCUcXmZ"))
                )
                
                # Extract karma
                karma_elements = self.driver.find_elements(By.CSS_SELECTOR, "._1hNyZSklmcC7R_IfCUcXmZ")
                if len(karma_elements) >= 2:
                    post_karma = self._extract_number(karma_elements[0].text)
                    comment_karma = self._extract_number(karma_elements[1].text)
                    account_info["post_karma"] = post_karma
                    account_info["comment_karma"] = comment_karma
                    account_info["karma"] = post_karma + comment_karma
                    
                # Extract account age
                cake_day_element = self.driver.find_element(By.CSS_SELECTOR, "span._2-nsWRm39LdEhE0RuJ4T7Y")
                if cake_day_element:
                    cake_day_text = cake_day_element.text
                    account_info["cake_day"] = cake_day_text
                    account_info["account_age_days"] = self._calculate_account_age_days(cake_day_text)
            except Exception as e:
                logger.error(f"Error extracting basic profile info: {e}")
                
            # Extract trophies
            try:
                # Click on 'More Options' or 'About' tab if needed to see trophies
                more_options = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'About')]")
                if more_options:
                    more_options[0].click()
                    time.sleep(1)
                
                trophy_elements = self.driver.find_elements(By.CSS_SELECTOR, "._2Gq3CSlw6ertQlLjXyMFaM")
                trophies = []
                for trophy in trophy_elements:
                    try:
                        trophy_name = trophy.text.strip()
                        if trophy_name:
                            trophies.append(trophy_name)
                    except:
                        pass
                        
                account_info["trophies"] = trophies
                
                # Check for verified email trophy
                account_info["has_verified_email"] = any("Verified Email" in trophy for trophy in trophies)
                
                # Check if user is a moderator
                account_info["is_moderator"] = any("Mod" in trophy for trophy in trophies)
            except Exception as e:
                logger.error(f"Error extracting trophies: {e}")
                
            # Extract active communities
            try:
                community_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "._3Qx5bBCG_O8wVZee9J-KyJ ._1Q_zPN5YtTLQVG72OwuRUQ"
                )
                communities = []
                for community in community_elements[:10]:  # Limit to top 10
                    try:
                        communities.append(community.text.strip())
                    except:
                        pass
                        
                account_info["active_communities"] = communities
            except Exception as e:
                logger.error(f"Error extracting communities: {e}")
                
            # Extract recent post history (titles and timestamps)
            try:
                # Click on Posts tab
                posts_tab = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Posts')]")
                if posts_tab:
                    posts_tab[0].click()
                    time.sleep(2)
                    
                    # Wait for posts to load
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "._1poyrkZ7g36PawDueRza-J"))
                    )
                    
                    # Get post elements
                    post_elements = self.driver.find_elements(By.CSS_SELECTOR, "._1poyrkZ7g36PawDueRza-J")
                    posts = []
                    
                    for post in post_elements[:5]:  # Limit to 5 most recent posts
                        try:
                            title_element = post.find_element(By.CSS_SELECTOR, "h3")
                            title = title_element.text if title_element else "Unknown Title"
                            
                            time_element = post.find_element(By.CSS_SELECTOR, "._3jOxDPIQ0KaOWpzvSQo-1s")
                            time_posted = time_element.text if time_element else "Unknown Time"
                            
                            subreddit_element = post.find_element(By.CSS_SELECTOR, "._3ryJoIoycVkI7FtYrCFQMf")
                            subreddit = subreddit_element.text if subreddit_element else "Unknown Subreddit"
                            
                            posts.append({
                                "title": title,
                                "time_posted": time_posted,
                                "subreddit": subreddit
                            })
                        except Exception as post_error:
                            logger.debug(f"Error extracting post data: {post_error}")
                            
                    account_info["post_history"] = posts
            except Exception as e:
                logger.error(f"Error extracting post history: {e}")
                
            return account_info
            
        except Exception as e:
            logger.error(f"Error extracting account info for {username}: {e}")
            return account_info
    
    def _extract_number(self, text: str) -> int:
        """
        Extract numeric value from text, handling suffixes like 'k' for thousands.
        
        Args:
            text: Text containing a number (e.g., "10.5k")
            
        Returns:
            Integer value
        """
        try:
            text = text.strip().lower().replace(',', '')
            if 'k' in text:
                return int(float(text.replace('k', '')) * 1000)
            elif 'm' in text:
                return int(float(text.replace('m', '')) * 1000000)
            else:
                return int(float(text))
        except Exception:
            return 0
    
    def _calculate_account_age_days(self, cake_day_text: str) -> int:
        """
        Calculate account age in days from cake day text.
        
        Args:
            cake_day_text: Text showing when account was created (e.g., "May 5, 2018")
            
        Returns:
            Age in days
        """
        try:
            from datetime import datetime
            
            # Handle various date formats
            formats = [
                "%b %d, %Y",  # "May 5, 2018"
                "%B %d, %Y",  # "May 5, 2018"
                "%d %b %Y",   # "5 May 2018"
                "%d %B %Y"    # "5 May 2018"
            ]
            
            cake_day = None
            for fmt in formats:
                try:
                    cake_day = datetime.strptime(cake_day_text, fmt)
                    break
                except ValueError:
                    continue
                    
            if cake_day:
                days = (datetime.now() - cake_day).days
                return max(0, days)  # Ensure non-negative
            return 0
        except Exception as e:
            logger.error(f"Error calculating account age: {e}")
            return 0
    
    def _random_delay(self, min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
        """
        Wait for a random amount of time to simulate human behavior.
        
        Args:
            min_seconds: Minimum wait time in seconds
            max_seconds: Maximum wait time in seconds
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def _human_like_typing(self, element: Any, text: str) -> None:
        """
        Type text into an element with human-like variations in timing.
        
        Args:
            element: Web element to type into
            text: Text to type
        """
        element.clear()
        for char in text:
            element.send_keys(char)
            # Random delay between keystrokes
            time.sleep(random.uniform(0.05, 0.15))
            
        # Add a short pause after typing
        time.sleep(random.uniform(0.2, 0.5))
