"""IMAP processor for Hotmail email verification."""

import os
import imaplib
import email
import email.header
import time
import logging
import re
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

class EmailVerifier:
    """
    Handles IMAP connections to Hotmail/Outlook for Reddit verification emails.
    Provides methods to search for and process Reddit verification messages.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the email verifier with configuration settings.
        
        Args:
            config: Dictionary containing email verification configuration
        """
        self.config = config
        self.imap_server = config.get("imap_server", "outlook.office365.com")
        self.imap_port = config.get("imap_port", 993)
        self.connection_timeout = config.get("connection_timeout", 30)
        self.verification_timeout = config.get("verification_timeout", 300)
        self.imap = None
        self.is_connected = False
    
    def __enter__(self):
        """Context manager entry point that connects to the email server."""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point that disconnects from the email server."""
        self.disconnect()
    
    def connect(self, username: str, password: str) -> bool:
        """
        Connect to the IMAP server and authenticate.
        
        Args:
            username: Email account username
            password: Email account password
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to {self.imap_server}:{self.imap_port}")
            
            # Create IMAP4 connection with SSL
            self.imap = imaplib.IMAP4_SSL(
                self.imap_server, 
                self.imap_port, 
                timeout=self.connection_timeout
            )
            
            # Authenticate
            logger.info(f"Authenticating as {username}")
            result, data = self.imap.login(username, password)
            
            if result != 'OK':
                logger.error(f"Authentication failed: {data}")
                return False
                
            # Select inbox
            result, data = self.imap.select('INBOX')
            if result != 'OK':
                logger.error(f"Failed to select inbox: {data}")
                return False
                
            self.is_connected = True
            logger.info("Successfully connected to email server")
            return True
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP connection error: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to email server: {e}")
            return False
    
    def disconnect(self) -> None:
        """Close the IMAP connection."""
        if self.imap:
            try:
                if self.is_connected:
                    self.imap.close()
                self.imap.logout()
                logger.info("Disconnected from email server")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self.imap = None
                self.is_connected = False
    
    def verify_reddit_account(self, username: str, email_address: str, wait_for_verification: bool = True) -> Dict[str, Any]:
        """
        Verify if a Reddit account is connected to a given email address.
        Optionally wait for a new verification email to arrive.
        
        Args:
            username: Reddit username to verify
            email_address: Email address to check for verification
            wait_for_verification: Whether to wait for new verification emails
            
        Returns:
            Dictionary with verification results
        """
        if not self.is_connected or not self.imap:
            return {
                "verified": False,
                "error": "Not connected to email server"
            }
            
        verification_result = {
            "verified": False,
            "email": email_address,
            "reddit_username": username,
            "verification_time": None,
            "verification_id": None,
            "error": None
        }
        
        # First, check for existing verification emails
        existing = self._search_verification_emails(username, days=30)
        
        if existing:
            # Process the most recent verification email
            verification_data = self._process_verification_email(existing[0])
            if verification_data and verification_data.get("username") == username:
                verification_result.update({
                    "verified": True,
                    "verification_time": verification_data.get("timestamp"),
                    "verification_id": verification_data.get("message_id")
                })
                logger.info(f"Found existing verification for {username}")
                return verification_result
        
        if not wait_for_verification:
            logger.info(f"No existing verification found for {username} and not waiting for new emails")
            return verification_result
            
        # Wait for new verification email to arrive
        logger.info(f"Waiting up to {self.verification_timeout} seconds for Reddit verification email")
        
        start_time = time.time()
        while time.time() - start_time < self.verification_timeout:
            # Check for new emails every 10 seconds
            time.sleep(10)
            
            try:
                # Check for new emails
                new_emails = self._search_verification_emails(username, minutes=10)
                
                if new_emails:
                    # Process the most recent verification email
                    verification_data = self._process_verification_email(new_emails[0])
                    
                    if verification_data and verification_data.get("username") == username:
                        verification_result.update({
                            "verified": True,
                            "verification_time": verification_data.get("timestamp"),
                            "verification_id": verification_data.get("message_id")
                        })
                        logger.info(f"Found new verification for {username}")
                        return verification_result
            except Exception as e:
                logger.error(f"Error while waiting for verification: {e}")
                verification_result["error"] = str(e)
                return verification_result
                
        # Timeout reached
        logger.warning(f"Verification timeout reached for {username}")
        verification_result["error"] = "Verification timeout"
        return verification_result
    
    def _search_verification_emails(self, username: Optional[str] = None, days: int = 0, minutes: int = 0) -> List[str]:
        """
        Search for Reddit verification emails.
        
        Args:
            username: Optional Reddit username to filter by
            days: Number of days back to search (default: 0)
            minutes: Number of minutes back to search (default: 0)
            
        Returns:
            List of email IDs matching search criteria
        """
        if not self.is_connected or not self.imap:
            logger.error("Not connected to email server")
            return []
            
        search_criteria = []
        
        # Add time criteria if specified
        if days > 0 or minutes > 0:
            date_since = datetime.now() - timedelta(days=days, minutes=minutes)
            date_str = date_since.strftime("%d-%b-%Y")
            search_criteria.append(f'(SINCE "{date_str}")')
        
        # Add subject and sender criteria
        search_criteria.append('(FROM "reddit.com")')
        search_criteria.append('(SUBJECT "Reddit account verification")')
        
        # Add username criteria if specified
        if username:
            # We'll do further filtering when we process the emails,
            # since IMAP doesn't support good substring matching
            pass
            
        # Combine search criteria
        search_query = ' '.join(search_criteria)
        
        try:
            logger.debug(f"Searching emails with criteria: {search_query}")
            result, data = self.imap.search(None, search_query)
            
            if result != 'OK':
                logger.error(f"Email search failed: {data}")
                return []
                
            # Get list of email IDs
            email_ids = data[0].split()
            
            if not email_ids:
                logger.info("No matching emails found")
                return []
                
            logger.info(f"Found {len(email_ids)} potential verification emails")
            
            # If username is specified, we need to filter the results
            if username:
                filtered_ids = []
                for email_id in email_ids:
                    email_data = self._fetch_email(email_id)
                    if email_data:
                        body = self._get_email_body(email_data)
                        if username.lower() in body.lower():
                            filtered_ids.append(email_id)
                
                logger.info(f"After filtering for {username}, found {len(filtered_ids)} matching emails")
                return filtered_ids
                
            return email_ids
            
        except Exception as e:
            logger.error(f"Error searching for verification emails: {e}")
            return []
    
    def _fetch_email(self, email_id: bytes) -> Optional[Dict[str, Any]]:
        """
        Fetch an email by ID.
        
        Args:
            email_id: Email ID to fetch
            
        Returns:
            Dictionary with email data or None if fetch failed
        """
        try:
            result, data = self.imap.fetch(email_id, '(RFC822)')
            
            if result != 'OK' or not data or not data[0]:
                logger.error(f"Failed to fetch email {email_id}")
                return None
                
            # Parse the email
            raw_email = data[0][1]
            email_message = email.message_from_bytes(raw_email)
            
            return {
                "id": email_id,
                "message": email_message
            }
            
        except Exception as e:
            logger.error(f"Error fetching email {email_id}: {e}")
            return None
    
    def _get_email_body(self, email_data: Dict[str, Any]) -> str:
        """
        Extract the body text from an email.
        
        Args:
            email_data: Email data dictionary
            
        Returns:
            Email body as plain text
        """
        email_message = email_data["message"]
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.get_payload():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
        else:
            body = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
            
        return body
    
    def _process_verification_email(self, email_id: bytes) -> Optional[Dict[str, Any]]:
        """
        Process a Reddit verification email and extract relevant data.
        
        Args:
            email_id: ID of the email to process
            
        Returns:
            Dictionary with verification data or None if processing failed
        """
        email_data = self._fetch_email(email_id)
        if not email_data:
            return None
            
        email_message = email_data["message"]
        body = self._get_email_body(email_data)
        
        # Extract Reddit username from email body
        username_match = re.search(r'u/(\w+)', body)
        if not username_match:
            logger.warning("Could not find Reddit username in verification email")
            return None
            
        username = username_match.group(1)
        
        # Extract verification link if present
        verification_link = None
        link_match = re.search(r'(https://www\.reddit\.com/verification/[^\s]+)', body)
        if link_match:
            verification_link = link_match.group(1)
            
        # Get email timestamp
        date_str = email_message.get("Date")
        timestamp = None
        if date_str:
            try:
                timestamp = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                logger.error(f"Could not parse email date: {date_str}")
                
        # Get message ID for reference
        message_id = email_message.get("Message-ID", "").strip("<>")
        
        return {
            "username": username,
            "verification_link": verification_link,
            "timestamp": timestamp,
            "message_id": message_id,
            "subject": email_message.get("Subject")
        }

    def test_connection(self) -> bool:
        """
        Test if the connection to the email server is working.
        
        Returns:
            True if connection is working, False otherwise
        """
        if not self.is_connected or not self.imap:
            return False
            
        try:
            result, data = self.imap.noop()
            return result == 'OK'
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
            
    def get_inbox_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the inbox.
        
        Returns:
            Dictionary with inbox statistics
        """
        if not self.is_connected or not self.imap:
            return {"error": "Not connected to email server"}
            
        try:
            result, data = self.imap.status('INBOX', '(MESSAGES UNSEEN)')
            
            if result != 'OK':
                logger.error(f"Failed to get inbox status: {data}")
                return {"error": "Failed to get inbox status"}
                
            # Parse status response
            status_match = re.search(r'MESSAGES\s+(\d+)\s+UNSEEN\s+(\d+)', data[0].decode('utf-8'))
            if not status_match:
                return {"error": "Failed to parse inbox status"}
                
            total_messages = int(status_match.group(1))
            unread_messages = int(status_match.group(2))
            
            # Get recent Reddit emails count
            reddit_emails = self._search_verification_emails(days=30)
            
            return {
                "total_messages": total_messages,
                "unread_messages": unread_messages,
                "reddit_verification_emails": len(reddit_emails)
            }
            
        except Exception as e:
            logger.error(f"Error getting inbox statistics: {e}")
            return {"error": str(e)}

    def get_verification_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get history of Reddit account verifications.
        
        Args:
            limit: Maximum number of verification emails to retrieve
            
        Returns:
            List of verification data dictionaries
        """
        if not self.is_connected or not self.imap:
            return [{"error": "Not connected to email server"}]
            
        try:
            # Search for verification emails
            email_ids = self._search_verification_emails(days=90)
            
            if not email_ids:
                return []
                
            # Process verification emails (up to the limit)
            verification_history = []
            for email_id in email_ids[:limit]:
                verification_data = self._process_verification_email(email_id)
                if verification_data:
                    verification_history.append(verification_data)
                    
            return verification_history
            
        except Exception as e:
            logger.error(f"Error getting verification history: {e}")
            return [{"error": str(e)}]
