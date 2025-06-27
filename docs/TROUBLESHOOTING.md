# Troubleshooting Guide

This document covers common issues and their solutions when using the Reddit Persona Validator.

## Installation Issues

### Python Version

**Issue**: Error about incompatible Python version.

**Solution**: Ensure you're using Python 3.10 or higher:
```bash
python --version  # Should be 3.10.x or higher
```

If you have multiple Python versions, use the specific version:
```bash
python3.10 -m venv venv
```

### Dependency Errors

**Issue**: Errors during pip install about missing system dependencies.

**Solution**: Install required system packages:

On Ubuntu/Debian:
```bash
sudo apt-get update
sudo apt-get install python3-dev build-essential libssl-dev libffi-dev
```

On macOS:
```bash
brew install openssl
```

Then try installation again:
```bash
pip install -r requirements.txt
```

## Runtime Issues

### Browser Automation

**Issue**: Browser doesn't start or crashes immediately.

**Solution**: Ensure you have the latest Chrome installed, then try:

1. Clear cached browser data:
```bash
rm -rf ~/.cache/undetected_chromedriver/
```

2. Check your config for correct timeouts:
```yaml
reddit:
  request_timeout: 30  # Increase this value if needed
```

### CAPTCHA Handling

**Issue**: Getting stuck on CAPTCHA screens.

**Solution**:

1. Use more "aged" proxies that are less likely to trigger CAPTCHAs
2. Increase CAPTCHA timeout in config:
```yaml
reddit:
  captcha_timeout: 60  # Increase from default 45
```
3. Ensure your proxies are correctly configured with authentication if needed

### Email Verification

**Issue**: Cannot connect to Hotmail IMAP server.

**Solution**:

1. Check your credentials in .env file
2. Ensure less secure app access is enabled for your test account
3. Try increasing connection timeout:
```yaml
email:
  connection_timeout: 60  # Increase from default 30
```

### Proxy Issues

**Issue**: All proxies failing health checks.

**Solution**:

1. Verify proxy format in .env file:
```
PROXY_LIST=ip1:port1:user1:pass1,ip2:port2:user2:pass2
```

2. Test proxies manually:
```bash
curl -x http://user:pass@ip:port https://www.reddit.com
```

3. Adjust health check parameters:
```yaml
proxy:
  health_check_interval: 120  # Increase from default 60
  max_failures: 5             # Increase from default 3
```

## Interface-Specific Issues

### GUI

**Issue**: GUI doesn't display or shows blank window.

**Solution**:

1. If using Docker, ensure X11 forwarding is set up correctly:
```yaml
volumes:
  - /tmp/.X11-unix:/tmp/.X11-unix
environment:
  - DISPLAY=${DISPLAY}
```

2. Try a different theme in config.yaml:
```yaml
interface:
  gui:
    theme: "SystemDefault"  # Change from DarkGrey9
```

### API

**Issue**: Cannot connect to API server.

**Solution**:

1. Check if the server is running:
```bash
ps aux | grep api.py
```

2. Verify port configuration:
```yaml
interface:
  api:
    port: 8000  # Make sure this matches your connection attempt
```

3. Ensure the host is correctly configured for network access:
```yaml
interface:
  api:
    host: "0.0.0.0"  # Allows external connections
```

## AI Analysis Issues

**Issue**: AI analysis failing or timing out.

**Solution**:

1. Check API keys in .env file
2. Increase timeouts in config.yaml:
```yaml
ai:
  deepseek:
    api_timeout: 120  # Increase from default 60
```

3. Try switching between providers (DeepSeek/Claude) if one is having issues

## Docker Issues

**Issue**: Container exits immediately after starting.

**Solution**:

Check logs:
```bash
docker logs <container_id>
```

Common fixes:
1. Ensure .env file is correctly mounted
2. Check for permission issues on mounted volumes
3. Verify environment variables are correctly set in compose.yml

## Still Having Problems?

If you continue to experience issues:

1. Check the logs for detailed error messages:
```bash
python src/interfaces/cli.py --log-level DEBUG
```

2. Create an issue on GitHub with:
   - Detailed description of the problem
   - Steps to reproduce
   - Relevant log output
   - Your environment (OS, Python version, etc.)
