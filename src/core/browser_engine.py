"""
Browser engine module for automated Reddit interaction.

This module handles browser automation tasks such as logging into Reddit,
navigating pages, and extracting data while handling CAPTCHAs and other challenges.
"""

from typing import Dict, List, Optional, Union, Any
import logging
import time
import random
import json
from pathlib import Path
from datetime import datetime

# Import undetected-chromedriver with proper type hints
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, 
        NoSuchElementException,
        ElementClickInterceptedException,
        StaleElementReferenceException
    )
except ImportError:
    logging.error("Required dependencies not installed. Please run: pip install undetected-chromedriver selenium")
    raise

logger = logging.getLogger(__name__)

class BrowserEngine:
    """Browser automation engine using undetected-chromedriver."""
    
    def __init__(
        self,
        headless: bool = True,
        proxy: Optional[str] = None,
        user_agent: Optional[str] = None,
        cookie_manager: Any = None,
        captcha_solver: Any = None,
        screenshot_dir: Optional[str] = None
    ):
        """Initialize the browser engine.
        
        Args:
            headless: Run in headless mode (no UI)
            proxy: Proxy string in format "host:port:user:pass"
            user_agent: Custom user agent string
            cookie_manager: Cookie management instance
            captcha_solver: Optional CAPTCHA solving service
            screenshot_dir: Directory to save debug screenshots
        """
        self.headless = headless
        self.proxy = proxy
        self.user_agent = user_agent
        self.cookie_manager = cookie_manager
        self.captcha_solver = captcha_solver
        self.screenshot_dir = screenshot_dir
        self.driver = None
        self.proxy_blocked = False
        self.current_proxy = proxy
        self.has_session_cookies = False
        
        if screenshot_dir:
            Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
        
        self._initialize_browser()
    
    def _initialize_browser(self) -> None:
        """Initialize the browser with appropriate settings."""
        logger.info("Initializing browser engine")
        
        options = uc.ChromeOptions()
        
        if self.headless:
            options.add_argument("--headless")
        
        # Add proxy if specified
        if self.proxy:
            if ":" in self.proxy:
                parts = self.proxy.split(":")
                if len(parts) == 2:  # host:port format
                    host, port = parts
                    options.add_argument(f"--proxy-server={host}:{port}")
                elif len(parts) == 4:  # host:port:user:pass format
                    host, port, user, password = parts
                    options.add_argument(f"--proxy-server={host}:{port}")
                    # Auth will be handled during navigation with selenium-wire
            else:
                options.add_argument(f"--proxy-server={self.proxy}")
        
        # Add user agent if specified
        if self.user_agent:
            options.add_argument(f"user-agent={self.user_agent}")
        
        # Additional options to avoid detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        
        # Initialize browser
        try:
            self.driver = uc.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            logger.info("Browser initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            raise
    
    def _take_screenshot(self, name: str) -> Optional[str]:
        """Take a screenshot for debugging purposes.
        
        Args:
            name: Screenshot file name
            
        Returns:
            Path to the screenshot file or None if failed
        """
        if not self.screenshot_dir or not self.driver:
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{name}.png"
            path = Path(self.screenshot_dir) / filename
            self.driver.save_screenshot(str(path))
            logger.debug(f"Screenshot saved: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"Failed to take screenshot: {str(e)}")
            return None
    
    def _random_wait(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """Wait a random amount of time to simulate human behavior.
        
        Args:
            min_seconds: Minimum wait time in seconds
            max_seconds: Maximum wait time in seconds
        """
        wait_time = random.uniform(min_seconds, max_seconds)
        time.sleep(wait_time)
    
    def _check_for_captcha(self) -> bool:
        """Check if a CAPTCHA is present and solve it if possible.
        
        Returns:
            True if CAPTCHA was solved or not present, False if unable to solve
        """
        if not self.driver:
            return False
        
        captcha_indicators = [
            "//iframe[contains(@src, 'recaptcha')]",
            "//iframe[contains(@src, 'hcaptcha')]",
            "//div[contains(@class, 'captcha')]",
            "//div[contains(text(), 'robot')]",
            "//div[contains(text(), 'CAPTCHA')]"
        ]
        
        for indicator in captcha_indicators:
            try:
                captcha_element = self.driver.find_elements(By.XPATH, indicator)
                if captcha_element:
                    logger.info("CAPTCHA detected")
                    self._take_screenshot("captcha_detected")
                    
                    if self.captcha_solver:
                        logger.info("Attempting to solve CAPTCHA")
                        solved = self.captcha_solver.solve(self.driver)
                        if solved:
                            logger.info("CAPTCHA solved successfully")
                            return True
                    
                    logger.warning("Unable to solve CAPTCHA automatically")
                    return False
            except Exception:
                continue
        
        return True  # No CAPTCHA detected
    
    def _check_for_proxy_block(self) -> bool:
        """Check if the current proxy is blocked.
        
        Returns:
            True if proxy is blocked, False otherwise
        """
        if not self.driver:
            return False
        
        block_indicators = [
            "//div[contains(text(), 'blocked')]",
            "//div[contains(text(), 'suspicious')]",
            "//div[contains(text(), 'unusual activity')]",
            "//div[contains(text(), 'automated')]",
            "//div[contains(text(), 'we noticed')]",
            "//div[contains(text(), 'your IP')]"
        ]
        
        for indicator in block_indicators:
            try:
                block_element = self.driver.find_elements(By.XPATH, indicator)
                if block_element:
                    logger.warning("Proxy appears to be blocked")
                    self._take_screenshot("proxy_blocked")
                    self.proxy_blocked = True
                    return True
            except Exception:
                continue
        
        return False
    
    def login_to_reddit(self, username: str, password: str) -> bool:
        """Log in to Reddit with the provided credentials.
        
        Args:
            username: Reddit username
            password: Reddit password
            
        Returns:
            True if login successful, False otherwise
        """
        if not self.driver:
            self._initialize_browser()
        
        logger.info(f"Attempting to login as {username}")
        
        try:
            # Navigate to Reddit login page
            self.driver.get("https://www.reddit.com/login/")
            self._random_wait(2.0, 4.0)
            
            # Check for cookie banner and accept if present
            try:
                cookie_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept')]"))
                )
                cookie_button.click()
                self._random_wait()
            except TimeoutException:
                logger.debug("No cookie banner found")
            
            # Enter username
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "loginUsername"))
            )
            username_field.clear()
            self._type_like_human(username_field, username)
            
            # Enter password
            password_field = self.driver.find_element(By.ID, "loginPassword")
            password_field.clear()
            self._type_like_human(password_field, password)
            
            # Click login button
            login_button = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Log In')]")
            login_button.click()
            
            # Wait for login to complete
            self._random_wait(3.0, 5.0)
            
            # Check for CAPTCHA
            if not self._check_for_captcha():
                logger.warning("CAPTCHA detected and could not be solved")
                return False
            
            # Check for proxy block
            if self._check_for_proxy_block():
                return False
            
            # Verify login success
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(@class, 'user')]"))
                )
                self.has_session_cookies = True
                logger.info("Login successful")
                return True
            except TimeoutException:
                # Check for error messages
                try:
                    error_msg = self.driver.find_element(By.XPATH, "//div[contains(@class, 'error')]").text
                    logger.warning(f"Login failed: {error_msg}")
                except NoSuchElementException:
                    logger.warning("Login failed for unknown reason")
                
                self._take_screenshot("login_failed")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            self._take_screenshot("login_error")
            return False
    
    def _type_like_human(self, element: Any, text: str) -> None:
        """Type text into an element with random delays to simulate human typing.
        
        Args:
            element: WebElement to type into
            text: Text to type
        """
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.2))
    
    def check_reddit_login(self) -> bool:
        """Check if currently logged in to Reddit.
        
        Returns:
            True if logged in, False otherwise
        """
        if not self.driver:
            return False
        
        try:
            self.driver.get("https://www.reddit.com/")
            self._random_wait()
            
            # Check for elements that indicate being logged in
            logged_in_indicators = [
                "//span[contains(@class, 'user')]",
                "//button[contains(@aria-label, 'Create')]",
                "//a[contains(@href, '/user/')]"
            ]
            
            for indicator in logged_in_indicators:
                try:
                    element = self.driver.find_element(By.XPATH, indicator)
                    if element:
                        logger.info("Confirmed logged in status")
                        return True
                except NoSuchElementException:
                    continue
            
            logger.info("Not currently logged in")
            return False
            
        except Exception as e:
            logger.warning(f"Error checking login status: {str(e)}")
            return False
    
    def set_cookies(self, cookies: List[Dict]) -> None:
        """Set browser cookies from a saved session.
        
        Args:
            cookies: List of cookie dictionaries
        """
        if not self.driver:
            self._initialize_browser()
        
        logger.info("Setting saved cookies")
        
        try:
            # Navigate to Reddit domain first (required for setting cookies)
            self.driver.get("https://www.reddit.com")
            self._random_wait()
            
            # Clear existing cookies
            self.driver.delete_all_cookies()
            
            # Set each cookie
            for cookie in cookies:
                try:
                    # Ensure cookie has required fields
                    if "name" in cookie and "value" in cookie:
                        # Remove problematic fields if present
                        cookie_dict = {k: v for k, v in cookie.items() 
                                     if k in ["name", "value", "domain", "path", "secure", "expiry"]}
                        self.driver.add_cookie(cookie_dict)
                except Exception as e:
                    logger.warning(f"Error setting cookie {cookie.get('name')}: {str(e)}")
            
            # Refresh page to apply cookies
            self.driver.refresh()
            self._random_wait()
            
        except Exception as e:
            logger.error(f"Error setting cookies: {str(e)}")
    
    def get_cookies(self) -> List[Dict]:
        """Get current browser cookies.
        
        Returns:
            List of cookie dictionaries
        """
        if not self.driver:
            return []
        
        try:
            return self.driver.get_cookies()
        except Exception as e:
            logger.error(f"Error getting cookies: {str(e)}")
            return []
    
    def scrape_reddit_profile(self, username: str) -> Dict[str, Any]:
        """Scrape profile data for a Reddit user.
        
        Args:
            username: Reddit username
            
        Returns:
            Dict containing profile data
        """
        if not self.driver:
            self._initialize_browser()
        
        logger.info(f"Scraping profile for user: {username}")
        profile_url = f"https://www.reddit.com/user/{username}"
        
        try:
            self.driver.get(profile_url)
            self._random_wait(2.0, 4.0)
            
            # Check for "profile not found" or "account suspended" indicators
            not_found_selectors = [
                "//div[contains(text(), 'page not found')]",
                "//div[contains(text(), 'account has been suspended')]"
            ]
            
            for selector in not_found_selectors:
                try:
                    not_found = self.driver.find_element(By.XPATH, selector)
                    if not_found:
                        logger.warning(f"Profile not available: {not_found.text}")
                        return {
                            "error": "profile_not_available",
                            "error_message": not_found.text,
                            "karma": 0,
                            "account_age_days": 0,
                            "has_verified_email": False
                        }
                except NoSuchElementException:
                    pass
            
            # Extract karma
            karma = 0
            try:
                # First attempt with newer Reddit UI
                karma_element = self.driver.find_element(
                    By.XPATH, "//span[contains(text(), 'karma')]/preceding-sibling::span"
                )
                karma_text = karma_element.text.replace(",", "")
                karma = int(karma_text)
            except (NoSuchElementException, ValueError):
                try:
                    # Second attempt with alternative layout
                    karma_elements = self.driver.find_elements(
                        By.XPATH, "//div[contains(@class, 'karma')]//span"
                    )
                    for element in karma_elements:
                        try:
                            karma_value = element.text.replace(",", "").replace("karma", "").strip()
                            karma += int(karma_value)
                        except ValueError:
                            continue
                except Exception:
                    logger.warning("Could not extract karma value")
            
            # Extract account age
            account_age_days = 0
            try:
                age_element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'ago')]"))
                )
                age_text = age_element.text
                
                # Parse age text (e.g., "3 years ago", "2 months ago", "5 days ago")
                if "year" in age_text:
                    years = int(age_text.split()[0])
                    account_age_days = years * 365
                elif "month" in age_text:
                    months = int(age_text.split()[0])
                    account_age_days = months * 30
                elif "day" in age_text:
                    account_age_days = int(age_text.split()[0])
                elif "hour" in age_text or "minute" in age_text:
                    account_age_days = 0
            except (TimeoutException, NoSuchElementException, ValueError):
                logger.warning("Could not extract account age")
            
            # Check for verified email badge
            has_verified_email = False
            try:
                email_badge = self.driver.find_element(
                    By.XPATH, "//i[contains(@class, 'email-verified')]"
                )
                has_verified_email = email_badge is not None
            except NoSuchElementException:
                # Try alternative indicator
                try:
                    email_text = self.driver.find_element(
                        By.XPATH, "//span[contains(text(), 'Email Verified')]"
                    )
                    has_verified_email = email_text is not None
                except NoSuchElementException:
                    pass
            
            # Extract avatar URL if available
            avatar_url = None
            try:
                avatar_img = self.driver.find_element(
                    By.XPATH, "//img[contains(@alt, 'User avatar')]"
                )
                avatar_url = avatar_img.get_attribute("src")
            except NoSuchElementException:
                logger.debug("No avatar found")
            
            # Check for premium status
            is_premium = False
            try:
                premium_badge = self.driver.find_element(
                    By.XPATH, "//i[contains(@class, 'premium')] | //span[contains(text(), 'Premium')]"
                )
                is_premium = premium_badge is not None
            except NoSuchElementException:
                pass
            
            # Extract badges/awards
            badges = []
            try:
                badge_elements = self.driver.find_elements(
                    By.XPATH, "//span[contains(@class, 'award-name')] | //span[contains(@class, 'badge')]"
                )
                for badge in badge_elements:
                    badges.append(badge.text.strip())
            except Exception:
                pass
            
            profile_data = {
                "karma": karma,
                "account_age_days": account_age_days,
                "has_verified_email": has_verified_email,
                "avatar_url": avatar_url,
                "is_premium": is_premium,
                "badges": badges
            }
            
            logger.info(f"Profile data scraped: {json.dumps(profile_data)}")
            return profile_data
            
        except Exception as e:
            logger.error(f"Error scraping profile: {str(e)}")
            self._take_screenshot(f"profile_error_{username}")
            return {
                "error": "scraping_failed",
                "error_message": str(e),
                "karma": 0,
                "account_age_days": 0,
                "has_verified_email": False
            }
    
    def trigger_password_reset(self, username: str) -> bool:
        """Trigger a password reset email for a Reddit account.
        
        Args:
            username: Reddit username
            
        Returns:
            True if reset triggered successfully, False otherwise
        """
        if not self.driver:
            self._initialize_browser()
        
        logger.info(f"Triggering password reset for: {username}")
        
        try:
            # Navigate to password reset page
            self.driver.get("https://www.reddit.com/password")
            self._random_wait(2.0, 3.0)
            
            # Enter username
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "username"))
            )
            username_field.clear()
            self._type_like_human(username_field, username)
            
            # Click submit button
            submit_button = self.driver.find_element(
                By.XPATH, "//button[@type='submit'] | //button[contains(text(), 'reset')]"
            )
            submit_button.click()
            self._random_wait(2.0, 3.0)
            
            # Check for confirmation message
            try:
                confirmation = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.XPATH, "//div[contains(text(), 'email') and contains(text(), 'sent')]"
                    ))
                )
                if confirmation:
                    logger.info("Password reset email sent successfully")
                    return True
            except TimeoutException:
                logger.warning("No confirmation message found for password reset")
                self._take_screenshot("reset_no_confirmation")
            
            return False
            
        except Exception as e:
            logger.error(f"Error triggering password reset: {str(e)}")
            self._take_screenshot("reset_error")
            return False
    
    def get_user_content_urls(self, username: str, limit: int = 10) -> List[str]:
        """Get URLs for the user's recent posts and comments.
        
        Args:
            username: Reddit username
            limit: Maximum number of URLs to collect
            
        Returns:
            List of content URLs
        """
        if not self.driver:
            self._initialize_browser()
        
        logger.info(f"Collecting content URLs for user: {username} (limit: {limit})")
        urls = []
        
        try:
            # Navigate to user's profile
            self.driver.get(f"https://www.reddit.com/user/{username}")
            self._random_wait(2.0, 4.0)
            
            # Scroll a few times to load more content
            scroll_attempts = min(5, (limit // 5) + 1)
            for _ in range(scroll_attempts):
                self.driver.execute_script("window.scrollBy(0, 1000)")
                self._random_wait(1.0, 2.0)
            
            # Find post and comment links
            content_elements = self.driver.find_elements(
                By.XPATH, "//a[contains(@data-click-id, 'body') or contains(@data-click-id, 'comments')]"
            )
            
            for element in content_elements:
                try:
                    url = element.get_attribute("href")
                    if url and "reddit.com" in url and url not in urls:
                        urls.append(url)
                        if len(urls) >= limit:
                            break
                except (StaleElementReferenceException, Exception) as e:
                    logger.debug(f"Error extracting URL: {str(e)}")
            
            logger.info(f"Collected {len(urls)} content URLs")
            return urls
            
        except Exception as e:
            logger.error(f"Error collecting content URLs: {str(e)}")
            return urls
    
    def extract_content_from_url(self, url: str) -> Optional[str]:
        """Extract content text from a Reddit post or comment URL.
        
        Args:
            url: Reddit content URL
            
        Returns:
            Content text or None if extraction failed
        """
        if not self.driver:
            self._initialize_browser()
        
        logger.info(f"Extracting content from URL: {url}")
        
        try:
            self.driver.get(url)
            self._random_wait(2.0, 4.0)
            
            # Check if it's a post or comment
            if "/comments/" in url:
                # Try to find post content
                try:
                    post_element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((
                            By.XPATH, "//div[@data-test-id='post-content'] | //div[contains(@class, 'Post__content')]"
                        ))
                    )
                    return post_element.text.strip()
                except TimeoutException:
                    # Try to find comment content
                    try:
                        comment_element = self.driver.find_element(
                            By.XPATH, "//div[contains(@class, 'Comment__body')]"
                        )
                        return comment_element.text.strip()
                    except NoSuchElementException:
                        logger.warning(f"Could not find content in {url}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting content: {str(e)}")
            return None
    
    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser closed")
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")
            finally:
                self.driver = None
