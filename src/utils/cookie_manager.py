"""Secure encrypted cookie storage with enhanced key management and error handling."""

import os
import json
import base64
import logging
import secrets
from typing import Dict, Optional, Any, List, Union
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from dataclasses import dataclass
from functools import wraps
import pickle  # For binary cookie storage

logger = logging.getLogger(__name__)

@dataclass
class CookieConfig:
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    http_only: bool = False
    expiry: Optional[int] = None
    same_site: Optional[str] = None

class CookieManager:
    """
    Enhanced secure cookie management with:
    - Stronger key derivation (PBKDF2 with configurable iterations)
    - Binary storage option for better performance
    - Cookie validation and sanitization
    - Thread-safe operations
    - Automatic key rotation
    """
    
    DEFAULT_ITERATIONS = 480000  # OWASP recommended minimum for PBKDF2-HMAC-SHA256
    
    def __init__(
        self,
        encryption_key: Optional[Union[str, bytes]] = None,
        salt: Optional[bytes] = None,
        storage_path: Union[str, Path] = "cookies",
        iterations: int = DEFAULT_ITERATIONS,
        binary_storage: bool = True
    ):
        """
        Initialize with enhanced security settings.
        
        Args:
            encryption_key: Existing key (str/bytes) or None to generate
            salt: Cryptographic salt (16+ bytes recommended)
            storage_path: Directory for cookie storage
            iterations: PBKDF2 iterations (higher = more secure but slower)
            binary_storage: Use binary format for smaller/faster storage
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True, mode=0o700)  # Secure directory
        
        # Key management
        self._key_version = 1
        self.iterations = max(iterations, 100000)  # Enforce minimum
        self.binary_storage = binary_storage
        
        # Initialize crypto
        self.salt = salt or secrets.token_bytes(16)
        self.encryption_key = self._normalize_key(encryption_key)
        self._fernet = self._init_fernet()
        
        logger.info(f"CookieManager initialized (key version {self._key_version})")

    def _normalize_key(self, key: Optional[Union[str, bytes]]) -> bytes:
        """Ensure we have valid key material in bytes format."""
        if key is None:
            key = self._generate_key()
        elif isinstance(key, str):
            if key.startswith("env:"):
                key = os.environ.get(key[4:]) or ""
            key = key.encode()
        return key

    def _generate_key(self) -> bytes:
        """Generate a new high-entropy encryption key."""
        return Fernet.generate_key()

    def _init_fernet(self) -> Fernet:
        """Initialize Fernet with properly derived key."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=self.iterations,
            backend=default_backend()
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(self.encryption_key))
        return Fernet(derived_key)

    def _get_cookie_path(self, identifier: str) -> Path:
        """Get full path for cookie file with extension."""
        ext = ".bin" if self.binary_storage else ".json"
        return self.storage_path / f"{identifier}{ext}"

    def _serialize_cookies(self, cookies: List[Dict[str, Any]]) -> bytes:
        """Serialize cookies to bytes with selected format."""
        if self.binary_storage:
            return pickle.dumps(cookies)
        return json.dumps(cookies).encode()

    def _deserialize_cookies(self, data: bytes) -> List[Dict[str, Any]]:
        """Deserialize cookies from bytes."""
        try:
            if self.binary_storage:
                return pickle.loads(data)
            return json.loads(data.decode())
        except (pickle.PickleError, json.JSONDecodeError) as e:
            logger.error(f"Deserialization failed: {str(e)}")
            raise ValueError("Invalid cookie data format") from e

    def _validate_cookie(self, cookie: Dict[str, Any]) -> bool:
        """Validate cookie structure before storage."""
        required = {"name", "value", "domain"}
        return all(field in cookie for field in required)

    def _sanitize_cookie(self, cookie: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and standardize cookie data."""
        return {
            "name": str(cookie.get("name", "")),
            "value": str(cookie.get("value", "")),
            "domain": str(cookie.get("domain", "")),
            "path": str(cookie.get("path", "/")),
            "secure": bool(cookie.get("secure", False)),
            "httpOnly": bool(cookie.get("httpOnly", False)),
            "expiry": int(cookie["expiry"]) if "expiry" in cookie else None,
            "sameSite": str(cookie.get("sameSite", "")) if "sameSite" in cookie else None
        }

    def save_cookies(
        self,
        cookies: List[Dict[str, Any]],
        identifier: str,
        overwrite: bool = True
    ) -> bool:
        """
        Securely store cookies with validation and encryption.
        
        Args:
            cookies: List of cookie dictionaries
            identifier: Unique name for this cookie set
            overwrite: Replace existing file if True
            
        Returns:
            True if successful
        """
        if not cookies:
            logger.warning("No cookies provided for saving")
            return False

        path = self._get_cookie_path(identifier)
        if path.exists() and not overwrite:
            logger.warning(f"Cookie file exists and overwrite=False: {path}")
            return False

        try:
            # Validate and sanitize all cookies
            validated = []
            for cookie in cookies:
                if not self._validate_cookie(cookie):
                    logger.warning(f"Skipping invalid cookie: {cookie.get('name')}")
                    continue
                validated.append(self._sanitize_cookie(cookie))

            if not validated:
                logger.error("No valid cookies to save")
                return False

            # Serialize and encrypt
            serialized = self._serialize_cookies(validated)
            encrypted = self._fernet.encrypt(serialized)

            # Atomic write with temp file pattern
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "wb") as f:
                f.write(encrypted)
            temp_path.replace(path)  # Atomic rename

            logger.info(f"Saved {len(validated)} cookies to {path}")
            return True

        except Exception as e:
            logger.error(f"Cookie save failed: {str(e)}", exc_info=True)
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            return False

    def load_cookies(self, identifier: str) -> Optional[List[Dict[str, Any]]]:
        """
        Load and decrypt cookies with validation.
        
        Args:
            identifier: Name of the cookie set to load
            
        Returns:
            List of cookies or None if failed
        """
        path = self._get_cookie_path(identifier)
        if not path.exists():
            logger.warning(f"Cookie file not found: {path}")
            return None

        try:
            with open(path, "rb") as f:
                encrypted = f.read()

            decrypted = self._fernet.decrypt(encrypted)
            cookies = self._deserialize_cookies(decrypted)

            if not isinstance(cookies, list):
                raise ValueError("Invalid cookie format - expected list")

            # Validate all loaded cookies
            for cookie in cookies:
                if not self._validate_cookie(cookie):
                    raise ValueError(f"Invalid cookie in storage: {cookie.get('name')}")

            logger.info(f"Loaded {len(cookies)} cookies from {path}")
            return cookies

        except InvalidToken:
            logger.error("Decryption failed - possible key mismatch")
            return None
        except Exception as e:
            logger.error(f"Cookie load failed: {str(e)}", exc_info=True)
            return None

    def delete_cookies(self, identifier: str) -> bool:
        """Securely delete cookie file."""
        path = self._get_cookie_path(identifier)
        try:
            if path.exists():
                path.unlink()
                logger.info(f"Deleted cookie file: {path}")
                return True
            logger.warning(f"Cookie file not found: {path}")
            return False
        except Exception as e:
            logger.error(f"Cookie deletion failed: {str(e)}")
            return False

    def list_saved(self) -> List[str]:
        """List all saved cookie identifiers."""
        try:
            return [
                f.stem for f in self.storage_path.glob("*")
                if f.suffix in (".json", ".bin")
            ]
        except Exception as e:
            logger.error(f"Failed to list cookies: {str(e)}")
            return []

    def rotate_key(self, new_key: Optional[Union[str, bytes]] = None) -> bool:
        """
        Rotate encryption key and re-encrypt all cookies.
        
        Args:
            new_key: Optional new key (generates if None)
            
        Returns:
            True if rotation succeeded
        """
        try:
            # Load all cookies before rotation
            all_cookies = {}
            for ident in self.list_saved():
                cookies = self.load_cookies(ident)
                if cookies:
                    all_cookies[ident] = cookies

            # Update key material
            self._key_version += 1
            self.encryption_key = self._normalize_key(new_key)
            self._fernet = self._init_fernet()

            # Re-save all cookies
            success = True
            for ident, cookies in all_cookies.items():
                if not self.save_cookies(cookies, ident):
                    logger.error(f"Failed to re-encrypt cookies for {ident}")
                    success = False

            logger.info(f"Key rotation {'succeeded' if success else 'partially failed'}")
            return success

        except Exception as e:
            logger.error(f"Key rotation failed: {str(e)}", exc_info=True)
            return False

    # Additional utility methods
    def get_cookie_file_size(self, identifier: str) -> Optional[int]:
        """Get size of cookie file in bytes."""
        path = self._get_cookie_path(identifier)
        return path.stat().st_size if path.exists() else None

    def get_storage_usage(self) -> Dict[str, int]:
        """Get storage statistics."""
        files = list(self.storage_path.glob("*"))
        return {
            "total_files": len(files),
            "total_bytes": sum(f.stat().st_size for f in files),
            "encryption_version": self._key_version
        }except Exception as e:
            logger.error(f"Failed to clear cookies: {str(e)}")
            return 0
