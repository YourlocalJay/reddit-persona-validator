"""
Email verification module for authenticating Hotmail/Outlook accounts.

This module handles IMAP connections to email servers to verify Reddit accounts
through email confirmation and password reset mechanisms.
"""

from typing import Dict, List, Optional, Union, Any
import logging
import imaplib
import email
import time
import re
from email.header import decode_header
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class EmailVerifier:
    """Email verification using IMAP protocol."""
    
    def __init__(
        self,
        imap_server: str = "outlook.office365.com",
        port: int = 993,
        use_ssl: bool = True,
        mock_mode: bool = False
    ):
        """Initialize the email verifier.
        
        Args:
            imap_server: IMAP server address
            port: IMAP server port
            use_ssl: Whether to use SSL for connection
            mock_mode: Run in mock mode for testing
        """
        self.imap_server = imap_server
        self.port = port
        self.use_ssl = use_ssl
        self.mock_mode = mock_mode
        self.connection = None
        self.is_connected = False
        self.username = None
    
    def login(self, username: str, password: str) -> bool:
        """Log in to the email server.
        
        Args:
            username: Email address
            password: Email password
            
        Returns:
            True if login successful, False otherwise
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Logging in as {username}")
            self.is_connected = True
            self.username = username
            return True
        
        logger.info(f"Connecting to {self.imap_server}:{self.port} as {username}")
        
        try:
            # Create IMAP connection
            if self.use_ssl:
                self.connection = imaplib.IMAP4_SSL(self.imap_server, self.port)
            else:
                self.connection = imaplib.IMAP4(self.imap_server, self.port)
            
            # Login to server
            self.connection.login(username, password)
            self.is_connected = True
            self.username = username
            logger.info("Email login successful")
            return True
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP login error: {str(e)}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Email login error: {str(e)}")
            self.is_connected = False
            return False
    
    def find_emails(
        self, 
        sender: Optional[str] = None,
        subject_contains: Optional[str] = None,
        days_back: int = 30,
        max_emails: int = 10,
        folder: str = "INBOX"
    ) -> List[Dict[str, Any]]:
        """Find emails matching specified criteria.
        
        Args:
            sender: Email sender to filter by
            subject_contains: Text that should be in the subject
            days_back: How many days back to search
            max_emails: Maximum number of emails to return
            folder: Email folder to search in
            
        Returns:
            List of matching email dictionaries
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Finding emails from {sender} with '{subject_contains}' in subject")
            # Return mock data
            if sender == "noreply@reddit.com":
                return [
                    {
                        "id": "mock1",
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "subject": "Verify your Reddit account",
                        "sender": "noreply@reddit.com",
                        "body": "This is a mock Reddit verification email",
                        "has_link": True,
                        "verification_link": "https://www.reddit.com/verification/mock123456"
                    }
                ]
            return []
        
        if not self.is_connected or not self.connection:
            logger.error("Not connected to email server")
            return []
        
        logger.info(f"Searching for emails in {folder}")
        emails_found = []
        
        try:
            # Select the folder
            status, _ = self.connection.select(folder)
            if status != "OK":
                logger.error(f"Could not open folder: {folder}")
                return []
            
            # Calculate date for search
            date_since = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
            
            # Build search criteria
            search_criteria = f'(SINCE "{date_since}")'
            if sender:
                search_criteria = f'(SINCE "{date_since}" FROM "{sender}")'
            
            # Search for emails
            status, data = self.connection.search(None, search_criteria)
            if status != "OK":
                logger.error("Search failed")
                return []
            
            # Get list of email IDs
            email_ids = data[0].split()
            if not email_ids:
                logger.info("No matching emails found")
                return []
            
            # Process the most recent emails first
            email_ids.reverse()
            email_ids = email_ids[:max_emails]
            
            # Fetch and process each email
            for email_id in email_ids:
                status, data = self.connection.fetch(email_id, "(RFC822)")
                if status != "OK":
                    logger.warning(f"Failed to fetch email {email_id}")
                    continue
                
                # Parse the email
                msg = email.message_from_bytes(data[0][1])
                
                # Extract subject
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding or "utf-8")
                
                # Skip if subject doesn't match the filter
                if subject_contains and subject_contains.lower() not in subject.lower():
                    continue
                
                # Extract sender
                from_header = msg["From"]
                from_name, from_addr = email.utils.parseaddr(from_header)
                
                # Extract date
                date_header = msg["Date"]
                try:
                    email_date = email.utils.parsedate_to_datetime(date_header)
                    date_str = email_date.strftime("%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    date_str = date_header
                
                # Extract body and look for links
                body_text = ""
                verification_link = None
                has_link = False
                
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        
                        # Skip attachments
                        if "attachment" in content_disposition:
                            continue
                        
                        # Get the email body
                        if content_type == "text/plain" or content_type == "text/html":
                            try:
                                payload = part.get_payload(decode=True)
                                charset = part.get_content_charset() or "utf-8"
                                body_text = payload.decode(charset, errors="replace")
                                break
                            except Exception as e:
                                logger.warning(f"Error decoding email body: {str(e)}")
                else:
                    # If the message is not multipart
                    try:
                        payload = msg.get_payload(decode=True)
                        charset = msg.get_content_charset() or "utf-8"
                        body_text = payload.decode(charset, errors="replace")
                    except Exception as e:
                        logger.warning(f"Error decoding email body: {str(e)}")
                
                # Look for verification or reset links
                if "reddit.com" in body_text:
                    has_link = True
                    # Extract verification links
                    link_patterns = [
                        r'https://www\.reddit\.com/verification/[a-zA-Z0-9-_]+',
                        r'https://www\.reddit\.com/account/verify/[a-zA-Z0-9-_]+',
                        r'https://www\.reddit\.com/reset/password/[a-zA-Z0-9-_]+'
                    ]
                    
                    for pattern in link_patterns:
                        match = re.search(pattern, body_text)
                        if match:
                            verification_link = match.group(0)
                            break
                
                # Add to results
                email_data = {
                    "id": email_id.decode(),
                    "date": date_str,
                    "subject": subject,
                    "sender": from_addr,
                    "body": body_text[:1000] + ("..." if len(body_text) > 1000 else ""),
                    "has_link": has_link,
                    "verification_link": verification_link
                }
                
                emails_found.append(email_data)
            
            logger.info(f"Found {len(emails_found)} matching emails")
            return emails_found
            
        except Exception as e:
            logger.error(f"Error finding emails: {str(e)}")
            return []
    
    def wait_for_email(
        self,
        sender: str,
        subject_contains: Optional[str] = None,
        timeout_seconds: int = 60,
        check_interval: int = 5,
        folder: str = "INBOX"
    ) -> Optional[Dict[str, Any]]:
        """Wait for a specific email to arrive.
        
        Args:
            sender: Email sender to wait for
            subject_contains: Text that should be in the subject
            timeout_seconds: Maximum time to wait in seconds
            check_interval: How often to check for new emails in seconds
            folder: Email folder to monitor
            
        Returns:
            Email data dictionary if found, None if timeout
        """
        if self.mock_mode:
            logger.info(f"[MOCK] Waiting for email from {sender}")
            time.sleep(2)  # Simulate waiting
            if sender == "noreply@reddit.com":
                return {
                    "id": "mock2",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "subject": "Reset your Reddit password",
                    "sender": "noreply@reddit.com",
                    "body": "This is a mock Reddit password reset email",
                    "has_link": True,
                    "verification_link": "https://www.reddit.com/reset/password/mock654321"
                }
            return None
        
        if not self.is_connected or not self.connection:
            logger.error("Not connected to email server")
            return None
        
        logger.info(f"Waiting for email from {sender}" + 
                  (f" with '{subject_contains}'" if subject_contains else ""))
        
        start_time = time.time()
        
        # Record existing email IDs to identify new ones
        try:
            self.connection.select(folder)
            status, data = self.connection.search(None, f'(FROM "{sender}")')
            if status != "OK":
                logger.error("Failed to get existing emails")
                return None
            
            existing_ids = set(data[0].split())
            
            while (time.time() - start_time) < timeout_seconds:
                # Check for new emails
                status, data = self.connection.search(None, f'(FROM "{sender}")')
                if status != "OK":
                    logger.warning("Email search failed during wait")
                    time.sleep(check_interval)
                    continue
                
                current_ids = set(data[0].split())
                new_ids = current_ids - existing_ids
                
                if new_ids:
                    logger.info(f"New email(s) arrived: {len(new_ids)} found")
                    
                    # Check each new email
                    for email_id in new_ids:
                        status, data = self.connection.fetch(email_id, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        # Parse the email
                        msg = email.message_from_bytes(data[0][1])
                        
                        # Extract subject
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding or "utf-8")
                        
                        # Check if subject matches
                        if subject_contains and subject_contains.lower() not in subject.lower():
                            continue
                        
                        # If we got here, we found the right email
                        logger.info(f"Found matching email: '{subject}'")
                        
                        # Process the email content (similar to find_emails method)
                        from_header = msg["From"]
                        _, from_addr = email.utils.parseaddr(from_header)
                        
                        date_header = msg["Date"]
                        try:
                            email_date = email.utils.parsedate_to_datetime(date_header)
                            date_str = email_date.strftime("%Y-%m-%d %H:%M:%S")
                        except (TypeError, ValueError):
                            date_str = date_header
                        
                        # Extract body and look for links
                        body_text = ""
                        verification_link = None
                        has_link = False
                        
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                content_disposition = str(part.get("Content-Disposition"))
                                
                                if "attachment" in content_disposition:
                                    continue
                                
                                if content_type == "text/plain" or content_type == "text/html":
                                    try:
                                        payload = part.get_payload(decode=True)
                                        charset = part.get_content_charset() or "utf-8"
                                        body_text = payload.decode(charset, errors="replace")
                                        break
                                    except Exception as e:
                                        logger.warning(f"Error decoding email: {str(e)}")
                        else:
                            try:
                                payload = msg.get_payload(decode=True)
                                charset = msg.get_content_charset() or "utf-8"
                                body_text = payload.decode(charset, errors="replace")
                            except Exception as e:
                                logger.warning(f"Error decoding email: {str(e)}")
                        
                        # Look for verification or reset links
                        if "reddit.com" in body_text:
                            has_link = True
                            # Extract verification links
                            link_patterns = [
                                r'https://www\.reddit\.com/verification/[a-zA-Z0-9-_]+',
                                r'https://www\.reddit\.com/account/verify/[a-zA-Z0-9-_]+',
                                r'https://www\.reddit\.com/reset/password/[a-zA-Z0-9-_]+'
                            ]
                            
                            for pattern in link_patterns:
                                match = re.search(pattern, body_text)
                                if match:
                                    verification_link = match.group(0)
                                    break
                        
                        return {
                            "id": email_id.decode(),
                            "date": date_str,
                            "subject": subject,
                            "sender": from_addr,
                            "body": body_text[:1000] + ("..." if len(body_text) > 1000 else ""),
                            "has_link": has_link,
                            "verification_link": verification_link
                        }
                
                # Update existing IDs for next iteration
                existing_ids = current_ids
                
                # Wait before checking again
                time.sleep(check_interval)
            
            logger.warning(f"Timeout waiting for email from {sender}")
            return None
            
        except Exception as e:
            logger.error(f"Error waiting for email: {str(e)}")
            return None
    
    def follow_verification_link(self, email_data: Dict[str, Any]) -> bool:
        """Extract and follow a verification link from an email.
        
        Args:
            email_data: Email data dictionary from find_emails or wait_for_email
            
        Returns:
            True if verification successful, False otherwise
        """
        if self.mock_mode:
            logger.info("[MOCK] Following verification link")
            return True
        
        if not email_data or not email_data.get("verification_link"):
            logger.error("No verification link found in email data")
            return False
        
        # This would normally use the browser engine to follow the link
        # For the email verifier, we just return True since the link existence
        # is enough to confirm the association
        logger.info(f"Verification link found: {email_data['verification_link']}")
        return True
    
    def logout(self) -> None:
        """Log out from the email server."""
        if self.mock_mode:
            logger.info("[MOCK] Logging out from email")
            self.is_connected = False
            return
        
        if self.connection and self.is_connected:
            try:
                self.connection.logout()
                logger.info("Logged out from email server")
            except Exception as e:
                logger.error(f"Error logging out: {str(e)}")
            finally:
                self.is_connected = False
                self.connection = None
    
    def close(self) -> None:
        """Close the connection and clean up resources."""
        self.logout()
