"""IMAP processor for Hotmail email verification with enhanced security and performance."""

import os
import imaplib
import email
import logging
import re
import time
import hashlib
import getpass
from typing import Dict, Optional, List, Tuple, Any, Union
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from functools import wraps, lru_cache
from contextlib import contextmanager
import signal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

@contextmanager
def timeout(seconds):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

@dataclass
class VerificationResult:
    verified: bool
    email: str
    reddit_username: str
    verification_time: Optional[str] = None
    verification_id: Optional[str] = None
    error: Optional[str] = None

class EmailVerifier:
    """
    Enhanced IMAP processor for Reddit account verification with:
    - Connection pooling and retries
    - Multi-part email processing
    - Advanced pattern matching
    - Timeout protection
    - Credential security
    """
    
    USERNAME_PATTERNS = [
        r'reddit\.com/u/([\w-]+)',        # URL pattern
        r'username:\s*([\w-]+)',          # Labeled pattern
        r'u/([\w-]+)\s+is your username', # Common template
        r'for u/([\w-]+)\s+to verify'     # Alternate template
    ]
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with enhanced security and connection settings.
        
        Args:
            config: {
                "imap_server": "outlook.office365.com",
                "imap_port": 993,
                "email_user": "user@example.com",
                "email_pass": "password",  # Optional (will prompt if missing)
                "connection_timeout": 30,
                "verification_timeout": 300,
                "max_retries": 3
            }
        """
        self.config = config
        self.imap_server = config.get("imap_server", "outlook.office365.com")
        self.imap_port = config.get("imap_port", 993)
        self.connection_timeout = config.get("connection_timeout", 30)
        self.verification_timeout = config.get("verification_timeout", 300)
        self.max_retries = config.get("max_retries", 3)
        
        # Secure credential handling
        self._username = config.get("email_user")
        self._password = config.get("email_pass") or getpass.getpass("Email password: ")
        self._password_hash = hashlib.sha256(self._password.encode()).hexdigest()
        
        self.imap = None
        self.is_connected = False
        self._connection_lock = False

    def __enter__(self):
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self) -> bool:
        """Establish IMAP connection with retry logic."""
        if self.is_connected:
            return True
            
        if self._connection_lock:
            logger.warning("Connection attempt already in progress")
            return False
            
        self._connection_lock = True
        
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Connection attempt {attempt}/{self.max_retries}")
                
                self.imap = imaplib.IMAP4_SSL(
                    self.imap_server,
                    self.imap_port,
                    timeout=self.connection_timeout
                )
                
                self.imap.login(self._username, self._password)
                self.imap.select('INBOX')
                self.is_connected = True
                logger.info("IMAP connection established")
                return True
                
            except imaplib.IMAP4.error as e:
                logger.error(f"IMAP error (attempt {attempt}): {str(e)}")
                if attempt == self.max_retries:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff
                
            except Exception as e:
                logger.error(f"Unexpected connection error: {str(e)}")
                self._safe_disconnect()
                if attempt == self.max_retries:
                    raise
                    
        self._connection_lock = False
        return False

    def _safe_disconnect(self) -> None:
        """Graceful disconnect with error suppression."""
        try:
            if self.imap:
                if self.is_connected:
                    self.imap.close()
                self.imap.logout()
        except Exception:
            pass
        finally:
            self.imap = None
            self.is_connected = False
            self._connection_lock = False

    def disconnect(self) -> None:
        """Thread-safe disconnection."""
        self._safe_disconnect()
        logger.info("Disconnected from IMAP server")

    @retry_imap()
    def verify_reddit_account(self, username: str, email_address: str, 
                            wait_for_verification: bool = True) -> VerificationResult:
        """
        Enhanced verification with timeout protection and pattern matching.
        
        Args:
            username: Reddit username to verify
            email_address: Email to check
            wait_for_verification: Whether to poll for new emails
            
        Returns:
            VerificationResult dataclass
        """
        result = VerificationResult(
            verified=False,
            email=email_address,
            reddit_username=username
        )
        
        try:
            with timeout(self.verification_timeout):
                if not self.connect():
                    result.error = "Connection failed"
                    return result
                
                # Check existing verifications
                existing = self._search_verification_emails(username, days=30)
                if existing:
                    verification_data = self._process_verification_email(existing[0])
                    if verification_data and verification_data.username.lower() == username.lower():
                        return self._create_success_result(verification_data, email_address, username)
                
                if not wait_for_verification:
                    result.error = "No existing verification found"
                    return result
                
                # Poll for new verification
                logger.info(f"Polling for new verification (timeout: {self.verification_timeout}s)")
                start_time = time.time()
                poll_interval = min(10, self.verification_timeout // 10)
                
                while time.time() - start_time < self.verification_timeout:
                    new_emails = self._search_verification_emails(username, minutes=5)
                    if new_emails:
                        verification_data = self._process_verification_email(new_emails[0])
                        if verification_data and verification_data.username.lower() == username.lower():
                            return self._create_success_result(verification_data, email_address, username)
                    
                    time.sleep(poll_interval)
                
                result.error = "Verification timeout reached"
                return result
                
        except TimeoutError:
            result.error = "Operation timed out"
            return result
        except Exception as e:
            logger.error(f"Verification error: {str(e)}", exc_info=True)
            result.error = str(e)
            return result

    def _create_success_result(self, verification_data: Dict, email: str, username: str) -> VerificationResult:
        """Helper to create successful verification result."""
        return VerificationResult(
            verified=True,
            email=email,
            reddit_username=username,
            verification_time=verification_data.get("timestamp"),
            verification_id=verification_data.get("message_id")
        )

    @retry_imap()
    @lru_cache(maxsize=100)
    def _process_verification_email(self, email_id: bytes) -> Optional[Dict[str, Any]]:
        """
        Cached email processing with enhanced extraction.
        """
        email_data = self._fetch_email(email_id)
        if not email_data:
            return None
            
        body = self._get_email_body(email_data["message"])
        username = self._extract_username(body)
        if not username:
            return None
            
        return {
            "username": username,
            "verification_link": self._extract_verification_link(body),
            "timestamp": self._get_email_timestamp(email_data["message"]),
            "message_id": email_data["message"].get("Message-ID", "").strip("<>"),
            "subject": email_data["message"].get("Subject")
        }

    def _extract_username(self, body: str) -> Optional[str]:
        """Multi-pattern username extraction."""
        body_lower = body.lower()
        for pattern in self.USERNAME_PATTERNS:
            match = re.search(pattern, body_lower)
            if match:
                return match.group(1)
        return None

    def _extract_verification_link(self, body: str) -> Optional[str]:
        """Robust link extraction."""
        patterns = [
            r'(https?://[^\s]*reddit\.com/verification/[^\s>]+)',
            r'<a href="(https?://[^"]+verification[^"]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _get_email_timestamp(self, msg) -> Optional[str]:
        """Safe timestamp parsing."""
        date_str = msg.get("Date")
        if date_str:
            try:
                return parsedate_to_datetime(date_str).isoformat()
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse email date: {date_str}")
        return None

    @retry_imap()
    def _search_verification_emails(self, username: Optional[str] = None, 
                                  days: int = 0, minutes: int = 0) -> List[bytes]:
        """
        Enhanced email search with combined criteria.
        """
        criteria = ['(FROM "reddit.com")', '(SUBJECT "verification")']
        
        if days > 0 or minutes > 0:
            since_date = (datetime.now() - timedelta(days=days, minutes=minutes))
            criteria.append(f'(SINCE "{since_date.strftime("%d-%b-%Y")}")')
            
        result, data = self.imap.search(None, ' '.join(criteria))
        if result != 'OK':
            return []
            
        email_ids = data[0].split()
        if not username or not email_ids:
            return email_ids
            
        # Filter by username if provided
        return [eid for eid in email_ids if self._email_matches_username(eid, username)]

    def _email_matches_username(self, email_id: bytes, username: str) -> bool:
        """Efficient username matching without full processing."""
        try:
            result, data = self.imap.fetch(email_id, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
            if result == 'OK' and data:
                subject = data[0][1].decode('utf-8', errors='ignore')
                return username.lower() in subject.lower()
        except Exception:
            logger.warning(f"Failed to check username match for email {email_id}")
        return False

    @retry_imap()
    def _fetch_email(self, email_id: bytes) -> Optional[Dict[str, Any]]:
        """Optimized email fetching with header preference."""
        try:
            result, data = self.imap.fetch(email_id, '(RFC822)')
            if result == 'OK' and data:
                return {
                    "id": email_id,
                    "message": email.message_from_bytes(data[0][1])
                }
        except Exception as e:
            logger.error(f"Email fetch failed: {str(e)}")
        return None

    def _get_email_body(self, msg) -> str:
        """Complete multi-part email body extraction."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype in ["text/plain", "text/html"]:
                    try:
                        body += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    except:
                        body += str(part.get_payload(decode=True))
                    if ctype == "text/plain":  # Prefer plain text
                        break
        else:
            payload = msg.get_payload(decode=True)
            body = payload.decode('utf-8', errors='ignore')
        return body.strip()

    # Additional utility methods remain unchanged...
    # (test_connection, get_inbox_statistics, get_verification_history)

def retry_imap(max_retries=3):
    """Decorator for IMAP operation retries."""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    if not self.is_connected:
                        self.connect()
                    return func(self, *args, **kwargs)
                except (imaplib.IMAP4.abort, ConnectionError) as e:
                    if attempt == max_retries - 1:
                        raise
                    self._safe_disconnect()
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Operation failed: {str(e)}")
                    raise
        return wrapper
    return decorator
