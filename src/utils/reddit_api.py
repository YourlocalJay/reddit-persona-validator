"""
Reddit API client with OAuth2 authentication.

This module provides a wrapper for the Reddit API using OAuth2 authentication,
enabling deeper data extraction for behavioral analysis.

References:
    - Reddit API Documentation: https://www.reddit.com/dev/api/
    - OAuth2 Specification: https://oauth.net/2/
"""

import time
import logging
import base64
import json
import hashlib
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Set, Union, cast
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import secrets
import webbrowser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class RedditOAuth2Error(Exception):
    """Exception for Reddit OAuth2 authentication errors."""
    pass

class RedditAPIError(Exception):
    """Exception for Reddit API errors."""
    pass

class RedditRateLimitError(Exception):
    """Exception for Reddit API rate limit errors."""
    pass

class RedditOAuth2Client:
    """
    Reddit API client with OAuth2 authentication.
    
    Handles OAuth2 flow, token management, and API requests with:
    - Authorization code flow for user-context operations
    - Application-only flow for public data access
    - Token caching and refresh
    - Rate limit handling
    - Proxy support
    
    Usage:
        # Initialize with client credentials
        client = RedditOAuth2Client(
            client_id="your_client_id",
            client_secret="your_client_secret",
            redirect_uri="http://localhost:8000/callback",
            user_agent="MyApp/1.0"
        )
        
        # User context authentication
        auth_url = client.get_authorization_url(scopes=["identity", "read"])
        # User opens auth_url and authorizes the app
        # App receives code from redirect
        client.authenticate_with_code(code="received_code")
        
        # Application-only authentication
        client.authenticate_app_only()
        
        # Make API requests
        me = client.get("/api/v1/me")
        user_data = client.get(f"/user/{username}/about")
    """
    
    TOKEN_ENDPOINT = "https://www.reddit.com/api/v1/access_token"
    AUTHORIZE_ENDPOINT = "https://www.reddit.com/api/v1/authorize"
    API_BASE_URL = "https://oauth.reddit.com"
    UNAUTHENTICATED_API_BASE_URL = "https://www.reddit.com"
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: Optional[str] = None,
        user_agent: Optional[str] = None,
        token_cache_path: Optional[str] = None,
        proxy_url: Optional[str] = None,
    ):
        """
        Initialize the Reddit OAuth2 client.
        
        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            redirect_uri: Redirect URI for authorization code flow
            user_agent: User agent for API requests
            token_cache_path: Path to token cache file
            proxy_url: Optional proxy URL (e.g., http://user:pass@host:port)
            
        Raises:
            ValueError: If required parameters are missing
        """
        if not client_id or not client_secret:
            raise ValueError("Client ID and client secret are required")
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.user_agent = user_agent or f"RedditPersonaValidator/1.0"
        self.proxy_url = proxy_url
        
        # Default token cache
        if token_cache_path:
            self.token_cache_path = Path(token_cache_path)
        else:
            cache_dir = Path(".cache/reddit_tokens")
            cache_dir.mkdir(parents=True, exist_ok=True)
            self.token_cache_path = cache_dir / "token_cache.json"
        
        # Token state
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.token_type: Optional[str] = None
        self.authenticated_user: Optional[str] = None
        self.authenticated_scopes: Set[str] = set()
        self.is_app_only = False
        
        # Session configuration
        self.session = self._create_session()
        
        # Load cached token if available
        self._load_token_from_cache()
        
        logger.info(f"Reddit OAuth2 client initialized (app-only: {self.is_app_only})")
    
    def _create_session(self) -> requests.Session:
        """
        Create a requests Session with retry configuration.
        
        Returns:
            Configured requests.Session
        """
        session = requests.Session()
        
        # Configure retries
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        # Configure proxies if provided
        if self.proxy_url:
            session.proxies = {
                "http": self.proxy_url,
                "https": self.proxy_url
            }
        
        # Set default headers
        session.headers.update({
            "User-Agent": self.user_agent
        })
        
        return session
    
    def _load_token_from_cache(self) -> bool:
        """
        Load authentication token from cache.
        
        Returns:
            True if token loaded successfully, False otherwise
        """
        if not self.token_cache_path.exists():
            return False
            
        try:
            with open(self.token_cache_path, 'r') as f:
                token_data = json.load(f)
                
            # Validate required fields
            if not all(k in token_data for k in ["access_token", "expires_at"]):
                logger.warning("Invalid token cache, missing required fields")
                return False
                
            # Load token data
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token")
            self.token_type = token_data.get("token_type", "bearer")
            self.authenticated_user = token_data.get("authenticated_user")
            self.authenticated_scopes = set(token_data.get("scopes", []))
            self.is_app_only = token_data.get("is_app_only", False)
            
            # Parse expiry
            if "expires_at" in token_data:
                self.token_expiry = datetime.fromisoformat(token_data["expires_at"])
                
                # Check if token is still valid
                if self.token_expiry <= datetime.now():
                    logger.info("Cached token expired, will need to refresh")
                    return False
            
            logger.info(f"Loaded cached token (app-only: {self.is_app_only})")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load token from cache: {str(e)}")
            return False
    
    def _save_token_to_cache(self) -> None:
        """
        Save current authentication token to cache.
        """
        if not self.access_token or not self.token_expiry:
            return
            
        try:
            token_data = {
                "access_token": self.access_token,
                "refresh_token": self.refresh_token,
                "token_type": self.token_type,
                "expires_at": self.token_expiry.isoformat(),
                "authenticated_user": self.authenticated_user,
                "scopes": list(self.authenticated_scopes),
                "is_app_only": self.is_app_only
            }
            
            os.makedirs(os.path.dirname(self.token_cache_path), exist_ok=True)
            with open(self.token_cache_path, 'w') as f:
                json.dump(token_data, f)
                
            logger.debug("Token saved to cache")
            
        except Exception as e:
            logger.warning(f"Failed to save token to cache: {str(e)}")
    
    def get_authorization_url(
        self, 
        scopes: List[str] = None,
        state: Optional[str] = None,
        duration: str = "permanent"
    ) -> Tuple[str, str]:
        """
        Generate an authorization URL for the user to authorize the application.
        
        Args:
            scopes: List of permission scopes to request
            state: Optional state parameter for CSRF protection
            duration: Token duration ("temporary" or "permanent")
            
        Returns:
            Tuple of (authorization_url, state)
            
        Raises:
            ValueError: If redirect_uri is not set
        """
        if not self.redirect_uri:
            raise ValueError("redirect_uri is required for authorization flow")
        
        # Default scopes if none provided
        if not scopes:
            scopes = ["identity", "read"]
            
        # Generate state for CSRF protection if not provided
        if not state:
            state = secrets.token_urlsafe(32)
            
        # Build authorization URL
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": self.redirect_uri,
            "duration": duration,
            "scope": " ".join(scopes)
        }
        
        auth_url = f"{self.AUTHORIZE_ENDPOINT}?"
        auth_url += "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
        
        logger.info(f"Generated authorization URL with scopes: {scopes}")
        return auth_url, state
    
    def authenticate_with_code(self, code: str) -> Dict[str, Any]:
        """
        Complete OAuth2 flow by exchanging authorization code for access token.
        
        Args:
            code: Authorization code from redirect
            
        Returns:
            Dict containing token information
            
        Raises:
            RedditOAuth2Error: If authentication fails
        """
        if not self.redirect_uri:
            raise RedditOAuth2Error("redirect_uri is required for authorization code flow")
        
        try:
            # Create Basic Auth header
            auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            
            # Set up the token request
            headers = {
                "Authorization": f"Basic {auth}",
                "User-Agent": self.user_agent
            }
            
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri
            }
            
            # Make the token request
            response = self.session.post(
                self.TOKEN_ENDPOINT,
                headers=headers,
                data=data
            )
            
            # Handle response
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        error_detail = f"{error_json.get('error')}: {error_json.get('error_description', '')}"
                except:
                    pass
                    
                raise RedditOAuth2Error(f"Authentication failed: {error_detail}")
            
            # Parse token response
            token_data = response.json()
            self._process_token_response(token_data, is_app_only=False)
            
            logger.info("Successfully authenticated with authorization code")
            return token_data
            
        except requests.RequestException as e:
            raise RedditOAuth2Error(f"Request failed during authentication: {str(e)}")
    
    def authenticate_app_only(self) -> Dict[str, Any]:
        """
        Authenticate using application-only OAuth2 flow.
        
        Returns:
            Dict containing token information
            
        Raises:
            RedditOAuth2Error: If authentication fails
        """
        try:
            # Create Basic Auth header
            auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            
            # Set up the token request
            headers = {
                "Authorization": f"Basic {auth}",
                "User-Agent": self.user_agent
            }
            
            data = {
                "grant_type": "client_credentials"
            }
            
            # Make the token request
            response = self.session.post(
                self.TOKEN_ENDPOINT,
                headers=headers,
                data=data
            )
            
            # Handle response
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        error_detail = f"{error_json.get('error')}: {error_json.get('error_description', '')}"
                except:
                    pass
                    
                raise RedditOAuth2Error(f"App-only authentication failed: {error_detail}")
            
            # Parse token response
            token_data = response.json()
            self._process_token_response(token_data, is_app_only=True)
            
            logger.info("Successfully authenticated with app-only flow")
            return token_data
            
        except requests.RequestException as e:
            raise RedditOAuth2Error(f"Request failed during app-only authentication: {str(e)}")
    
    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh the access token using the refresh token.
        
        Returns:
            Dict containing new token information
            
        Raises:
            RedditOAuth2Error: If refresh fails or no refresh token is available
        """
        if not self.refresh_token:
            if self.is_app_only:
                # App-only authentication doesn't use refresh tokens
                return self.authenticate_app_only()
            else:
                raise RedditOAuth2Error("No refresh token available")
        
        try:
            # Create Basic Auth header
            auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
            
            # Set up the token request
            headers = {
                "Authorization": f"Basic {auth}",
                "User-Agent": self.user_agent
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token
            }
            
            # Make the token request
            response = self.session.post(
                self.TOKEN_ENDPOINT,
                headers=headers,
                data=data
            )
            
            # Handle response
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    if "error" in error_json:
                        error_detail = f"{error_json.get('error')}: {error_json.get('error_description', '')}"
                except:
                    pass
                    
                raise RedditOAuth2Error(f"Token refresh failed: {error_detail}")
            
            # Parse token response
            token_data = response.json()
            self._process_token_response(token_data, is_app_only=False)
            
            logger.info("Successfully refreshed access token")
            return token_data
            
        except requests.RequestException as e:
            raise RedditOAuth2Error(f"Request failed during token refresh: {str(e)}")
    
    def _process_token_response(self, token_data: Dict[str, Any], is_app_only: bool) -> None:
        """
        Process and store token data from OAuth2 response.
        
        Args:
            token_data: Token response from Reddit API
            is_app_only: Whether this is an application-only token
        """
        if "access_token" not in token_data:
            raise RedditOAuth2Error("Invalid token response: missing access_token")
        
        self.access_token = token_data["access_token"]
        self.token_type = token_data.get("token_type", "bearer")
        
        # Store refresh token if provided
        if "refresh_token" in token_data:
            self.refresh_token = token_data["refresh_token"]
        
        # Calculate token expiry
        expires_in = int(token_data.get("expires_in", 3600))
        self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
        
        # Store authentication scope
        if "scope" in token_data:
            scope_str = token_data["scope"]
            self.authenticated_scopes = set(s.strip() for s in scope_str.split() if s.strip())
        
        # Store app-only flag
        self.is_app_only = is_app_only
        
        # Save token to cache
        self._save_token_to_cache()
    
    def _ensure_authenticated(self) -> None:
        """
        Ensure the client has a valid access token.
        
        Attempts to refresh the token if expired, or falls back to app-only auth.
        
        Raises:
            RedditOAuth2Error: If authentication fails
        """
        # Check if token is valid
        if (
            self.access_token and 
            self.token_expiry and 
            self.token_expiry > datetime.now() + timedelta(minutes=5)
        ):
            return
        
        logger.debug("Access token expired or missing, attempting to refresh")
        
        # Try to refresh token
        if self.refresh_token:
            try:
                self.refresh_access_token()
                return
            except RedditOAuth2Error as e:
                logger.warning(f"Failed to refresh token: {str(e)}")
        
        # Fall back to app-only auth
        if not self.is_app_only:
            logger.info("Falling back to app-only authentication")
            self.authenticate_app_only()
        else:
            # Re-authenticate app-only
            self.authenticate_app_only()
    
    def get(
        self, 
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        authenticated: bool = True,
        raw_response: bool = False
    ) -> Any:
        """
        Make a GET request to the Reddit API.
        
        Args:
            endpoint: API endpoint (starting with /)
            params: Optional query parameters
            authenticated: Whether to use authentication
            raw_response: Whether to return the raw response object
            
        Returns:
            JSON response data or raw response if raw_response=True
            
        Raises:
            RedditAPIError: If the API request fails
            RedditRateLimitError: If rate limited
        """
        return self._request("GET", endpoint, params=params, authenticated=authenticated, raw_response=raw_response)
    
    def post(
        self, 
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        authenticated: bool = True,
        raw_response: bool = False
    ) -> Any:
        """
        Make a POST request to the Reddit API.
        
        Args:
            endpoint: API endpoint (starting with /)
            data: Optional form data
            json_data: Optional JSON data
            authenticated: Whether to use authentication
            raw_response: Whether to return the raw response object
            
        Returns:
            JSON response data or raw response if raw_response=True
            
        Raises:
            RedditAPIError: If the API request fails
            RedditRateLimitError: If rate limited
        """
        return self._request(
            "POST", 
            endpoint, 
            data=data, 
            json_data=json_data, 
            authenticated=authenticated, 
            raw_response=raw_response
        )
    
    def _request(
        self, 
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        authenticated: bool = True,
        raw_response: bool = False
    ) -> Any:
        """
        Make a request to the Reddit API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (starting with /)
            params: Optional query parameters
            data: Optional form data
            json_data: Optional JSON data
            authenticated: Whether to use authentication
            raw_response: Whether to return the raw response object
            
        Returns:
            JSON response data or raw response if raw_response=True
            
        Raises:
            RedditAPIError: If the API request fails
            RedditRateLimitError: If rate limited
        """
        if authenticated:
            self._ensure_authenticated()
            base_url = self.API_BASE_URL
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
        else:
            base_url = self.UNAUTHENTICATED_API_BASE_URL
            headers = {}
        
        # Ensure endpoint starts with /
        if not endpoint.startswith('/'):
            endpoint = f"/{endpoint}"
        
        url = f"{base_url}{endpoint}"
        
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                data=data,
                json=json_data,
                headers=headers
            )
            
            # Check for rate limiting
            remaining = response.headers.get("X-Ratelimit-Remaining")
            used = response.headers.get("X-Ratelimit-Used")
            reset = response.headers.get("X-Ratelimit-Reset")
            
            if remaining is not None and used is not None:
                remaining = float(remaining)
                if remaining < 1:
                    reset_time = int(reset) if reset else 600
                    logger.warning(f"Rate limit exceeded. Reset in {reset_time} seconds")
                    raise RedditRateLimitError(
                        f"Rate limit exceeded. Reset in {reset_time} seconds. Used: {used}, Remaining: {remaining}"
                    )
            
            # Check for successful response
            if not response.ok:
                error_message = f"API request failed: {response.status_code} - {response.text}"
                logger.error(error_message)
                
                # Try to parse error details
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_detail = f"{error_data.get('error')}: {error_data.get('error_description', '')}"
                        error_message = f"API request failed: {response.status_code} - {error_detail}"
                except:
                    pass
                    
                raise RedditAPIError(error_message)
            
            # Return raw response if requested
            if raw_response:
                return response
            
            # Parse JSON response
            try:
                return response.json()
            except ValueError:
                # Some endpoints return empty responses or non-JSON content
                return response.text
                
        except requests.RequestException as e:
            raise RedditAPIError(f"Request failed: {str(e)}")
    
    def get_user_profile(self, username: str, include_comments: bool = True, include_posts: bool = True, limit: int = 25) -> Dict[str, Any]:
        """
        Get comprehensive profile data for a Reddit user.
        
        Args:
            username: Reddit username
            include_comments: Whether to include user comments
            include_posts: Whether to include user posts
            limit: Number of items to fetch for comments and posts
            
        Returns:
            Dict containing user profile data
        """
        result = {
            "username": username,
            "profile": None,
            "comments": [],
            "posts": [],
            "metadata": {
                "fetched_at": datetime.now().isoformat(),
                "comment_count": 0,
                "post_count": 0
            }
        }
        
        try:
            # Get user profile
            profile = self.get(f"/user/{username}/about", authenticated=True)
            result["profile"] = profile.get("data", {})
            
            # Get user comments
            if include_comments:
                comments = self.get(
                    f"/user/{username}/comments",
                    params={"limit": limit, "sort": "new"},
                    authenticated=True
                )
                
                if "data" in comments and "children" in comments["data"]:
                    result["comments"] = [child["data"] for child in comments["data"]["children"]]
                    result["metadata"]["comment_count"] = len(result["comments"])
            
            # Get user posts
            if include_posts:
                posts = self.get(
                    f"/user/{username}/submitted",
                    params={"limit": limit, "sort": "new"},
                    authenticated=True
                )
                
                if "data" in posts and "children" in posts["data"]:
                    result["posts"] = [child["data"] for child in posts["data"]["children"]]
                    result["metadata"]["post_count"] = len(result["posts"])
            
            return result
            
        except (RedditAPIError, RedditRateLimitError) as e:
            logger.error(f"Failed to get user profile for {username}: {str(e)}")
            result["error"] = str(e)
            return result
    
    def get_user_engagement_metrics(self, username: str) -> Dict[str, Any]:
        """
        Calculate user engagement metrics based on post and comment history.
        
        Args:
            username: Reddit username
            
        Returns:
            Dict containing engagement metrics
        """
        try:
            # Get user profile data
            profile_data = self.get_user_profile(
                username=username,
                include_comments=True,
                include_posts=True,
                limit=100
            )
            
            if "error" in profile_data:
                return {"error": profile_data["error"]}
            
            # Calculate engagement metrics
            comments = profile_data.get("comments", [])
            posts = profile_data.get("posts", [])
            
            # Comment metrics
            comment_karma = sum(c.get("score", 0) for c in comments)
            comment_subreddits = [c.get("subreddit", "") for c in comments]
            comment_sub_distribution = {}
            for sub in comment_subreddits:
                comment_sub_distribution[sub] = comment_sub_distribution.get(sub, 0) + 1
            
            # Post metrics
            post_karma = sum(p.get("score", 0) for p in posts)
            post_subreddits = [p.get("subreddit", "") for p in posts]
            post_sub_distribution = {}
            for sub in post_subreddits:
                post_sub_distribution[sub] = post_sub_distribution.get(sub, 0) + 1
            
            # Calculate time distribution
            def extract_time_of_day(timestamp):
                dt = datetime.fromtimestamp(timestamp)
                hour = dt.hour
                if 5 <= hour < 12:
                    return "morning"
                elif 12 <= hour < 17:
                    return "afternoon"
                elif 17 <= hour < 22:
                    return "evening"
                else:
                    return "night"
            
            comment_times = [c.get("created_utc", 0) for c in comments]
            post_times = [p.get("created_utc", 0) for p in posts]
            
            time_distribution = {
                "morning": 0,
                "afternoon": 0,
                "evening": 0,
                "night": 0
            }
            
            for timestamp in comment_times + post_times:
                time_of_day = extract_time_of_day(timestamp)
                time_distribution[time_of_day] += 1
            
            # Calculate activity consistency
            timestamps = sorted(comment_times + post_times)
            activity_gaps = []
            for i in range(1, len(timestamps)):
                gap = timestamps[i] - timestamps[i-1]
                activity_gaps.append(gap / 3600)  # Gap in hours
            
            consistency_score = 0
            if activity_gaps:
                avg_gap = sum(activity_gaps) / len(activity_gaps)
                gap_variance = sum((g - avg_gap) ** 2 for g in activity_gaps) / len(activity_gaps)
                # Lower variance means more consistent posting pattern
                consistency_score = 100 / (1 + gap_variance / 100)
                consistency_score = min(100, max(0, consistency_score))
            
            return {
                "username": username,
                "activity_summary": {
                    "total_comments": len(comments),
                    "total_posts": len(posts),
                    "comment_karma": comment_karma,
                    "post_karma": post_karma,
                    "total_karma": comment_karma + post_karma,
                    "comment_to_post_ratio": len(comments) / max(1, len(posts)),
                    "active_subreddits": len(set(comment_subreddits + post_subreddits))
                },
                "engagement_patterns": {
                    "time_distribution": time_distribution,
                    "top_subreddits_by_comments": dict(sorted(
                        comment_sub_distribution.items(), 
                        key=lambda x: x[1], 
                        reverse=True
                    )[:5]),
                    "top_subreddits_by_posts": dict(sorted(
                        post_sub_distribution.items(), 
                        key=lambda x: x[1], 
                        reverse=True
                    )[:5]),
                    "consistency_score": round(consistency_score, 2)
                },
                "metadata": {
                    "sample_size": len(comments) + len(posts),
                    "fetched_at": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate engagement metrics for {username}: {str(e)}")
            return {"error": str(e)}
    
    def close(self) -> None:
        """Close the session and clean up resources."""
        self.session.close()
        logger.debug("Reddit OAuth2 client session closed")
