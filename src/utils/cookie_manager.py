"""Encrypted cookie storage using Fernet."""

import os
import json
import base64
import logging
from typing import Dict, Optional, Any, List
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class CookieManager:
    """
    Secure cookie management with encryption for browser session persistence.
    Uses Fernet symmetric encryption to protect cookie data.
    """
    
    def __init__(self, encryption_key: Optional[str] = None, salt: Optional[bytes] = None):
        """
        Initialize cookie manager with encryption settings.
        
        Args:
            encryption_key: Optional encryption key (generated if not provided)
            salt: Optional salt for key derivation (generated if not provided)
        """
        self.cookies_dir = Path("cookies")
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        
        # Use provided key or generate from environment variable or create new one
        self.encryption_key = (
            encryption_key or 
            os.environ.get("COOKIE_ENCRYPTION_KEY") or 
            self._generate_key()
        )
        
        # Salt for key derivation
        self.salt = salt or os.urandom(16)
        
        # Initialize Fernet cipher
        self.fernet = self._setup_fernet()
    
    def _generate_key(self) -> str:
        """
        Generate a new encryption key.
        
        Returns:
            Base64 encoded encryption key
        """
        key = Fernet.generate_key()
        logger.warning("Generated new encryption key - cookies from previous sessions won't be readable")
        return key.decode()
    
    def _setup_fernet(self) -> Fernet:
        """
        Set up Fernet cipher with derived key.
        
        Returns:
            Configured Fernet cipher
        """
        # Convert string key to bytes if needed
        key_bytes = (
            self.encryption_key.encode() 
            if isinstance(self.encryption_key, str) 
            else self.encryption_key
        )
        
        # Derive a secure key using PBKDF2
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(key_bytes))
        
        return Fernet(derived_key)
    
    def save_cookies(self, driver: Any, filepath: str) -> bool:
        """
        Save browser cookies with encryption.
        
        Args:
            driver: Selenium WebDriver instance
            filepath: Path to save cookies
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create directory if it doesn't exist
            cookie_path = Path(filepath)
            cookie_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get cookies from browser
            cookies = driver.get_cookies()
            if not cookies:
                logger.warning(f"No cookies to save from driver")
                return False
            
            # Encrypt cookies
            cookies_json = json.dumps(cookies)
            encrypted_data = self.fernet.encrypt(cookies_json.encode())
            
            # Save to file
            with open(cookie_path, 'wb') as f:
                f.write(encrypted_data)
                
            logger.info(f"Saved {len(cookies)} cookies to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save cookies: {str(e)}")
            return False
    
    def load_cookies(self, driver: Any, filepath: str) -> bool:
        """
        Load encrypted cookies into browser.
        
        Args:
            driver: Selenium WebDriver instance
            filepath: Path to cookie file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cookie_path = Path(filepath)
            if not cookie_path.exists():
                logger.warning(f"Cookie file not found: {filepath}")
                return False
            
            # Read and decrypt cookies
            with open(cookie_path, 'rb') as f:
                encrypted_data = f.read()
                
            try:
                decrypted_data = self.fernet.decrypt(encrypted_data)
                cookies = json.loads(decrypted_data)
            except InvalidToken:
                logger.error("Failed to decrypt cookies - encryption key mismatch")
                return False
            
            # Set a dummy URL before adding cookies
            current_url = driver.current_url
            if current_url == "data:,":  # Empty page
                driver.get("https://www.reddit.com")
            
            # Add cookies to browser
            for cookie in cookies:
                # Skip cookies that might cause issues
                if "expiry" in cookie:
                    # Convert expiry to int if needed
                    cookie["expiry"] = int(cookie["expiry"])
                
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Couldn't set cookie {cookie.get('name')}: {str(e)}")
            
            logger.info(f"Loaded {len(cookies)} cookies from {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load cookies: {str(e)}")
            return False
    
    def delete_cookies(self, filepath: str) -> bool:
        """
        Delete saved cookie file.
        
        Args:
            filepath: Path to cookie file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cookie_path = Path(filepath)
            if cookie_path.exists():
                cookie_path.unlink()
                logger.info(f"Deleted cookie file: {filepath}")
                return True
            else:
                logger.warning(f"Cookie file not found: {filepath}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete cookies: {str(e)}")
            return False
    
    def list_saved_cookies(self) -> List[str]:
        """
        List all saved cookie files.
        
        Returns:
            List of cookie filenames
        """
        try:
            return [f.name for f in self.cookies_dir.glob("*.json")]
        except Exception as e:
            logger.error(f"Failed to list cookies: {str(e)}")
            return []
    
    def clear_all_cookies(self) -> int:
        """
        Delete all saved cookie files.
        
        Returns:
            Number of files deleted
        """
        try:
            count = 0
            for cookie_file in self.cookies_dir.glob("*.json"):
                cookie_file.unlink()
                count += 1
                
            logger.info(f"Deleted {count} cookie files")
            return count
            
        except Exception as e:
            logger.error(f"Failed to clear cookies: {str(e)}")
            return 0
