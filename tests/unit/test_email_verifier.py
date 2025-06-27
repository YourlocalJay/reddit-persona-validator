"""Unit tests for the email verifier module."""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import time
from datetime import datetime
import email

from src.core.email_verifier import EmailVerifier


class TestEmailVerifier(unittest.TestCase):
    """Test cases for the EmailVerifier class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            "imap_server": "outlook.office365.com",
            "imap_port": 993,
            "connection_timeout": 5,
            "verification_timeout": 10
        }
        
        # Patch imaplib
        self.imaplib_patcher = patch('src.core.email_verifier.imaplib')
        self.mock_imaplib = self.imaplib_patcher.start()
        
        # Mock IMAP4_SSL instance
        self.mock_imap = MagicMock()
        self.mock_imaplib.IMAP4_SSL.return_value = self.mock_imap
        
        # Configure mock IMAP responses
        self.mock_imap.login.return_value = ('OK', [b'Login successful'])
        self.mock_imap.select.return_value = ('OK', [b'1'])
    
    def tearDown(self):
        """Tear down test fixtures."""
        self.imaplib_patcher.stop()
    
    def test_connect(self):
        """Test connecting to the email server."""
        verifier = EmailVerifier(self.config)
        
        # Test successful connection
        result = verifier.connect("test@outlook.com", "password123")
        
        # Verify connection was established
        self.assertTrue(result)
        self.assertTrue(verifier.is_connected)
        
        # Verify IMAP methods were called
        self.mock_imaplib.IMAP4_SSL.assert_called_once_with(
            "outlook.office365.com", 993, timeout=5
        )
        self.mock_imap.login.assert_called_once_with("test@outlook.com", "password123")
        self.mock_imap.select.assert_called_once_with('INBOX')
    
    def test_connect_failure(self):
        """Test connection failure handling."""
        verifier = EmailVerifier(self.config)
        
        # Test login failure
        self.mock_imap.login.return_value = ('NO', [b'Login failed'])
        
        result = verifier.connect("test@outlook.com", "wrong_password")
        
        self.assertFalse(result)
        self.assertFalse(verifier.is_connected)
    
    def test_disconnect(self):
        """Test disconnecting from the email server."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        verifier.disconnect()
        
        # Verify IMAP methods were called
        self.mock_imap.close.assert_called_once()
        self.mock_imap.logout.assert_called_once()
        
        # Verify attributes were reset
        self.assertIsNone(verifier.imap)
        self.assertFalse(verifier.is_connected)
    
    def test_context_manager(self):
        """Test that context manager properly connects and disconnects."""
        with patch.object(EmailVerifier, 'connect') as mock_connect:
            with patch.object(EmailVerifier, 'disconnect') as mock_disconnect:
                with EmailVerifier(self.config) as verifier:
                    mock_connect.assert_called_once()
                
                mock_disconnect.assert_called_once()
    
    def test_search_verification_emails(self):
        """Test searching for verification emails."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        # Mock search results
        self.mock_imap.search.return_value = ('OK', [b'1 2 3'])
        
        # Mock fetch for username filtering
        mock_email = MagicMock()
        mock_email.get_payload.return_value = "This is an email for u/testuser"
        
        with patch.object(verifier, '_fetch_email') as mock_fetch:
            with patch.object(verifier, '_get_email_body') as mock_get_body:
                mock_fetch.return_value = {"message": mock_email}
                mock_get_body.return_value = "This is an email for u/testuser"
                
                # Test search without username
                email_ids = verifier._search_verification_emails(days=30)
                
                # Verify correct search criteria were used
                self.mock_imap.search.assert_called_with(
                    None, 
                    '(SINCE "26-May-2025") (FROM "reddit.com") (SUBJECT "Reddit account verification")'
                )
                self.assertEqual(email_ids, [b'1', b'2', b'3'])
                
                # Test search with username
                email_ids = verifier._search_verification_emails(username="testuser", days=30)
                
                # Verify emails were filtered by username
                self.assertEqual(len(email_ids), 3)
    
    def test_process_verification_email(self):
        """Test processing a verification email."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        # Create a mock email message
        mock_email_message = email.message.Message()
        mock_email_message["Subject"] = "Reddit account verification"
        mock_email_message["Date"] = "Thu, 26 Jun 2025 12:00:00 -0400"
        mock_email_message["Message-ID"] = "<message123@reddit.com>"
        mock_email_message.set_payload("u/testuser - Verify your Reddit account at https://www.reddit.com/verification/abc123")
        
        with patch.object(verifier, '_fetch_email') as mock_fetch:
            with patch.object(verifier, '_get_email_body') as mock_get_body:
                mock_fetch.return_value = {"id": b'1', "message": mock_email_message}
                mock_get_body.return_value = "u/testuser - Verify your Reddit account at https://www.reddit.com/verification/abc123"
                
                # Process the email
                verification_data = verifier._process_verification_email(b'1')
                
                # Verify correct data was extracted
                self.assertEqual(verification_data["username"], "testuser")
                self.assertEqual(verification_data["verification_link"], "https://www.reddit.com/verification/abc123")
                self.assertIsNotNone(verification_data["timestamp"])
                self.assertEqual(verification_data["message_id"], "message123@reddit.com")
    
    def test_verify_reddit_account_existing(self):
        """Test verifying a Reddit account with existing verification."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        # Mock verification data
        verification_data = {
            "username": "testuser",
            "verification_link": "https://www.reddit.com/verification/abc123",
            "timestamp": "2025-06-26T12:00:00-04:00",
            "message_id": "message123@reddit.com",
            "subject": "Reddit account verification"
        }
        
        with patch.object(verifier, '_search_verification_emails') as mock_search:
            with patch.object(verifier, '_process_verification_email') as mock_process:
                mock_search.return_value = [b'1']
                mock_process.return_value = verification_data
                
                # Test verification
                result = verifier.verify_reddit_account("testuser", "test@outlook.com")
                
                # Verify correct result
                self.assertTrue(result["verified"])
                self.assertEqual(result["reddit_username"], "testuser")
                self.assertEqual(result["verification_time"], "2025-06-26T12:00:00-04:00")
                self.assertEqual(result["verification_id"], "message123@reddit.com")
    
    def test_verify_reddit_account_waiting(self):
        """Test waiting for a new verification email."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        # Mock no existing verification, then new verification after wait
        verification_data = {
            "username": "testuser",
            "verification_link": "https://www.reddit.com/verification/abc123",
            "timestamp": "2025-06-26T12:00:00-04:00",
            "message_id": "message123@reddit.com",
            "subject": "Reddit account verification"
        }
        
        with patch.object(verifier, '_search_verification_emails') as mock_search:
            with patch.object(verifier, '_process_verification_email') as mock_process:
                with patch('src.core.email_verifier.time.sleep'):
                    # No existing verification
                    mock_search.side_effect = [[], [b'1']]
                    mock_process.return_value = verification_data
                    
                    # Test verification with waiting
                    result = verifier.verify_reddit_account("testuser", "test@outlook.com", wait_for_verification=True)
                    
                    # Verify correct result
                    self.assertTrue(result["verified"])
                    self.assertEqual(result["reddit_username"], "testuser")
    
    def test_verify_reddit_account_timeout(self):
        """Test verification timeout."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        with patch.object(verifier, '_search_verification_emails') as mock_search:
            with patch('src.core.email_verifier.time.sleep'):
                with patch('src.core.email_verifier.time.time') as mock_time:
                    # No existing verification
                    mock_search.return_value = []
                    
                    # Set up time to trigger timeout
                    mock_time.side_effect = [0, 100, 200, 300, 400]
                    
                    # Test verification with timeout
                    result = verifier.verify_reddit_account("testuser", "test@outlook.com", wait_for_verification=True)
                    
                    # Verify correct result
                    self.assertFalse(result["verified"])
                    self.assertEqual(result["error"], "Verification timeout")
    
    def test_test_connection(self):
        """Test connection test functionality."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        # Mock successful NOOP
        self.mock_imap.noop.return_value = ('OK', [b'NOOP completed'])
        
        # Test connection test
        result = verifier.test_connection()
        
        # Verify result
        self.assertTrue(result)
        self.mock_imap.noop.assert_called_once()
        
        # Test failed connection
        self.mock_imap.noop.return_value = ('NO', [b'Connection lost'])
        result = verifier.test_connection()
        self.assertFalse(result)
    
    def test_get_inbox_statistics(self):
        """Test getting inbox statistics."""
        verifier = EmailVerifier(self.config)
        verifier.imap = self.mock_imap
        verifier.is_connected = True
        
        # Mock status response
        self.mock_imap.status.return_value = ('OK', [b'INBOX (MESSAGES 100 UNSEEN 10)'])
        
        with patch.object(verifier, '_search_verification_emails') as mock_search:
            mock_search.return_value = [b'1', b'2', b'3']
            
            # Test getting statistics
            stats = verifier.get_inbox_statistics()
            
            # Verify correct statistics
            self.assertEqual(stats["total_messages"], 100)
            self.assertEqual(stats["unread_messages"], 10)
            self.assertEqual(stats["reddit_verification_emails"], 3)


if __name__ == '__main__':
    unittest.main()
