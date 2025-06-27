"""Unit tests for the proxy rotator utility."""

import os
import unittest
from unittest.mock import patch, MagicMock
import time

from src.utils.proxy_rotator import ProxyRotator, Proxy


class TestProxy(unittest.TestCase):
    """Test cases for the Proxy class."""
    
    def test_proxy_initialization(self):
        """Test that a proxy initializes with the correct attributes."""
        proxy = Proxy("192.168.1.1", 8080, "user", "pass")
        
        self.assertEqual(proxy.ip, "192.168.1.1")
        self.assertEqual(proxy.port, 8080)
        self.assertEqual(proxy.username, "user")
        self.assertEqual(proxy.password, "pass")
        self.assertEqual(proxy.failures, 0)
        self.assertTrue(proxy.is_healthy)
    
    def test_proxy_url_formatting(self):
        """Test that proxy URLs are correctly formatted."""
        # With auth
        proxy = Proxy("192.168.1.1", 8080, "user", "pass")
        self.assertEqual(proxy.url, "http://user:pass@192.168.1.1:8080")
        
        # Without auth
        proxy = Proxy("192.168.1.1", 8080)
        self.assertEqual(proxy.url, "http://192.168.1.1:8080")
    
    def test_dict_format(self):
        """Test that the proxy dict format is correct for requests."""
        proxy = Proxy("192.168.1.1", 8080)
        expected = {
            "http": "http://192.168.1.1:8080",
            "https": "http://192.168.1.1:8080"
        }
        self.assertEqual(proxy.dict_format, expected)
    
    def test_mark_failure(self):
        """Test failure counter incrementation."""
        proxy = Proxy("192.168.1.1", 8080)
        self.assertEqual(proxy.failures, 0)
        
        proxy.mark_failure()
        self.assertEqual(proxy.failures, 1)
        
        proxy.mark_failure()
        self.assertEqual(proxy.failures, 2)
    
    def test_reset_failures(self):
        """Test failure counter reset."""
        proxy = Proxy("192.168.1.1", 8080)
        proxy.failures = 5
        
        proxy.reset_failures()
        self.assertEqual(proxy.failures, 0)
    
    def test_mark_used(self):
        """Test that last_used timestamp is updated."""
        proxy = Proxy("192.168.1.1", 8080)
        old_time = proxy.last_used
        
        time.sleep(0.01)  # Ensure some time passes
        proxy.mark_used()
        
        self.assertGreater(proxy.last_used, old_time)


class TestProxyRotator(unittest.TestCase):
    """Test cases for the ProxyRotator class."""
    
    @patch.dict(os.environ, {"PROXY_LIST": "192.168.1.1:8080:user:pass,10.0.0.1:3128"})
    def test_load_proxies_from_env(self):
        """Test loading proxies from environment variables."""
        config = {"rotation_interval": 60}
        rotator = ProxyRotator(config)
        
        self.assertEqual(len(rotator.proxies), 2)
        self.assertEqual(rotator.proxies[0].ip, "192.168.1.1")
        self.assertEqual(rotator.proxies[0].port, 8080)
        self.assertEqual(rotator.proxies[0].username, "user")
        self.assertEqual(rotator.proxies[0].password, "pass")
        
        self.assertEqual(rotator.proxies[1].ip, "10.0.0.1")
        self.assertEqual(rotator.proxies[1].port, 3128)
        self.assertIsNone(rotator.proxies[1].username)
        self.assertIsNone(rotator.proxies[1].password)
    
    @patch.dict(os.environ, {"PROXY_LIST": ""})
    def test_empty_proxy_list(self):
        """Test behavior with empty proxy list."""
        config = {}
        rotator = ProxyRotator(config)
        
        self.assertEqual(len(rotator.proxies), 0)
        self.assertIsNone(rotator.get_proxy())
    
    @patch('requests.get')
    @patch.dict(os.environ, {"PROXY_LIST": "192.168.1.1:8080,10.0.0.1:3128"})
    def test_health_check(self, mock_get):
        """Test proxy health check functionality."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        config = {
            "health_check_interval": 0.1,  # Speed up testing
            "max_failures": 2
        }
        
        # Create the rotator but skip the health check thread
        with patch.object(ProxyRotator, '_start_health_check_thread'):
            rotator = ProxyRotator(config)
            
            # Manually trigger health check
            rotator._check_all_proxies()
            
            # All proxies should be healthy
            self.assertTrue(all(p.is_healthy for p in rotator.proxies))
            self.assertEqual(all(p.failures for p in rotator.proxies), 0)
            
            # Now make health check fail
            mock_get.side_effect = Exception("Connection error")
            
            # First failure
            rotator._check_all_proxies()
            self.assertTrue(all(p.is_healthy for p in rotator.proxies))  # Still healthy
            self.assertEqual(all(p.failures for p in rotator.proxies), 1)  # But failures recorded
            
            # Second failure - should mark unhealthy due to max_failures=2
            rotator._check_all_proxies()
            self.assertFalse(any(p.is_healthy for p in rotator.proxies))  # All unhealthy
            self.assertEqual(all(p.failures for p in rotator.proxies), 2)
    
    @patch.dict(os.environ, {"PROXY_LIST": "192.168.1.1:8080,10.0.0.1:3128"})
    def test_get_proxy(self):
        """Test proxy rotation and selection."""
        config = {"rotation_interval": 0.1}  # Short interval for testing
        
        # Create the rotator but skip the health check thread
        with patch.object(ProxyRotator, '_start_health_check_thread'):
            rotator = ProxyRotator(config)
            
            # Get first proxy
            proxy1 = rotator.get_proxy()
            self.assertIsNotNone(proxy1)
            
            # Get another proxy - should get a different one since we have multiple
            proxy2 = rotator.get_proxy()
            self.assertIsNotNone(proxy2)
            
            # Force all proxies to be recently used
            for proxy in rotator.proxies:
                proxy.mark_used()
            
            # Wait for rotation interval to expire
            time.sleep(0.15)
            
            # Get proxy again - should work after interval
            proxy3 = rotator.get_proxy()
            self.assertIsNotNone(proxy3)
    
    @patch.dict(os.environ, {"PROXY_LIST": "192.168.1.1:8080"})
    def test_mark_proxy_failure(self):
        """Test marking a proxy as failed."""
        config = {"max_failures": 2}
        
        # Create the rotator but skip the health check thread
        with patch.object(ProxyRotator, '_start_health_check_thread'):
            rotator = ProxyRotator(config)
            
            # First failure
            rotator.mark_proxy_failure("http://192.168.1.1:8080")
            self.assertEqual(rotator.proxies[0].failures, 1)
            self.assertTrue(rotator.proxies[0].is_healthy)
            
            # Second failure - should mark unhealthy due to max_failures=2
            rotator.mark_proxy_failure("http://192.168.1.1:8080")
            self.assertEqual(rotator.proxies[0].failures, 2)
            self.assertFalse(rotator.proxies[0].is_healthy)
    
    @patch.dict(os.environ, {"PROXY_LIST": "192.168.1.1:8080,10.0.0.1:3128"})
    def test_get_status(self):
        """Test getting proxy pool status."""
        # Create the rotator but skip the health check thread
        with patch.object(ProxyRotator, '_start_health_check_thread'):
            rotator = ProxyRotator({})
            
            # Both proxies start healthy
            status = rotator.get_status()
            self.assertEqual(status["total_proxies"], 2)
            self.assertEqual(status["healthy_proxies"], 2)
            self.assertEqual(status["unhealthy_proxies"], 0)
            
            # Mark one proxy as unhealthy
            rotator.proxies[0].is_healthy = False
            
            # Check status again
            status = rotator.get_status()
            self.assertEqual(status["total_proxies"], 2)
            self.assertEqual(status["healthy_proxies"], 1)
            self.assertEqual(status["unhealthy_proxies"], 1)


if __name__ == '__main__':
    unittest.main()
