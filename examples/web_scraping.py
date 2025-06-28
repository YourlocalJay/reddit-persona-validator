#!/usr/bin/env python3
"""
Example script demonstrating the use of ProxyLoader for web scraping.

This script shows how to use the ProxyLoader class to rotate between
proxies when making HTTP requests and handle proxy failures gracefully.
"""

import os
import sys
import time
import random
import logging
import argparse
import requests
from typing import Optional, List, Dict, Tuple
from pathlib import Path

# Add the parent directory to the sys.path to import from src/utils
sys.path.append(str(Path(__file__).parent.parent))
from src.utils.proxy_loader import ProxyLoader, NoProxiesAvailableError, AuthenticationError


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def make_request(
    url: str, 
    proxy: Optional[str] = None, 
    timeout: int = 10,
    max_retries: int = 3,
    retry_delay: int = 2
) -> Tuple[Optional[requests.Response], Optional[str]]:
    """
    Make an HTTP request with retry logic and proxy support.
    
    Args:
        url: URL to request
        proxy: Optional proxy URL to use
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        Tuple of (response object or None, error message or None)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
    }
    
    proxies = {"http": proxy, "https": proxy} if proxy else None
    
    for attempt in range(max_retries):
        try:
            logger.debug(f"Request attempt {attempt + 1}/{max_retries} to {url}")
            if proxy:
                logger.debug(f"Using proxy: {proxy}")
                
            response = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=timeout
            )
            
            # Check if the response indicates a proxy failure (common status codes)
            if response.status_code in (403, 407, 429, 502, 503, 504):
                logger.warning(f"Proxy may have failed: status code {response.status_code}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                    
            return response, None
            
        except requests.exceptions.ProxyError as e:
            logger.error(f"Proxy error: {str(e)}")
            error_msg = f"Proxy error: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
                
        except requests.exceptions.Timeout:
            logger.error(f"Request timed out after {timeout} seconds")
            error_msg = "Request timed out"
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            error_msg = f"Request exception: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
                
    return None, error_msg


def scrape_urls(
    urls: List[str], 
    proxy_loader: ProxyLoader,
    timeout: int = 10,
    max_retries: int = 3,
    rotate_on_failure: bool = True
) -> Dict[str, Dict]:
    """
    Scrape a list of URLs using proxies from the proxy loader.
    
    Args:
        urls: List of URLs to scrape
        proxy_loader: Initialized ProxyLoader instance
        timeout: Request timeout in seconds
        max_retries: Maximum retries per request
        rotate_on_failure: Whether to rotate proxies on failure
        
    Returns:
        Dictionary mapping URLs to their result information
    """
    results = {}
    
    for url in urls:
        logger.info(f"Scraping URL: {url}")
        
        # Get a proxy from the loader
        proxy = proxy_loader.get_next_proxy()
        if not proxy:
            logger.error("No proxies available")
            results[url] = {"success": False, "error": "No proxies available"}
            continue
            
        # Make the request
        response, error = make_request(url, proxy, timeout, max_retries)
        
        if response and response.status_code == 200:
            logger.info(f"Successfully scraped {url} (status: {response.status_code}, length: {len(response.text)} bytes)")
            results[url] = {
                "success": True,
                "status_code": response.status_code,
                "content_length": len(response.text),
                "proxy_used": proxy
            }
            
        else:
            logger.warning(f"Failed to scrape {url}: {error or f'Status code: {response.status_code if response else None}'}")
            
            # Blacklist the proxy if it failed
            if rotate_on_failure:
                logger.info(f"Blacklisting proxy due to failure: {proxy}")
                proxy_loader.blacklist_proxy(proxy)
                
                # If we've blacklisted too many proxies, reload the list
                if proxy_loader.get_proxy_count() < 2:
                    logger.warning("Running low on proxies, reloading proxy list")
                    try:
                        proxy_loader.reload_proxies()
                    except NoProxiesAvailableError:
                        logger.error("No more proxies available after reload")
            
            results[url] = {
                "success": False,
                "status_code": response.status_code if response else None,
                "error": error or f"Status code: {response.status_code}",
                "proxy_used": proxy
            }
            
        # Add a small delay between requests to avoid hammering the server
        time.sleep(random.uniform(1, 3))
        
    return results


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Web scraping example using proxy rotation")
    parser.add_argument("--urls", nargs="+", help="URLs to scrape")
    parser.add_argument("--url-file", help="File containing URLs to scrape (one per line)")
    parser.add_argument("--proxy-config", default="config/proxies.json", help="Path to proxy configuration file")
    parser.add_argument("--country", help="Filter proxies by country code")
    parser.add_argument("--timeout", type=int, default=10, help="Request timeout in seconds")
    parser.add_argument("--protocol", choices=["http", "https", "socks5"], default="http", help="Proxy protocol to use")
    args = parser.parse_args()
    
    # Get URLs from command line or file
    urls = []
    if args.urls:
        urls.extend(args.urls)
    if args.url_file:
        try:
            with open(args.url_file, 'r') as f:
                file_urls = [line.strip() for line in f if line.strip()]
                urls.extend(file_urls)
        except Exception as e:
            logger.error(f"Error reading URL file: {str(e)}")
            return 1
            
    if not urls:
        urls = [
            "https://httpbin.org/ip",
            "https://httpbin.org/user-agent",
            "https://httpbin.org/headers",
            "https://example.com"
        ]
        logger.info("No URLs provided, using default test URLs")
    
    # Initialize the proxy loader
    try:
        proxy_loader = ProxyLoader(args.proxy_config)
        proxy_loader.load_proxies(
            country_filter=args.country,
            protocol=args.protocol,
            shuffle=True
        )
        logger.info(f"Loaded {proxy_loader.get_proxy_count()} proxies")
    except (FileNotFoundError, PermissionError, ValueError, AuthenticationError) as e:
        logger.error(f"Failed to initialize proxy loader: {str(e)}")
        return 1
    except NoProxiesAvailableError as e:
        logger.error(f"No proxies available: {str(e)}")
        return 1
    
    # Scrape the URLs
    results = scrape_urls(
        urls=urls,
        proxy_loader=proxy_loader,
        timeout=args.timeout
    )
    
    # Print a summary
    logger.info("\nScraping Results Summary:")
    success_count = sum(1 for result in results.values() if result["success"])
    logger.info(f"Total URLs: {len(urls)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {len(urls) - success_count}")
    logger.info(f"Proxies used: {len(set(result['proxy_used'] for result in results.values()))}")
    logger.info(f"Proxies blacklisted: {proxy_loader.get_blacklisted_count()}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
