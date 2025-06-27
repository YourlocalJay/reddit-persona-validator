"""
Proxy rotation utility with health checks and intelligent failover.
"""

import os
import time
import logging
import random
import threading
import requests
from typing import Dict, Optional, List, Tuple, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class Proxy:
    """
    Representation of a single proxy with health tracking and performance metrics.
    """
    def __init__(self, ip: str, port: int, 
                 username: Optional[str] = None, 
                 password: Optional[str] = None,
                 protocol: str = "http"):
        """
        Initialize a proxy instance with connection details and metrics.
        
        Args:
            ip: Proxy IP address or hostname
            port: Proxy port number
            username: Auth username (optional)
            password: Auth password (optional)
            protocol: Proxy protocol (http/https/socks5)
        """
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.protocol = protocol
        self.failures = 0
        self.successes = 0
        self.last_used = 0
        self.last_response_time = 0
        self.is_healthy = True
        self.blacklist_until = 0
    
    @property
    def url(self) -> str:
        """Get formatted proxy URL."""
        auth = f"{self.username}:{self.password}@" if self.username and self.password else ""
        return f"{self.protocol}://{auth}{self.ip}:{self.port}"
    
    @property
    def dict_format(self) -> Dict[str, str]:
        """Get proxy in requests-compatible format."""
        return {
            "http": self.url,
            "https": self.url
        }
    
    def mark_failure(self) -> None:
        """Record a failed request."""
        self.failures += 1
        self.successes = max(0, self.successes - 0.5)
    
    def mark_success(self, response_time: float) -> None:
        """Record a successful request."""
        self.successes += 1
        self.last_response_time = response_time
        if self.failures > 0:
            self.failures -= 0.2  # Gradual recovery
    
    def mark_used(self) -> None:
        """Update last used timestamp."""
        self.last_used = time.time()
    
    def should_use(self, min_success_rate: float = 0.7) -> bool:
        """Determine if proxy meets usage criteria."""
        total_attempts = self.failures + self.successes
        success_rate = self.successes / total_attempts if total_attempts > 0 else 1.0
        return (self.is_healthy and 
                time.time() > self.blacklist_until and
                success_rate >= min_success_rate)

    def blacklist(self, duration: int = 300) -> None:
        """Temporarily blacklist this proxy."""
        self.blacklist_until = time.time() + duration
        logger.warning(f"Blacklisted proxy {self.ip}:{self.port} for {duration}s")


class ProxyRotator:
    """
    Intelligent proxy rotation system with health monitoring and performance-based selection.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize proxy rotator with configuration.
        
        Args:
            config: {
                "rotation_interval": 300,
                "health_check_interval": 60,
                "max_failures": 3,
                "connection_timeout": 10,
                "health_check_url": "https://www.google.com",
                "success_rate_threshold": 0.7,
                "blacklist_duration": 300
            }
        """
        self.config = config or {}
        self.proxies: List[Proxy] = []
        self.lock = threading.RLock()
        self.health_check_url = self.config.get("health_check_url", "https://www.google.com")
        self.health_check_thread = None
        
        self._load_proxies()
        if self.proxies:
            self._start_health_check_thread()
    
    def _load_proxies(self) -> None:
        """Load proxies from multiple sources."""
        # 1. Load from environment variable
        env_proxies = os.getenv("PROXY_LIST", "")
        if env_proxies:
            self._parse_proxy_list(env_proxies.split(","))
        
        # 2. Load from config file if specified
        if not self.proxies and self.config.get("proxy_config_file"):
            try:
                with open(self.config["proxy_config_file"]) as f:
                    proxy_lines = [line.strip() for line in f if line.strip()]
                self._parse_proxy_list(proxy_lines)
            except Exception as e:
                logger.error(f"Failed to load proxy config: {e}")
    
    def _parse_proxy_list(self, proxy_strings: List[str]) -> None:
        """Parse proxy strings into Proxy objects."""
        for proxy_str in proxy_strings:
            try:
                # Handle full URL format (http://user:pass@host:port)
                if proxy_str.startswith(("http://", "https://", "socks5://")):
                    parsed = urlparse(proxy_str)
                    protocol = parsed.scheme
                    auth = parsed.netloc.split("@")[0] if "@" in parsed.netloc else None
                    host_port = parsed.netloc.split("@")[-1].split(":")
                    ip = host_port[0]
                    port = int(host_port[1]) if len(host_port) > 1 else 8080
                    username, password = (auth.split(":") if auth else (None, None))
                else:
                    # Handle ip:port:user:pass format
                    parts = proxy_str.split(":")
                    ip = parts[0]
                    port = int(parts[1]) if len(parts) > 1 else 8080
                    username = parts[2] if len(parts) > 2 else None
                    password = parts[3] if len(parts) > 3 else None
                    protocol = "http"
                
                self.proxies.append(Proxy(
                    ip=ip,
                    port=port,
                    username=username,
                    password=password,
                    protocol=protocol
                ))
                logger.info(f"Loaded proxy: {ip}:{port}")
            except Exception as e:
                logger.error(f"Failed to parse proxy '{proxy_str}': {e}")
    
    def _start_health_check_thread(self) -> None:
        """Start background health monitoring."""
        def health_check_worker():
            while True:
                try:
                    self._perform_health_checks()
                    time.sleep(self.config.get("health_check_interval", 60))
                except Exception as e:
                    logger.error(f"Health check thread error: {e}")
                    time.sleep(30)  # Recoverable error delay
        
        self.health_check_thread = threading.Thread(
            target=health_check_worker,
            daemon=True,
            name="ProxyHealthCheck"
        )
        self.health_check_thread.start()
        logger.info("Started proxy health monitoring")
    
    def _perform_health_checks(self) -> None:
        """Check all proxies' health status."""
        check_url = self.health_check_url
        timeout = self.config.get("connection_timeout", 10)
        
        for proxy in self.proxies:
            try:
                start_time = time.time()
                response = requests.get(
                    check_url,
                    proxies=proxy.dict_format,
                    timeout=timeout,
                    headers={"User-Agent": "ProxyHealthCheck/1.0"}
                )
                response_time = time.time() - start_time
                
                if response.ok:
                    with self.lock:
                        proxy.mark_success(response_time)
                        proxy.is_healthy = True
                    logger.debug(f"Proxy {proxy.ip}:{proxy.port} healthy (RT: {response_time:.2f}s)")
                else:
                    with self.lock:
                        proxy.mark_failure()
                    logger.warning(f"Proxy {proxy.ip}:{proxy.port} failed with status {response.status_code}")
            except Exception as e:
                with self.lock:
                    proxy.mark_failure()
                logger.warning(f"Proxy {proxy.ip}:{proxy.port} health check failed: {str(e)}")
            
            # Evaluate health status
            with self.lock:
                if (proxy.failures >= self.config.get("max_failures", 3) or 
                    not proxy.should_use(self.config.get("success_rate_threshold", 0.7))):
                    proxy.is_healthy = False
    
    def get_proxy(self, strategy: str = "balanced") -> Optional[Dict[str, str]]:
        """
        Get next proxy based on selection strategy.
        
        Args:
            strategy: "balanced" (default), "fastest", "random", "round_robin"
        
        Returns:
            Proxy dictionary or None if no proxies available
        """
        if not self.proxies:
            return None
            
        with self.lock:
            # Get eligible proxies
            eligible = [p for p in self.proxies if p.should_use()]
            
            if not eligible:
                logger.warning("No eligible proxies available")
                return None
            
            # Apply selection strategy
            if strategy == "fastest":
                proxy = min(eligible, key=lambda p: p.last_response_time)
            elif strategy == "random":
                proxy = random.choice(eligible)
            elif strategy == "round_robin":
                # Simple round-robin implementation
                proxy = eligible[0]
                self.proxies.append(self.proxies.pop(0))
            else:  # balanced (default)
                # Weighted random based on performance
                weights = [
                    (p.successes / (p.failures + p.successes + 1)) * 
                    (1 / (p.last_response_time + 0.1))
                    for p in eligible
                ]
                proxy = random.choices(eligible, weights=weights, k=1)[0]
            
            proxy.mark_used()
            logger.info(f"Selected proxy: {proxy.ip}:{proxy.port} (Strategy: {strategy})")
            return proxy.dict_format
    
    def report_result(self, proxy_url: str, success: bool, response_time: float = 0) -> None:
        """
        Report usage result back to rotator.
        
        Args:
            proxy_url: The proxy URL that was used
            success: Whether the request succeeded
            response_time: Response time in seconds
        """
        with self.lock:
            for proxy in self.proxies:
                if proxy.url == proxy_url:
                    if success:
                        proxy.mark_success(response_time)
                    else:
                        proxy.mark_failure()
                        if proxy.failures >= self.config.get("max_failures", 3):
                            proxy.blacklist(self.config.get("blacklist_duration", 300))
                    break
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current proxy pool status.
        
        Returns:
            Dictionary with detailed proxy metrics
        """
        with self.lock:
            now = time.time()
            healthy = [p for p in self.proxies if p.is_healthy]
            
            return {
                "total_proxies": len(self.proxies),
                "healthy_proxies": len(healthy),
                "unhealthy_proxies": len(self.proxies) - len(healthy),
                "blacklisted_proxies": sum(1 for p in self.proxies if p.blacklist_until > now),
                "avg_response_time": (
                    sum(p.last_response_time for p in healthy) / len(healthy) 
                    if healthy else 0
                ),
                "success_rate": (
                    sum(p.successes for p in self.proxies) / 
                    sum(p.successes + p.failures for p in self.proxies)
                    if any(p.successes + p.failures > 0 for p in self.proxies) 
                    else 1.0
                ),
                "proxies": [
                    {
                        "url": p.url,
                        "status": (
                            "blacklisted" if p.blacklist_until > now else
                            "healthy" if p.is_healthy else
                            "unhealthy"
                        ),
                        "successes": p.successes,
                        "failures": p.failures,
                        "success_rate": (
                            p.successes / (p.successes + p.failures) 
                            if p.successes + p.failures > 0 else 1.0
                        ),
                        "last_response_time": p.last_response_time,
                        "last_used": p.last_used,
                        "blacklisted_until": (
                            p.blacklist_until if p.blacklist_until > now else None
                        )
                    }
                    for p in self.proxies
                ]
            }


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Sample configuration
    config = {
        "rotation_interval": 60,
        "health_check_interval": 30,
        "max_failures": 2,
        "connection_timeout": 5,
        "health_check_url": "https://httpbin.org/get",
        "success_rate_threshold": 0.6,
        "blacklist_duration": 120
    }
    
    rotator = ProxyRotator(config)
    
    # Simulate usage
    for i in range(5):
        proxy = rotator.get_proxy(strategy="balanced")
        if proxy:
            print(f"Using proxy: {proxy['http']}")
            try:
                start = time.time()
                response = requests.get(
                    "https://httpbin.org/ip",
                    proxies=proxy,
                    timeout=5
                )
                response_time = time.time() - start
                print(f"Success! Response: {response.json()}, Time: {response_time:.2f}s")
                rotator.report_result(proxy['http'], True, response_time)
            except Exception as e:
                print(f"Request failed: {e}")
                rotator.report_result(proxy['http'], False)
        
        print("\nCurrent status:")
        print(rotator.get_status())
        time.sleep(1)
