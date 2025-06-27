"""
Undetectable Chrome driver manager for web automation with advanced anti-detection measures.
"""

import os
import time
import logging
import random
import platform
import zipfile
import json
from typing import Dict, Optional, Any, List, Tuple
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    WebDriverException
)
import undetected_chromedriver as uc
from fake_useragent import UserAgent

from ..utils.proxy_rotator import ProxyRotator
from ..utils.cookie_manager import CookieManager

logger = logging.getLogger(__name__)

class BrowserEngine:
    """
    Manages stealthy Chrome browser sessions with:
    - Randomized fingerprinting
    - Proxy rotation
    - CAPTCHA handling
    - Human-like interaction patterns
    """
    
    def __init__(self, config: Dict[str, Any], proxy_rotator: Optional[ProxyRotator] = None):
        """
        Initialize browser engine with configuration.
        
        Args:
            config: {
                "user_agent": "optional custom UA",
                "headless": False,
                "stealth_level": 3,  # 1-3
                "timeouts": {
                    "page_load": 30,
                    "element": 10,
                    "captcha": 45
                },
                "chrome_version": 119  # Optional
            }
            proxy_rotator: ProxyRotator instance
        """
        self.config = config
        self.proxy_rotator = proxy_rotator
        self.driver = None
        self.profile_dir = None
        self.cookie_manager = CookieManager()
        
        # Timeout configuration
        self.timeouts = {
            "page_load": 30,
            "element": 10,
            "captcha": 45,
            **config.get("timeouts", {})
        }
        
        # Anti-detection settings
        self.stealth_level = config.get("stealth_level", 3)
        self.headless = config.get("headless", False)
        self.chrome_version = config.get("chrome_version")
        
        # Initialize random user agent if not specified
        self.user_agent = config.get("user_agent") or UserAgent().chrome
        
    def __enter__(self):
        self.initialize()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        
    def initialize(self) -> None:
        """Initialize a stealthy browser session."""
        if self.driver:
            logger.warning("Browser already initialized")
            return
            
        try:
            # Create isolated profile directory
            self.profile_dir = self._create_profile_dir()
            
            # Configure Chrome options
            options = self._configure_options()
            
            # Initialize undetected Chrome
            self.driver = uc.Chrome(
                options=options,
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                version_main=self.chrome_version,
                patcher_force_close=True,
                suppress_welcome=True
            )
            
            # Configure timeouts
            self.driver.set_page_load_timeout(self.timeouts["page_load"])
            self.driver.implicitly_wait(self.timeouts["element"])
            
            # Apply anti-detection measures
            self._apply_fingerprint_spoofing()
            self._apply_stealth_techniques()
            
            logger.info("Browser initialized with stealth level %d", self.stealth_level)
            
        except Exception as e:
            logger.error("Browser initialization failed: %s", str(e))
            self.close()
            raise
            
    def _create_profile_dir(self) -> Path:
        """Create isolated browser profile directory."""
        profile_dir = Path(f"tmp/profiles/{int(time.time())}")
        profile_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Created profile directory: %s", profile_dir)
        return profile_dir
        
    def _configure_options(self) -> uc.ChromeOptions:
        """Configure Chrome options with anti-detection settings."""
        options = uc.ChromeOptions()
        
        # Standard options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=en-US,en;q=0.9")
        options.add_argument(f"--user-agent={self.user_agent}")
        
        # Platform-specific optimizations
        if platform.system() == "Linux":
            options.add_argument("--disable-setuid-sandbox")
            
        # Proxy configuration
        if self.proxy_rotator:
            proxy = self.proxy_rotator.get_proxy()
            if proxy:
                options.add_argument(f"--proxy-server={proxy['http']}")
                logger.info("Using proxy: %s", proxy['http'])
        
        # Headless-specific options
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            
        # Stealth level specific options
        if self.stealth_level >= 2:
            options.add_argument("--disable-web-security")
            options.add_argument("--allow-running-insecure-content")
            
        if self.stealth_level >= 3:
            options.add_argument("--disable-bundled-ppapi-flash")
            options.add_argument("--disable-logging")
            
        return options
        
    def _apply_fingerprint_spoofing(self) -> None:
        """Modify browser fingerprint to avoid detection."""
        scripts = [
            # Basic webdriver masking
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });
            """,
            
            # Plugin spoofing
            """
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            """,
            
            # Language spoofing
            """
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
            """
        ]
        
        # Additional stealth measures for higher levels
        if self.stealth_level >= 2:
            scripts.extend([
                # Screen resolution spoofing
                """
                Object.defineProperty(screen, 'width', {
                    get: () => 1920 + Math.floor(Math.random() * 100)
                });
                Object.defineProperty(screen, 'height', {
                    get: () => 1080 + Math.floor(Math.random() * 100)
                });
                """,
                
                # Timezone spoofing
                """
                Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {
                    get: function() {
                        return () => {
                            const options = Reflect.apply(
                                Intl.DateTimeFormat.prototype.resolvedOptions, 
                                this, 
                                []
                            );
                            options.timeZone = 'America/New_York';
                            return options;
                        };
                    }
                });
                """
            ])
            
        if self.stealth_level >= 3:
            scripts.extend([
                # Advanced API spoofing
                """
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ? 
                    Promise.resolve({ state: 'denied' }) :
                    originalQuery(parameters)
                );
                """
            ])
            
        for script in scripts:
            try:
                self.driver.execute_script(script)
            except Exception as e:
                logger.debug("Fingerprint script failed: %s", str(e))
                
    def _apply_stealth_techniques(self) -> None:
        """Apply additional stealth techniques based on configuration."""
        # Randomize mouse movement patterns
        self.driver.execute_script("""
            window.randomMouseMovement = true;
            document.addEventListener('mousemove', (e) => {
                if (window.randomMouseMovement) {
                    e.preventDefault();
                    const newEvent = new MouseEvent('mousemove', {
                        clientX: e.clientX + Math.random() * 10 - 5,
                        clientY: e.clientY + Math.random() * 10 - 5
                    });
                    e.target.dispatchEvent(newEvent);
                }
            });
        """)
        
        # Disable WebRTC leak (for proxy users)
        if self.proxy_rotator:
            self.driver.execute_script("""
                const originalRTCPeerConnection = window.RTCPeerConnection;
                window.RTCPeerConnection = function(...args) {
                    const pc = new originalRTCPeerConnection(...args);
                    pc.createDataChannel('');
                    pc.close();
                    return new originalRTCPeerConnection(...args);
                };
            """)
            
    def close(self) -> None:
        """Cleanly close the browser session."""
        if self.driver:
            try:
                # Save cookies before closing
                if hasattr(self, 'profile_dir'):
                    self.cookie_manager.save_cookies(
                        self.driver,
                        f"cookies/{self.profile_dir.name}.json"
                    )
                    
                self.driver.quit()
                logger.info("Browser session closed")
            except Exception as e:
                logger.error("Error closing browser: %s", str(e))
            finally:
                self.driver = None
                
        # Clean up profile directory
        if hasattr(self, 'profile_dir') and self.profile_dir.exists():
            try:
                import shutil
                shutil.rmtree(self.profile_dir)
                logger.debug("Removed profile directory: %s", self.profile_dir)
            except Exception as e:
                logger.error("Failed to remove profile: %s", str(e))
                
    def load_cookies(self, username: str) -> bool:
        """Load cookies for a specific username if available."""
        cookie_file = Path(f"cookies/{username}.json")
        if cookie_file.exists():
            try:
                self.cookie_manager.load_cookies(self.driver, str(cookie_file))
                logger.info("Loaded cookies for %s", username)
                return True
            except Exception as e:
                logger.warning("Failed to load cookies: %s", str(e))
        return False
        
    def login_to_reddit(self, username: str, password: str) -> bool:
        """
        Perform human-like Reddit login with CAPTCHA handling.
        
        Returns:
            bool: True if login successful
        """
        if not self.driver:
            self.initialize()
            
        try:
            # Try loading existing cookies first
            if self.load_cookies(username):
                self.driver.get("https://www.reddit.com")
                if self._is_logged_in(username):
                    logger.info("Logged in via cookies")
                    return True
                    
            # Navigate to login page
            self.driver.get("https://www.reddit.com/login")
            self._random_delay(1, 2)
            
            # Fill login form with human-like behavior
            self._human_like_typing(By.ID, "loginUsername", username)
            self._random_delay(0.5, 1.5)
            self._human_like_typing(By.ID, "loginPassword", password)
            self._random_delay(0.3, 0.8)
            
            # Click login button
            self._click_element(By.CSS_SELECTOR, "button[type=submit]")
            
            # Handle CAPTCHA if present
            if self._check_for_captcha():
                logger.warning("CAPTCHA detected - waiting for resolution")
                if not self._handle_captcha():
                    return False
                    
            # Verify login success
            if self._is_logged_in(username):
                logger.info("Login successful for %s", username)
                return True
                
            logger.error("Login failed - unknown reason")
            return False
            
        except Exception as e:
            logger.error("Login failed: %s", str(e))
            return False
            
    def _is_logged_in(self, username: str) -> bool:
        """Check if we're logged in as the specified user."""
        try:
            self.driver.get("https://www.reddit.com")
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "USER_DROPDOWN_ID"))
            )
            return username.lower() in self.driver.page_source.lower()
        except:
            return False
            
    def _check_for_captcha(self) -> bool:
        """Detect CAPTCHA challenges on current page."""
        captcha_selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            ".captcha-container",
            "#captcha-challenge"
        ]
        
        for selector in captcha_selectors:
            try:
                if self.driver.find_elements(By.CSS_SELECTOR, selector):
                    return True
            except:
                continue
        return False
        
    def _handle_captcha(self) -> bool:
        """Handle CAPTCHA challenge with timeout."""
        start_time = time.time()
        timeout = self.timeouts["captcha"]
        
        logger.info("Waiting for CAPTCHA resolution (timeout: %ds)", timeout)
        
        while time.time() - start_time < timeout:
            if not self._check_for_captcha():
                return True
            time.sleep(1)
            
        logger.warning("CAPTCHA resolution timed out")
        return False
        
    def extract_account_info(self, username: str) -> Dict[str, Any]:
        """
        Extract detailed account information from Reddit profile.
        
        Returns:
            Dictionary containing account metrics
        """
        if not self.driver:
            self.initialize()
            
        info = {
            "username": username,
            "exists": True,
            "karma": 0,
            "age_days": 0,
            "verified": False,
            "moderator": False,
            "trophies": [],
            "communities": []
        }
        
        try:
            # Navigate to profile
            self.driver.get(f"https://www.reddit.com/user/{username}")
            self._random_delay(2, 4)
            
            # Check if user exists
            if "nobody on Reddit goes by that name" in self.driver.page_source:
                info["exists"] = False
                return info
                
            # Extract karma points
            try:
                karma_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "._3XFx6CfPlg-4Usgxm0gK8R")
                if karma_elements:
                    info["karma"] = self._parse_karma(karma_elements[0].text)
            except:
                pass
                
            # Extract account age
            try:
                cake_day = self.driver.find_element(
                    By.CSS_SELECTOR, "._2VF2J19pUIMSLJFky-7PEI").text
                info["age_days"] = self._parse_cake_day(cake_day)
            except:
                pass
                
            # Extract trophies and badges
            try:
                trophy_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "._2Gq3CSlw6ertQlLjXyMFaM")
                info["trophies"] = [t.text for t in trophy_elements if t.text]
                info["verified"] = any("Verified" in t for t in info["trophies"])
                info["moderator"] = any("Moderator" in t for t in info["trophies"])
            except:
                pass
                
            # Extract active communities
            try:
                self.driver.get(f"https://www.reddit.com/user/{username}/communities")
                self._random_delay(2, 3)
                
                community_elements = self.driver.find_elements(
                    By.CSS_SELECTOR, "._3q9sJ7I9Ep1QkC8dOK4wxD")
                info["communities"] = [c.text for c in community_elements[:10]]
            except:
                pass
                
        except Exception as e:
            logger.error("Account info extraction failed: %s", str(e))
            
        return info
        
    def _parse_karma(self, karma_text: str) -> int:
        """Parse karma string into integer."""
        multipliers = {
            'k': 1000,
            'm': 1000000
        }
        
        karma_text = karma_text.lower().replace(',', '')
        if karma_text[-1] in multipliers:
            return int(float(karma_text[:-1]) * multipliers[karma_text[-1]])
        return int(float(karma_text))
        
    def _parse_cake_day(self, cake_day_text: str) -> int:
        """Calculate account age in days from cake day."""
        from datetime import datetime
        
        try:
            formats = ["%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y"]
            for fmt in formats:
                try:
                    created = datetime.strptime(cake_day_text, fmt)
                    return (datetime.now() - created).days
                except ValueError:
                    continue
        except:
            pass
        return 0
        
    def _human_like_typing(self, by: str, selector: str, text: str) -> None:
        """Type text with human-like delays."""
        element = WebDriverWait(self.driver, self.timeouts["element"]).until(
            EC.presence_of_element_located((by, selector))
        )
        
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
            
    def _click_element(self, by: str, selector: str) -> None:
        """Click element with human-like delay."""
        element = WebDriverWait(self.driver, self.timeouts["element"]).until(
            EC.element_to_be_clickable((by, selector))
        )
        
        self._random_delay(0.2, 0.5)
        element.click()
        
    def _random_delay(self, min_sec: float, max_sec: float) -> None:
        """Wait random interval to mimic human behavior."""
        time.sleep(random.uniform(min_sec, max_sec))
