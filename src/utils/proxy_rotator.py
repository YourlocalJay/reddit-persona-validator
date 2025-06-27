"""Proxy rotation utility with health checks."""

import os
import time
import logging
import random
import threading
import requests
from typing import Dict, Optional, List, Tuple, Any

logger = logging.getLogger(__name__)

class Proxy:
    """
    Representation of a single proxy with tracking for health status.
    """
    def __init__(self, ip: str, port: int, username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize a proxy instance with connection details and health metrics.
        
        Args:
            ip: The IP address of the proxy
            port: The port number of the proxy
            username: Optional username for proxy authentication
            password: Optional password for proxy authentication
        """
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.failures = 0
        self.last_used = 0
        self.is_healthy = True
    
    @property
    def url(self) -> str:
        """
        Get the proxy URL in the format required by requests library.
        
        Returns:
            Formatted proxy URL string
        """
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"http://{auth}{self.ip}:{self.port}"
    
    @property
    def dict_format(self) -> Dict[str, str]:
        """
        Get the proxy in dictionary format for use with requests.
        
        Returns:
            Dictionary with http and https proxy settings
        """
        return {
            "http": self.url,
            "https": self.url
        }
    
    def mark_failure(self) -> None:
        """Increment the failure counter for this proxy."""
        self.failures += 1
    
    def reset_failures(self) -> None:
        """Reset the failure counter after successful use."""
        self.failures = 0
    
    def mark_used(self) -> None:
        """Update the last used timestamp to the current time."""
        self.last_used = time.time()


class ProxyRotator:
    """
    Proxy management system for rotating, health checking, and tracking proxies.
    """
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the proxy rotator with configuration settings.
        
        Args:
            config: Dictionary containing proxy configuration
        """
        self.config = config
        self.proxies: List[Proxy] = []
        self.current_index = 0
        self.rotation_interval = config.get("rotation_interval", 300)  # Default 5 minutes
        self.health_check_interval = config.get("health_check_interval", 60)  # Default 1 minute
        self.max_failures = config.get("max_failures", 3)
        self.connection_timeout = config.get("connection_timeout", 10)
        self.lock = threading.RLock()
        
        # Load proxies from environment variables
        self._load_proxies_from_env()
        
        # Start health check thread if we have proxies
        if self.proxies:
            self._start_health_check_thread()
    
    def _load_proxies_from_env(self) -> None:
        """
        Load proxy list from the PROXY_LIST environment variable.
        Format: ip1:port1:user1:pass1,ip2:port2:user2:pass2
        """
        proxy_list = os.environ.get("PROXY_LIST", "")
        if not proxy_list:
            logger.warning("No proxies found in environment variables.")
            return
            
        for proxy_str in proxy_list.split(","):
            parts = proxy_str.strip().split(":")
            if len(parts) >= 2:
                try:
                    ip = parts[0]
                    port = int(parts[1])
                    username = parts[2] if len(parts) > 2 else None
                    password = parts[3] if len(parts) > 3 else None
                    
                    self.proxies.append(Proxy(ip, port, username, password))
                    logger.info(f"Loaded proxy: {ip}:{port}")
                except (ValueError, IndexError) as e:
                    logger.error(f"Failed to parse proxy: {proxy_str}. Error: {e}")
    
    def _start_health_check_thread(self) -> None:
        """Start a background thread to periodically check proxy health."""
        def health_check_worker():
            while True:
                try:
                    self._check_all_proxies()
                except Exception as e:
                    logger.error(f"Error in health check thread: {e}")
                finally:
                    time.sleep(self.health_check_interval)
        
        thread = threading.Thread(target=health_check_worker, daemon=True)
        thread.start()
        logger.info("Started proxy health check thread")
    
    def _check_all_proxies(self) -> None:
        """Check the health of all proxies in the pool."""
        for proxy in self.proxies:
            try:
                # Use a simple GET request to test the proxy
                response = requests.get(
                    "https://www.google.com", 
                    proxies=proxy.dict_format,
                    timeout=self.connection_timeout
                )
                
                if response.status_code == 200:
                    with self.lock:
                        proxy.is_healthy = True
                        proxy.reset_failures()
                    logger.debug(f"Proxy {proxy.ip}:{proxy.port} is healthy")
                else:
                    logger.warning(f"Proxy {proxy.ip}:{proxy.port} returned status code {response.status_code}")
                    with self.lock:
                        proxy.mark_failure()
            except Exception as e:
                logger.warning(f"Proxy {proxy.ip}:{proxy.port} health check failed: {e}")
                with self.lock:
                    proxy.mark_failure()
            
            # Update health status based on failures
            with self.lock:
                if proxy.failures >= self.max_failures:
                    proxy.is_healthy = False
                    logger.error(f"Proxy {proxy.ip}:{proxy.port} marked unhealthy after {proxy.failures} failures")
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """
        Get the next available healthy proxy using a rotation strategy.
        
        Returns:
            Dictionary containing proxy settings or None if no healthy proxies
        """
        if not self.proxies:
            return None
            
        with self.lock:
            # Filter only healthy proxies
            healthy_proxies = [p for p in self.proxies if p.is_healthy]
            
            if not healthy_proxies:
                logger.warning("No healthy proxies available")
                return None
            
            # Find a proxy that hasn't been used recently
            current_time = time.time()
            available_proxies = [
                p for p in healthy_proxies 
                if (current_time - p.last_used) > self.rotation_interval
            ]
            
            if not available_proxies:
                # If all proxies were recently used, pick a random healthy one
                proxy = random.choice(healthy_proxies)
            else:
                # Pick a random proxy from those not recently used
                proxy = random.choice(available_proxies)
            
            proxy.mark_used()
            logger.info(f"Using proxy: {proxy.ip}:{proxy.port}")
            return proxy.dict_format
    
    def mark_proxy_failure(self, proxy_url: str) -> None:
        """
        Mark a proxy as having failed a request.
        
        Args:
            proxy_url: The URL of the proxy that failed
        """
        with self.lock:
            for proxy in self.proxies:
                if proxy.url in proxy_url:
                    proxy.mark_failure()
                    if proxy.failures >= self.max_failures:
                        proxy.is_healthy = False
                        logger.error(f"Proxy {proxy.ip}:{proxy.port} marked unhealthy after {proxy.failures} failures")
                    break
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current status of all proxies.
        
        Returns:
            Dictionary with proxy pool statistics
        """
        with self.lock:
            total = len(self.proxies)
            healthy = sum(1 for p in self.proxies if p.is_healthy)
            
            return {
                "total_proxies": total,
                "healthy_proxies": healthy,
                "unhealthy_proxies": total - healthy,
                "proxies": [
                    {
                        "ip": p.ip,
                        "port": p.port,
                        "is_healthy": p.is_healthy,
                        "failures": p.failures,
                        "last_used": p.last_used
                    }
                    for p in self.proxies
                ]
            }
