# Advanced Proxy Loader for Web Automation

A robust, feature-rich proxy management system designed for stealth web automation and scraping projects. Optimized for use with Oxylabs residential proxies but adaptable to any proxy provider.

## Features

- **Multiple Authentication Schemes**: Support for username/password authentication with optional customer prefixing
- **Smart Proxy Selection**: Filter proxies by country, datacenter, or IP version
- **Rotation Strategies**: Sequential or random proxy rotation
- **Proxy Health Management**: Automatic blacklisting of failed proxies
- **Comprehensive Logging**: Detailed logging for monitoring and debugging
- **Production-Ready Code**: Fully type-annotated with extensive documentation and unit tests

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YourlocalJay/reddit-persona-validator.git
   cd reddit-persona-validator
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure your environment variables:
   ```bash
   export OXYLABS_USERNAME="your_username"
   export OXYLABS_PASSWORD="your_password"
   export OXYLABS_CUSTOMER="your_customer_id"  # Optional
   ```

## Usage

### Basic Usage

```python
from src.utils.proxy_loader import ProxyLoader

# Initialize the proxy loader
loader = ProxyLoader("config/proxies.json")

# Load and filter proxies
proxies = loader.load_proxies(
    country_filter="US",  # Optional: filter by country
    protocol="http",      # Optional: http, https, or socks5
    shuffle=True          # Optional: randomize proxy order
)

# Get the next proxy in the rotation
proxy = loader.get_next_proxy()

# Use the proxy with your HTTP client
response = requests.get("https://example.com", proxies={"http": proxy, "https": proxy})
```

### Advanced Usage with Blacklisting

```python
from src.utils.proxy_loader import ProxyLoader, NoProxiesAvailableError

loader = ProxyLoader("config/proxies.json")
proxies = loader.load_proxies()

try:
    # Attempt to make a request with a proxy
    proxy = loader.get_next_proxy()
    response = make_request(url, proxy=proxy)
    
    # If the proxy is detected or blocked, blacklist it
    if response.status_code in (403, 407, 429, 502, 503, 504):
        loader.blacklist_proxy(proxy)
        
        # Get a new proxy and retry
        proxy = loader.get_next_proxy()
        response = make_request(url, proxy=proxy)
        
except Exception as e:
    # If an exception occurs, blacklist the proxy
    loader.blacklist_proxy(proxy)
    
    # If we're running low on proxies, reload the list
    if loader.get_proxy_count() < 3:
        try:
            loader.reload_proxies()
        except NoProxiesAvailableError:
            logger.error("No more proxies available")
```

### Example Web Scraper

Check out the [examples/web_scraping.py](examples/web_scraping.py) script for a complete example of how to use the proxy loader for web scraping with error handling and proxy rotation.

Run the example:

```bash
python examples/web_scraping.py --country US --protocol https
```

## Proxy Configuration

The proxy configuration file should be a JSON array of proxy objects. Each proxy object should have at least the following fields:

```json
[
  {
    "ip": "123.123.123.123",
    "port": 10000,
    "countryCode": "US",
    "dc": "dc1"
  },
  ...
]
```

Additional fields can be included for more advanced filtering:

```json
{
  "ip": "123.123.123.123",
  "port": 10000,
  "countryCode": "US",
  "dc": "dc1",
  "health": 100,
  "lastChecked": "2025-06-01T12:00:00Z",
  "tags": ["residential", "high-speed"]
}
```

## Testing

Run the unit tests:

```bash
pytest -xvs tests/test_proxy_loader.py
```

## License

MIT

## Disclaimer

This tool is intended for legitimate web automation and scraping purposes only. Always respect website terms of service, rate limits, and legal requirements when conducting web scraping activities.
