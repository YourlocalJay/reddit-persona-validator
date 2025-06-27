"""Base analyzer interface for AI-powered Reddit persona analysis."""

import abc
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import json
import backoff
from ratelimit import limits, sleep_and_retry

# Configure module logger
logger = logging.getLogger(__name__)

class BaseAnalyzer(abc.ABC):
    """
    Abstract base class defining the interface for all AI analyzers.
    
    This class provides a common interface for different AI analyzers to:
    1. Extract content from Reddit personas
    2. Analyze the content for authenticity and trust
    3. Handle rate limiting and retries
    4. Process and normalize results
    
    All concrete analyzer implementations should inherit from this class.
    """
    
    def __init__(self, 
                api_key: Optional[str] = None, 
                mock_mode: bool = False,
                rate_limit_calls: int = 10,
                rate_limit_period: int = 60,
                max_retries: int = 3):
        """
        Initialize the base analyzer.
        
        Args:
            api_key: API key for the AI service
            mock_mode: Whether to run in mock mode (no actual API calls)
            rate_limit_calls: Maximum number of API calls in the rate limit period
            rate_limit_period: Rate limit period in seconds
            max_retries: Maximum number of retries for API calls
        """
        self.api_key = api_key
        self.mock_mode = mock_mode
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period
        self.max_retries = max_retries
        
        # Configure method rate limiting
        self._configure_rate_limits()
        
        logger.info(f"Initialized {self.__class__.__name__} (mock_mode={mock_mode})")
    
    def _configure_rate_limits(self) -> None:
        """Configure method-specific rate limits."""
        # Apply rate limiting decorator to analyze_content method
        self.analyze_content = sleep_and_retry(
            limits(calls=self.rate_limit_calls, period=self.rate_limit_period)(
                self.analyze_content
            )
        )
    
    @abc.abstractmethod
    def extract_content(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant content from persona data for analysis.
        
        Args:
            persona_data: Dictionary containing Reddit persona data
            
        Returns:
            Dictionary with extracted content ready for analysis
        """
        pass
    
    @abc.abstractmethod
    def analyze_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze extracted content using AI service.
        
        Args:
            content: Extracted content dictionary
            
        Returns:
            Dictionary with analysis results
            
        Raises:
            RateLimitExceeded: If API rate limit is exceeded
            APIError: If API call fails
        """
        pass
    
    @abc.abstractmethod
    def _build_prompt(self, content: Dict[str, Any]) -> str:
        """
        Build prompt for AI service based on extracted content.
        
        Args:
            content: Extracted content dictionary
            
        Returns:
            Formatted prompt string
        """
        pass
    
    @abc.abstractmethod
    def _parse_response(self, response: Any) -> Dict[str, Any]:
        """
        Parse and normalize response from AI service.
        
        Args:
            response: Raw response from AI service
            
        Returns:
            Normalized dictionary with analysis results
        """
        pass
    
    @abc.abstractmethod
    def _mock_analyze(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate mock analysis results for testing.
        
        Args:
            content: Extracted content dictionary
            
        Returns:
            Mock analysis results dictionary
        """
        pass
    
    @backoff.on_exception(backoff.expo, 
                         (Exception,), 
                         max_tries=3, 
                         jitter=backoff.full_jitter)
    def _api_call_with_retry(self, func, *args, **kwargs) -> Any:
        """
        Make API call with exponential backoff retry.
        
        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Result of the function call
            
        Raises:
            Exception: If all retries fail
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"API call failed: {str(e)}")
            raise
    
    def analyze(self, persona_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrate the complete analysis process.
        
        This method:
        1. Extracts content from persona data
        2. Analyzes the content using the AI service (or mock)
        3. Handles errors and retries
        4. Returns normalized results
        
        Args:
            persona_data: Dictionary containing Reddit persona data
            
        Returns:
            Dictionary with complete analysis results
        """
        start_time = time.time()
        logger.info(f"Starting {self.__class__.__name__} analysis")
        
        if self.mock_mode:
            logger.info("Using mock mode")
            extracted_content = self.extract_content(persona_data)
            results = self._mock_analyze(extracted_content)
            results["analysis_time"] = time.time() - start_time
            results["mock"] = True
            return results
        
        try:
            # Extract content
            extracted_content = self.extract_content(persona_data)
            
            # Analyze content
            results = self._api_call_with_retry(
                self.analyze_content, extracted_content
            )
            
            # Add metadata
            results["analysis_time"] = time.time() - start_time
            results["analysis_timestamp"] = datetime.now().isoformat()
            results["analyzer"] = self.__class__.__name__
            
            logger.info(f"Analysis completed in {results['analysis_time']:.2f}s")
            return results
            
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            
            # Fallback to mock analysis
            logger.info("Falling back to mock analysis")
            results = self._mock_analyze(self.extract_content(persona_data))
            results["error"] = str(e)
            results["fallback"] = True
            results["analysis_time"] = time.time() - start_time
            
            return results


class RateLimitExceeded(Exception):
    """Exception raised when API rate limit is exceeded."""
    pass


class APIError(Exception):
    """Exception raised when API call fails."""
    pass
