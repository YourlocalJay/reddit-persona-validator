#!/usr/bin/env python3
"""
Unit tests for the ProxyLoader class.

Run with pytest:
    pytest -xvs tests/test_proxy_loader.py
"""

import os
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from typing import Dict, List

import pytest

from src.utils.proxy_loader import (
    ProxyLoader,
    ProxyError,
    NoProxiesAvailableError,
    AuthenticationError
)


class TestProxyLoader(unittest.TestCase):
    """Test suite for ProxyLoader class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary proxy configuration file
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "test_proxies.json"
        
        # Sample proxy data
        self.proxy_data = [
            {
                "ip": "192.168.1.1",
                "port": 8080,
                "countryCode": "US",
                "dc": "dc1"
            },
            {
                "ip": "192.168.1.2",
                "port": 8080,
                "countryCode": "CA",
                "dc": "dc2"
            },
            {
                "ip": "192.168.1.3",
                "port": 8080,
                "countryCode": "US",
                "dc": "dc1"
            },
            {
                "ip": "2001:db8::1",
                "port": 8080,
                "countryCode": "UK",
                "dc": "dc3"
            }
        ]
        
        # Write the sample data to the config file
        with open(self.config_path, 'w') as f:
            json.dump(self.proxy_data, f)
            
        # Mock environment variables
        self.env_patcher = mock.patch.dict(os.environ, {
            "OXYLABS_USERNAME": "testuser",
            "OXYLABS_PASSWORD": "testpass",
            "OXYLABS_CUSTOMER": "testcustomer"
        })
        self.env_patcher.start()
        
        # Create the proxy loader instance
        self.loader = ProxyLoader(str(self.config_path))

    def tearDown(self):
        """Tear down test fixtures."""
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def test_init_with_invalid_path(self):
        """Test initialization with an invalid config path."""
        with pytest.raises(FileNotFoundError):
            ProxyLoader("nonexistent/path.json")

    def test_load_credentials(self):
        """Test loading credentials from environment variables."""
        creds = self.loader._load_credentials()
        assert creds["username"] == "testuser"
        assert creds["password"] == "testpass"
        assert creds["customer"] == "testcustomer"

    def test_load_credentials_missing(self):
        """Test loading credentials with missing environment variables."""
        with mock.patch.dict(os.environ, {
            "OXYLABS_USERNAME": "",
            "OXYLABS_PASSWORD": ""
        }):
            with pytest.raises(AuthenticationError):
                self.loader._load_credentials()

    def test_load_proxies_basic(self):
        """Test basic proxy loading functionality."""
        proxies = self.loader.load_proxies(shuffle=False)
        assert len(proxies) == 4
        assert all(p.startswith("http://") for p in proxies)
        assert all("testcustomer" in p for p in proxies)

    def test_load_proxies_with_country_filter(self):
        """Test loading proxies with country filter."""
        proxies = self.loader.load_proxies(country_filter="US", shuffle=False)
        assert len(proxies) == 2
        
        # Verify IPs in the filtered proxies
        assert any("192.168.1.1" in p for p in proxies)
        assert any("192.168.1.3" in p for p in proxies)
        assert not any("192.168.1.2" in p for p in proxies)

    def test_load_proxies_with_datacenter_filter(self):
        """Test loading proxies with datacenter filter."""
        proxies = self.loader.load_proxies(datacenter_filter="dc1", shuffle=False)
        assert len(proxies) == 2
        
        # Verify IPs in the filtered proxies
        assert any("192.168.1.1" in p for p in proxies)
        assert any("192.168.1.3" in p for p in proxies)
        assert not any("192.168.1.2" in p for p in proxies)

    def test_load_proxies_with_ip_version_filter(self):
        """Test loading proxies with IP version filter."""
        # IPv4 only
        proxies = self.loader.load_proxies(ip_version="4", shuffle=False)
        assert len(proxies) == 3
        assert not any("2001:db8::1" in p for p in proxies)
        
        # IPv6 only
        proxies = self.loader.load_proxies(ip_version="6", shuffle=False)
        assert len(proxies) == 1
        assert any("2001:db8::1" in p for p in proxies)

    def test_load_proxies_with_multiple_filters(self):
        """Test loading proxies with multiple filters applied."""
        proxies = self.loader.load_proxies(
            country_filter="US",
            datacenter_filter="dc1",
            ip_version="4",
            shuffle=False
        )
        assert len(proxies) == 2
        assert all("192.168.1" in p for p in proxies)

    def test_load_proxies_with_no_matches(self):
        """Test loading proxies with filters that result in no matches."""
        with pytest.raises(NoProxiesAvailableError):
            self.loader.load_proxies(country_filter="DE")

    def test_load_proxies_with_protocol(self):
        """Test loading proxies with different protocols."""
        # HTTP protocol (default)
        proxies = self.loader.load_proxies(shuffle=False)
        assert all(p.startswith("http://") for p in proxies)
        
        # HTTPS protocol
        proxies = self.loader.load_proxies(protocol="https", shuffle=False)
        assert all(p.startswith("https://") for p in proxies)
        
        # SOCKS5 protocol
        proxies = self.loader.load_proxies(protocol="socks5", shuffle=False)
        assert all(p.startswith("socks5://") for p in proxies)
        
        # Invalid protocol
        with pytest.raises(ValueError):
            self.loader.load_proxies(protocol="invalid")

    def test_get_next_proxy(self):
        """Test getting the next proxy in rotation."""
        self.loader.load_proxies(shuffle=False)
        
        # Get all proxies in sequence
        proxies = []
        for _ in range(4):
            proxies.append(self.loader.get_next_proxy())
            
        # Check all proxies are different
        assert len(set(proxies)) == 4
        
        # Check rotation wraps around
        next_proxy = self.loader.get_next_proxy()
        assert next_proxy == proxies[0]

    def test_get_random_proxy(self):
        """Test getting a random proxy."""
        self.loader.load_proxies()
        
        # Get several random proxies
        random_proxies = [self.loader.get_random_proxy() for _ in range(10)]
        
        # At least some should be different (with high probability)
        assert len(set(random_proxies)) > 1

    def test_blacklist_proxy(self):
        """Test blacklisting a proxy."""
        self.loader.load_proxies(shuffle=False)
        initial_count = self.loader.get_proxy_count()
        
        # Blacklist a proxy
        proxy = self.loader.get_next_proxy()
        self.loader.blacklist_proxy(proxy)
        
        # Check proxy count decreased
        assert self.loader.get_proxy_count() == initial_count - 1
        assert self.loader.get_blacklisted_count() == 1
        
        # Verify the blacklisted proxy is not returned
        for _ in range(initial_count):
            assert self.loader.get_next_proxy() != proxy

    def test_clear_blacklist(self):
        """Test clearing the proxy blacklist."""
        self.loader.load_proxies(shuffle=False)
        initial_count = self.loader.get_proxy_count()
        
        # Blacklist a couple of proxies
        proxy1 = self.loader.get_next_proxy()
        self.loader.blacklist_proxy(proxy1)
        proxy2 = self.loader.get_next_proxy()
        self.loader.blacklist_proxy(proxy2)
        
        assert self.loader.get_proxy_count() == initial_count - 2
        
        # Clear the blacklist
        self.loader.clear_blacklist()
        
        # Check all proxies are available again
        assert self.loader.get_proxy_count() == initial_count
        assert self.loader.get_blacklisted_count() == 0

    def test_reload_proxies(self):
        """Test reloading proxies."""
        self.loader.load_proxies(country_filter="US")
        assert self.loader.get_proxy_count() == 2
        
        # Update the proxy file with new data
        new_data = [
            {
                "ip": "192.168.2.1",
                "port": 8080,
                "countryCode": "US",
                "dc": "dc1"
            }
        ]
        with open(self.config_path, 'w') as f:
            json.dump(new_data, f)
            
        # Reload proxies
        self.loader.reload_proxies()
        
        # Check the new data is loaded
        assert self.loader.get_proxy_count() == 1
        assert "192.168.2.1" in self.loader.get_next_proxy()

    def test_get_proxy_details(self):
        """Test getting detailed information about a proxy."""
        self.loader.load_proxies(shuffle=False)
        proxy = self.loader.get_next_proxy()
        
        # Get details of the proxy
        details = self.loader.get_proxy_details(proxy)
        
        # Check details are available
        assert details is not None
        assert "ip" in details
        assert "port" in details
        assert "countryCode" in details


if __name__ == "__main__":
    unittest.main()
