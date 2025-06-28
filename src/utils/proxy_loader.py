import os
import json
import random
import logging
import time
import ipaddress
from typing import List, Dict, Optional, Set, Union, Tuple
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class ProxyError(Exception):
    """Base exception for proxy-related errors."""
    pass


class NoProxiesAvailableError(ProxyError):
    """Raised when no proxies are available after filtering."""
    pass


class AuthenticationError(ProxyError):
    """Raised when proxy authentication credentials are missing or invalid."""
    pass


class ProxyLoader:
    """
    Enhanced proxy list loader for residential and datacenter proxies.
    
    Features:
    - Multiple authentication schemes (username/password with optional customer prefix)
    - Multiple proxy sources (environment variables, JSON file)
    - Filtering by country, datacenter, IP version
    - Automatic proxy rotation (sequential or random)
    - Proxy health checking and blacklisting
    - Detailed logging
    
    Typical usage:
    ```python
    # Basic usage
    loader = ProxyLoader("config/proxies.json")
    proxies = loader.load_proxies(country_filter="US")
    proxy = loader.get_next_proxy()
    
    # With blacklisting
    loader = ProxyLoader("config/proxies.json")
    proxies = loader.load_proxies()
    try:
        # Use proxy for some request
        proxy = loader.get_next_proxy()
        response = make_request(url, proxy=proxy)
        if response.status_code == 403:
            loader.blacklist_proxy(proxy)
    except Exception as e:
        loader.blacklist_proxy(proxy)
    ```
    """

    def __init__(self, config_path: str = "config/proxies.json"):
        """
        Initialize the ProxyLoader.
        
        Args:
            config_path: Path to the proxy configuration JSON file
        """
        self.config_path = Path(config_path)
        self._proxies = []
        self._original_proxies = []  # Keep a copy of unfiltered proxies
        self._current_index = 0
        self._blacklisted_proxies: Set[str] = set()
        self._validate_config_path()
        self._last_reload_time = 0
        self._proxy_details: Dict[str, Dict] = {}  # Maps formatted proxy URL to its details

    def _validate_config_path(self) -> None:
        """Validate that the config file exists and is readable."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Proxy config file not found at {self.config_path}")
        if not os.access(self.config_path, os.R_OK):
            raise PermissionError(f"No read permissions for {self.config_path}")

    def _load_credentials(self) -> Dict[str, str]:
        """
        Load proxy authentication credentials from environment variables.
        
        Returns:
            Dict containing username, password, and optional customer prefix
        
        Raises:
            AuthenticationError: If required credentials are missing
        """
        creds = {
            'username': os.getenv("OXYLABS_USERNAME"),
            'password': os.getenv("OXYLABS_PASSWORD"),
            'customer': os.getenv("OXYLABS_CUSTOMER", "")
        }
        
        if not creds['username'] or not creds['password']:
            raise AuthenticationError(
                "OXYLABS_USERNAME and OXYLABS_PASSWORD must be set in environment variables"
            )
            
        # URL encode the credentials to handle special characters
        creds['username'] = quote_plus(creds['username'])
        creds['password'] = quote_plus(creds['password'])
        if creds['customer']:
            creds['customer'] = quote_plus(creds['customer'])
            
        return creds

    def load_proxies(
        self,
        country_filter: Optional[str] = None,
        datacenter_filter: Optional[str] = None,
        ip_version: Optional[str] = None,
        shuffle: bool = True,
        protocol: str = "http",
        reload_if_older_than: int = 3600  # Reload if older than 1 hour
    ) -> List[str]:
        """
        Load and filter proxies from the configuration file.
        
        Args:
            country_filter: ISO country code to filter proxies (e.g., "US")
            datacenter_filter: Datacenter identifier to filter proxies
            ip_version: IP version to filter by ("4" or "6")
            shuffle: Whether to shuffle the proxy list
            protocol: Protocol to use (http, https, socks5)
            reload_if_older_than: Reload proxies if last load was older than this many seconds
            
        Returns:
            List of formatted proxy URLs
            
        Raises:
            ValueError: For invalid inputs or JSON format
            NoProxiesAvailableError: If no proxies match the filters
        """
        # Check if we need to reload based on time
        current_time = time.time()
        if self._proxies and (current_time - self._last_reload_time) < reload_if_older_than:
            logger.debug("Using cached proxy list")
            return self._proxies
            
        try:
            creds = self._load_credentials()
            
            with open(self.config_path, 'r') as f:
                raw_proxies = json.load(f)
                
            if not isinstance(raw_proxies, list):
                raise ValueError("Proxy config must contain a list of proxy entries")
                
            filtered_proxies = self._filter_proxies(
                raw_proxies, 
                country_filter, 
                datacenter_filter,
                ip_version
            )
            
            self._original_proxies = self._format_proxies(filtered_proxies, creds, protocol)
            
            # Filter out blacklisted proxies
            self._proxies = [p for p in self._original_proxies if p not in self._blacklisted_proxies]
            
            if shuffle:
                random.shuffle(self._proxies)
                
            self._last_reload_time = current_time
            
            if not self._proxies:
                raise NoProxiesAvailableError(
                    f"No proxies available after filtering (country={country_filter}, "
                    f"datacenter={datacenter_filter}, ip_version={ip_version})"
                )
                
            logger.info(f"Loaded {len(self._proxies)} proxies (filtered from {len(filtered_proxies)} total)")
            return self._proxies
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in proxy file: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to load proxies: {str(e)}")
            raise

    def _filter_proxies(
        self, 
        proxies: List[Dict], 
        country: Optional[str], 
        datacenter: Optional[str],
        ip_version: Optional[str]
    ) -> List[Dict]:
        """
        Filter proxies based on country, datacenter, and IP version.
        
        Args:
            proxies: List of proxy entries
            country: ISO country code filter
            datacenter: Datacenter identifier filter
            ip_version: IP version filter ("4" or "6")
            
        Returns:
            Filtered list of proxy entries
        """
        filtered = []
        for proxy in proxies:
            # Skip proxies missing required fields
            if not all(key in proxy for key in ['ip', 'port']):
                logger.warning(f"Skipping invalid proxy entry: {proxy}")
                continue
                
            # Country filter
            if country and proxy.get('countryCode', '').upper() != country.upper():
                continue
                
            # Datacenter filter
            if datacenter and proxy.get('dc', '') != datacenter:
                continue
                
            # IP version filter
            if ip_version:
                try:
                    ip_obj = ipaddress.ip_address(proxy['ip'])
                    if ip_version == "4" and not isinstance(ip_obj, ipaddress.IPv4Address):
                        continue
                    if ip_version == "6" and not isinstance(ip_obj, ipaddress.IPv6Address):
                        continue
                except ValueError:
                    logger.warning(f"Invalid IP address in proxy: {proxy['ip']}")
                    continue
                    
            filtered.append(proxy)
            
        if not filtered:
            logger.warning(
                f"No proxies matched the specified filters (country={country}, "
                f"datacenter={datacenter}, ip_version={ip_version})"
            )
            
        return filtered

    def _format_proxies(
        self, 
        proxies: List[Dict], 
        credentials: Dict[str, str], 
        protocol: str
    ) -> List[str]:
        """
        Format proxy entries into proxy URLs with authentication.
        
        Args:
            proxies: List of proxy entries
            credentials: Dict with authentication credentials
            protocol: Protocol to use
            
        Returns:
            List of formatted proxy URLs
            
        Raises:
            ValueError: If protocol is invalid
        """
        valid_protocols = ("http", "https", "socks5")
        if protocol not in valid_protocols:
            raise ValueError(f"Invalid protocol. Must be one of: {valid_protocols}")
            
        formatted = []
        for proxy in proxies:
            # Create auth string with or without customer prefix
            if credentials['customer']:
                auth = f"{credentials['customer']}-{credentials['username']}:{credentials['password']}"
            else:
                auth = f"{credentials['username']}:{credentials['password']}"
                
            url = f"{protocol}://{auth}@{proxy['ip']}:{proxy['port']}"
            formatted.append(url)
            
            # Store proxy details for later reference
            self._proxy_details[url] = proxy
            
        return formatted

    def get_next_proxy(self) -> Optional[str]:
        """
        Get the next proxy in the rotation.
        
        Returns:
            Next proxy URL or None if no proxies are available
        """
        if not self._proxies:
            return None
            
        proxy = self._proxies[self._current_index % len(self._proxies)]
        self._current_index += 1
        return proxy

    def get_random_proxy(self) -> Optional[str]:
        """
        Get a random proxy from the available proxies.
        
        Returns:
            Random proxy URL or None if no proxies are available
        """
        return random.choice(self._proxies) if self._proxies else None

    def get_proxy_count(self) -> int:
        """
        Get the count of available proxies.
        
        Returns:
            Number of available proxies
        """
        return len(self._proxies)

    def get_blacklisted_count(self) -> int:
        """
        Get the count of blacklisted proxies.
        
        Returns:
            Number of blacklisted proxies
        """
        return len(self._blacklisted_proxies)

    def blacklist_proxy(self, proxy: str) -> None:
        """
        Add a proxy to the blacklist. Blacklisted proxies will not be returned.
        
        Args:
            proxy: Proxy URL to blacklist
        """
        if proxy in self._proxies:
            self._blacklisted_proxies.add(proxy)
            self._proxies.remove(proxy)
            logger.info(f"Blacklisted proxy: {proxy}")
        else:
            logger.warning(f"Attempted to blacklist unknown proxy: {proxy}")

    def clear_blacklist(self) -> None:
        """Clear the proxy blacklist and restore all proxies."""
        self._blacklisted_proxies.clear()
        self._proxies = self._original_proxies.copy()
        logger.info("Cleared proxy blacklist")

    def get_proxy_details(self, proxy: str) -> Optional[Dict]:
        """
        Get detailed information about a proxy.
        
        Args:
            proxy: Proxy URL
            
        Returns:
            Dict with proxy details or None if proxy not found
        """
        return self._proxy_details.get(proxy)

    def reload_proxies(self, **kwargs) -> List[str]:
        """
        Force reload proxies from the configuration file.
        
        Args:
            **kwargs: Forwarded to load_proxies()
            
        Returns:
            List of formatted proxy URLs
        """
        self._last_reload_time = 0  # Force reload
        return self.load_proxies(**kwargs)


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example usage
    loader = ProxyLoader("config/proxy_lists.json")
    try:
        # Load US-based SOCKS5 proxies
        proxies = loader.load_proxies(
            country_filter="US", 
            protocol="socks5", 
            shuffle=True,
            ip_version="4"  # IPv4 only
        )
        
        print(f"Loaded {loader.get_proxy_count()} proxies")
        
        # Get and use proxies
        print("Next proxy:", loader.get_next_proxy())
        print("Random proxy:", loader.get_random_proxy())
        
        # Simulate proxy failure and blacklisting
        bad_proxy = loader.get_next_proxy()
        print(f"Simulating failure for {bad_proxy}")
        loader.blacklist_proxy(bad_proxy)
        print(f"Remaining proxies: {loader.get_proxy_count()}")
        print(f"Blacklisted proxies: {loader.get_blacklisted_count()}")
        
    except Exception as e:
        print(f"Proxy loading failed: {str(e)}")
