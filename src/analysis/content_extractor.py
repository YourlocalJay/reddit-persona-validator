"""
Advanced content extraction for deeper behavioral analysis.

This module provides enhanced content extraction capabilities for the Reddit Persona Validator,
allowing for more sophisticated behavioral analysis by extracting and processing a wider range
of user data points from Reddit.

Features:
- Content clustering by topic
- Sentiment analysis
- Language pattern detection
- Temporal activity pattern analysis
- Subreddit engagement profiling
- Interaction network mapping
"""

import re
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set, Union, Counter
from collections import defaultdict, Counter as CollectionsCounter
import json
from pathlib import Path
import hashlib
import os

# Try to import NLP libraries, with graceful fallback
try:
    import nltk
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False

from ..utils.reddit_api import RedditOAuth2Client

logger = logging.getLogger(__name__)

class ContentExtractionError(Exception):
    """Exception raised for content extraction errors."""
    pass

class ContentExtractor:
    """
    Advanced content extractor for deeper behavioral analysis.
    
    This class provides methods to extract, process, and analyze Reddit user content
    with a focus on behavioral patterns, linguistic features, and temporal activity.
    
    Features:
    - Content extraction from Reddit API
    - Text preprocessing and cleaning
    - Sentiment analysis
    - Topic clustering
    - Temporal pattern analysis
    - Interaction network mapping
    
    Usage:
        extractor = ContentExtractor(reddit_client=reddit_client)
        user_profile = extractor.extract_user_profile("username")
        linguistic_features = extractor.extract_linguistic_features(user_profile)
        behavior_patterns = extractor.extract_behavior_patterns(user_profile)
    """
    
    def __init__(
        self,
        reddit_client: Optional[RedditOAuth2Client] = None,
        cache_dir: Optional[str] = None,
        cache_enabled: bool = True,
        cache_expiry: int = 86400,  # 24 hours
        use_nlp: bool = True
    ):
        """
        Initialize the content extractor.
        
        Args:
            reddit_client: Reddit API client instance
            cache_dir: Directory to store cached data
            cache_enabled: Whether to enable caching
            cache_expiry: Cache expiry time in seconds
            use_nlp: Whether to use NLP features if available
        """
        self.reddit_client = reddit_client
        self.cache_enabled = cache_enabled
        self.cache_expiry = cache_expiry
        self.use_nlp = use_nlp
        
        # Configure cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(".cache/content_extraction")
            
        if self.cache_enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize NLP components if available
        self.nlp_initialized = False
        self.nlp = None
        self.sentiment_analyzer = None
        self.lemmatizer = None
        self.stop_words = set()
        
        if use_nlp:
            self._init_nlp()
            
        logger.info(f"ContentExtractor initialized (NLP: {self.nlp_initialized})")
    
    def _init_nlp(self) -> None:
        """
        Initialize NLP components if available.
        """
        if not self.use_nlp:
            return
            
        try:
            # Initialize NLTK components
            if NLTK_AVAILABLE:
                # Download required NLTK resources if not already downloaded
                try:
                    nltk.data.find('tokenizers/punkt')
                except LookupError:
                    nltk.download('punkt', quiet=True)
                    
                try:
                    nltk.data.find('corpora/stopwords')
                except LookupError:
                    nltk.download('stopwords', quiet=True)
                    
                try:
                    nltk.data.find('corpora/wordnet')
                except LookupError:
                    nltk.download('wordnet', quiet=True)
                    
                try:
                    nltk.data.find('sentiment/vader_lexicon')
                except LookupError:
                    nltk.download('vader_lexicon', quiet=True)
                
                # Initialize NLTK components
                self.lemmatizer = WordNetLemmatizer()
                self.stop_words = set(stopwords.words('english'))
                self.sentiment_analyzer = SentimentIntensityAnalyzer()
                
                logger.info("NLTK components initialized successfully")
            
            # Initialize spaCy model if available
            if SPACY_AVAILABLE:
                try:
                    # Try to load a small English model
                    self.nlp = spacy.load("en_core_web_sm")
                except OSError:
                    # If model not found, try to download it
                    try:
                        os.system("python -m spacy download en_core_web_sm")
                        self.nlp = spacy.load("en_core_web_sm")
                    except Exception as e:
                        logger.warning(f"Failed to download spaCy model: {str(e)}")
                        self.nlp = None
                
                if self.nlp:
                    logger.info("spaCy model loaded successfully")
            
            self.nlp_initialized = NLTK_AVAILABLE or (SPACY_AVAILABLE and self.nlp is not None)
            
        except Exception as e:
            logger.warning(f"Failed to initialize NLP components: {str(e)}")
            self.nlp_initialized = False
    
    def _get_cache_path(self, username: str, cache_type: str) -> Path:
        """
        Get the path to a cached file.
        
        Args:
            username: Reddit username
            cache_type: Type of cached data
            
        Returns:
            Path to the cached file
        """
        # Use lowercase username for cache files
        username = username.lower()
        
        # Create a cache key that combines username and cache type
        cache_key = f"{username}_{cache_type}"
        
        # Use a hash to ensure filename compatibility
        filename = f"{hashlib.md5(cache_key.encode()).hexdigest()}.json"
        
        return self.cache_dir / filename
    
    def _load_from_cache(self, username: str, cache_type: str) -> Optional[Dict[str, Any]]:
        """
        Load data from cache if available and not expired.
        
        Args:
            username: Reddit username
            cache_type: Type of cached data
            
        Returns:
            Cached data dictionary or None if not available
        """
        if not self.cache_enabled:
            return None
            
        cache_path = self._get_cache_path(username, cache_type)
        
        if not cache_path.exists():
            return None
            
        try:
            # Read cached data
            with open(cache_path, 'r') as f:
                cached_data = json.load(f)
                
            # Check cache expiry
            if "cached_at" in cached_data:
                cached_at = datetime.fromisoformat(cached_data["cached_at"])
                expiry_time = cached_at + timedelta(seconds=self.cache_expiry)
                
                if datetime.now() > expiry_time:
                    logger.debug(f"Cache expired for {username} ({cache_type})")
                    return None
                    
            return cached_data
            
        except Exception as e:
            logger.warning(f"Failed to load cache for {username} ({cache_type}): {str(e)}")
            return None
    
    def _save_to_cache(self, username: str, cache_type: str, data: Dict[str, Any]) -> bool:
        """
        Save data to cache.
        
        Args:
            username: Reddit username
            cache_type: Type of cached data
            data: Data to cache
            
        Returns:
            True if successfully saved, False otherwise
        """
        if not self.cache_enabled:
            return False
            
        cache_path = self._get_cache_path(username, cache_type)
        
        try:
            # Add cache metadata
            data_to_cache = dict(data)  # Create a copy to avoid modifying the original
            data_to_cache["cached_at"] = datetime.now().isoformat()
            
            # Write to cache file
            with open(cache_path, 'w') as f:
                json.dump(data_to_cache, f)
                
            return True
            
        except Exception as e:
            logger.warning(f"Failed to save cache for {username} ({cache_type}): {str(e)}")
            return False
    
    def extract_user_profile(
        self, 
        username: str,
        force_refresh: bool = False,
        comment_limit: int = 100,
        post_limit: int = 50
    ) -> Dict[str, Any]:
        """
        Extract comprehensive user profile data.
        
        Args:
            username: Reddit username
            force_refresh: Whether to force a refresh from the API
            comment_limit: Maximum number of comments to fetch
            post_limit: Maximum number of posts to fetch
            
        Returns:
            Dictionary with user profile data
            
        Raises:
            ContentExtractionError: If extraction fails
        """
        if not force_refresh:
            # Try to load from cache first
            cached_data = self._load_from_cache(username, "profile")
            if cached_data:
                logger.info(f"Loaded profile for {username} from cache")
                return cached_data
        
        if not self.reddit_client:
            raise ContentExtractionError("Reddit client not initialized")
            
        try:
            # Fetch user profile data using Reddit API
            profile_data = self.reddit_client.get_user_profile(
                username=username,
                include_comments=True,
                include_posts=True,
                limit=max(comment_limit, post_limit)
            )
            
            if "error" in profile_data:
                raise ContentExtractionError(f"Failed to fetch user profile: {profile_data['error']}")
            
            # Extract comments and posts
            comments = profile_data.get("comments", [])
            posts = profile_data.get("posts", [])
            
            # Limit the number of items based on parameters
            comments = comments[:comment_limit]
            posts = posts[:post_limit]
            
            # Calculate basic metrics
            profile = profile_data.get("profile", {})
            
            # Process timestamp fields to make cache JSON-serializable
            processed_profile = self._process_timestamps(profile)
            processed_comments = [self._process_timestamps(c) for c in comments]
            processed_posts = [self._process_timestamps(p) for p in posts]
            
            # Assemble enhanced profile data
            enhanced_profile = {
                "username": username,
                "profile": processed_profile,
                "comments": processed_comments,
                "posts": processed_posts,
                "metadata": {
                    "fetched_at": datetime.now().isoformat(),
                    "comment_count": len(processed_comments),
                    "post_count": len(processed_posts)
                }
            }
            
            # Save to cache
            self._save_to_cache(username, "profile", enhanced_profile)
            
            logger.info(f"Extracted profile for {username} with {len(processed_comments)} comments and {len(processed_posts)} posts")
            return enhanced_profile
            
        except Exception as e:
            logger.error(f"Failed to extract user profile for {username}: {str(e)}")
            raise ContentExtractionError(f"Failed to extract user profile: {str(e)}")
    
    def _process_timestamps(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process timestamp fields to make them JSON-serializable.
        
        Args:
            data: Dictionary containing timestamp fields
            
        Returns:
            Processed dictionary
        """
        if not isinstance(data, dict):
            return data
            
        result = {}
        
        for key, value in data.items():
            if key == "created_utc" and isinstance(value, (int, float)):
                # Convert Unix timestamp to ISO format
                result[key] = value
                result["created_iso"] = datetime.fromtimestamp(value).isoformat()
            else:
                result[key] = value
                
        return result
    
    def extract_linguistic_features(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract linguistic features from user content.
        
        Args:
            profile_data: User profile data from extract_user_profile
            
        Returns:
            Dictionary with linguistic features
        """
        username = profile_data.get("username", "unknown")
        
        # Try to load from cache first
        cached_data = self._load_from_cache(username, "linguistic")
        if cached_data:
            logger.info(f"Loaded linguistic features for {username} from cache")
            return cached_data
        
        comments = profile_data.get("comments", [])
        posts = profile_data.get("posts", [])
        
        # Extract text content
        comment_texts = [c.get("body", "") for c in comments if "body" in c]
        post_titles = [p.get("title", "") for p in posts if "title" in p]
        post_texts = [p.get("selftext", "") for p in posts if "selftext" in p and p.get("selftext") != "[removed]"]
        
        # Combine all text for analysis
        all_texts = comment_texts + post_texts + post_titles
        combined_text = " ".join(all_texts)
        
        # Initialize result structure
        result = {
            "username": username,
            "basic_metrics": self._extract_basic_text_metrics(all_texts),
            "vocabulary_metrics": self._extract_vocabulary_metrics(all_texts),
            "sentiment_analysis": self._extract_sentiment_metrics(all_texts),
            "writing_style": self._extract_writing_style_metrics(all_texts),
            "topic_analysis": self._extract_topic_analysis(all_texts),
            "temporal_patterns": self._extract_temporal_patterns(comments, posts),
            "metadata": {
                "analyzed_at": datetime.now().isoformat(),
                "comment_count": len(comments),
                "post_count": len(posts),
                "text_sample_count": len(all_texts)
            }
        }
        
        # Save to cache
        self._save_to_cache(username, "linguistic", result)
        
        logger.info(f"Extracted linguistic features for {username}")
        return result
    
    def _extract_basic_text_metrics(self, texts: List[str]) -> Dict[str, Any]:
        """
        Extract basic text metrics from content.
        
        Args:
            texts: List of text content
            
        Returns:
            Dictionary with basic text metrics
        """
        if not texts:
            return {
                "total_text_length": 0,
                "average_text_length": 0,
                "text_length_stddev": 0,
                "total_words": 0,
                "average_words": 0,
                "total_sentences": 0,
                "average_sentences": 0
            }
        
        # Calculate text lengths
        text_lengths = [len(text) for text in texts]
        total_length = sum(text_lengths)
        avg_length = total_length / len(texts)
        length_stddev = statistics.stdev(text_lengths) if len(texts) > 1 else 0
        
        # Count words and sentences if NLP is available
        total_words = 0
        total_sentences = 0
        
        if NLTK_AVAILABLE:
            # Count words and sentences using NLTK
            word_counts = [len(word_tokenize(text)) for text in texts]
            total_words = sum(word_counts)
            
            sentence_counts = [len(sent_tokenize(text)) for text in texts]
            total_sentences = sum(sentence_counts)
        else:
            # Fallback to simple counting
            word_counts = [len(text.split()) for text in texts]
            total_words = sum(word_counts)
            
            # Rough sentence counting using periods, exclamation, and question marks
            sentence_counts = [len(re.findall(r'[.!?]+', text)) + 1 for text in texts]
            total_sentences = sum(sentence_counts)
        
        return {
            "total_text_length": total_length,
            "average_text_length": avg_length,
            "text_length_stddev": length_stddev,
            "total_words": total_words,
            "average_words": total_words / len(texts),
            "total_sentences": total_sentences,
            "average_sentences": total_sentences / len(texts) if total_sentences > 0 else 0
        }
    
    def _extract_vocabulary_metrics(self, texts: List[str]) -> Dict[str, Any]:
        """
        Extract vocabulary metrics from content.
        
        Args:
            texts: List of text content
            
        Returns:
            Dictionary with vocabulary metrics
        """
        if not texts or not self.nlp_initialized:
            return {
                "vocabulary_size": 0,
                "lexical_diversity": 0,
                "word_frequency": {},
                "rare_word_ratio": 0
            }
        
        # Combine texts for analysis
        combined_text = " ".join(texts)
        
        # Tokenize and preprocess
        if NLTK_AVAILABLE:
            # Use NLTK for tokenization and preprocessing
            words = word_tokenize(combined_text.lower())
            # Remove punctuation and stopwords
            words = [word for word in words if word.isalpha() and word not in self.stop_words]
            # Lemmatize words
            if self.lemmatizer:
                words = [self.lemmatizer.lemmatize(word) for word in words]
        elif SPACY_AVAILABLE and self.nlp:
            # Use spaCy for tokenization and preprocessing
            doc = self.nlp(combined_text)
            words = [token.lemma_.lower() for token in doc if token.is_alpha and not token.is_stop]
        else:
            # Fallback to simple word splitting
            words = combined_text.lower().split()
            words = [word for word in words if word.isalpha()]
        
        # Calculate vocabulary metrics
        vocabulary = set(words)
        vocabulary_size = len(vocabulary)
        
        # Calculate lexical diversity (type-token ratio)
        lexical_diversity = vocabulary_size / len(words) if words else 0
        
        # Word frequency distribution
        word_counts = CollectionsCounter(words)
        common_words = dict(word_counts.most_common(20))
        
        # Calculate rare word ratio (words that appear only once)
        rare_words = [word for word, count in word_counts.items() if count == 1]
        rare_word_ratio = len(rare_words) / vocabulary_size if vocabulary_size > 0 else 0
        
        return {
            "vocabulary_size": vocabulary_size,
            "lexical_diversity": lexical_diversity,
            "word_frequency": common_words,
            "rare_word_ratio": rare_word_ratio
        }
    
    def _extract_sentiment_metrics(self, texts: List[str]) -> Dict[str, Any]:
        """
        Extract sentiment metrics from content.
        
        Args:
            texts: List of text content
            
        Returns:
            Dictionary with sentiment metrics
        """
        if not texts or not self.nlp_initialized or not NLTK_AVAILABLE or not self.sentiment_analyzer:
            return {
                "average_sentiment": 0,
                "sentiment_distribution": {
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0
                },
                "emotional_volatility": 0
            }
        
        # Analyze sentiment for each text
        sentiment_scores = []
        for text in texts:
            if not text.strip():
                continue
                
            sentiment = self.sentiment_analyzer.polarity_scores(text)
            sentiment_scores.append(sentiment)
        
        if not sentiment_scores:
            return {
                "average_sentiment": 0,
                "sentiment_distribution": {
                    "positive": 0,
                    "neutral": 0,
                    "negative": 0
                },
                "emotional_volatility": 0
            }
        
        # Calculate average compound sentiment
        compound_scores = [s["compound"] for s in sentiment_scores]
        avg_sentiment = sum(compound_scores) / len(compound_scores)
        
        # Categorize sentiments
        positive_count = sum(1 for score in compound_scores if score > 0.05)
        negative_count = sum(1 for score in compound_scores if score < -0.05)
        neutral_count = len(compound_scores) - positive_count - negative_count
        
        # Calculate sentiment distribution
        total_count = len(compound_scores)
        sentiment_distribution = {
            "positive": positive_count / total_count if total_count > 0 else 0,
            "neutral": neutral_count / total_count if total_count > 0 else 0,
            "negative": negative_count / total_count if total_count > 0 else 0
        }
        
        # Calculate emotional volatility (standard deviation of sentiment scores)
        emotional_volatility = statistics.stdev(compound_scores) if len(compound_scores) > 1 else 0
        
        return {
            "average_sentiment": avg_sentiment,
            "sentiment_distribution": sentiment_distribution,
            "emotional_volatility": emotional_volatility
        }
    
    def _extract_writing_style_metrics(self, texts: List[str]) -> Dict[str, Any]:
        """
        Extract writing style metrics from content.
        
        Args:
            texts: List of text content
            
        Returns:
            Dictionary with writing style metrics
        """
        if not texts:
            return {
                "average_word_length": 0,
                "average_sentence_length": 0,
                "punctuation_frequency": {},
                "capitalization_ratio": 0,
                "question_ratio": 0,
                "formality_score": 0
            }
        
        # Combine texts for analysis
        combined_text = " ".join(texts)
        
        # Calculate average word length
        words = re.findall(r'\b\w+\b', combined_text.lower())
        total_word_length = sum(len(word) for word in words)
        avg_word_length = total_word_length / len(words) if words else 0
        
        # Calculate average sentence length
        sentences = []
        if NLTK_AVAILABLE:
            sentences = sent_tokenize(combined_text)
        else:
            # Simple sentence splitting as fallback
            sentences = re.split(r'[.!?]+', combined_text)
            sentences = [s.strip() for s in sentences if s.strip()]
        
        sentence_word_counts = [len(re.findall(r'\b\w+\b', sentence)) for sentence in sentences]
        avg_sentence_length = sum(sentence_word_counts) / len(sentences) if sentences else 0
        
        # Count punctuation
        punctuation_counts = {}
        for char in combined_text:
            if char in ",.!?;:\"'()[]{}":
                punctuation_counts[char] = punctuation_counts.get(char, 0) + 1
        
        # Calculate capitalization ratio
        uppercase_letters = sum(1 for c in combined_text if c.isupper())
        total_letters = sum(1 for c in combined_text if c.isalpha())
        capitalization_ratio = uppercase_letters / total_letters if total_letters > 0 else 0
        
        # Calculate question ratio
        question_count = combined_text.count('?')
        total_sentences = len(sentences)
        question_ratio = question_count / total_sentences if total_sentences > 0 else 0
        
        # Calculate formality score (higher is more formal)
        # Based on features like contraction usage, pronoun usage, etc.
        contraction_count = len(re.findall(r"\b\w+'(ve|re|s|t|ll|d|m)\b", combined_text.lower()))
        first_person_count = len(re.findall(r"\b(i|me|my|mine|we|us|our|ours)\b", combined_text.lower()))
        
        # Simple formality heuristic: longer words, longer sentences, fewer contractions, and fewer first-person pronouns
        formality_factors = [
            min(1, avg_word_length / 5),  # Normalize to 0-1
            min(1, avg_sentence_length / 20),  # Normalize to 0-1
            1 - min(1, contraction_count / max(1, len(words) / 20)),  # Fewer contractions is more formal
            1 - min(1, first_person_count / max(1, len(words) / 10))  # Fewer first-person references is more formal
        ]
        
        formality_score = sum(formality_factors) / len(formality_factors) if formality_factors else 0
        
        return {
            "average_word_length": avg_word_length,
            "average_sentence_length": avg_sentence_length,
            "punctuation_frequency": punctuation_counts,
            "capitalization_ratio": capitalization_ratio,
            "question_ratio": question_ratio,
            "formality_score": formality_score
        }
    
    def _extract_topic_analysis(self, texts: List[str]) -> Dict[str, Any]:
        """
        Extract topic analysis from content.
        
        Args:
            texts: List of text content
            
        Returns:
            Dictionary with topic analysis
        """
        if not texts or not self.nlp_initialized:
            return {
                "top_keywords": [],
                "top_bigrams": [],
                "top_entities": []
            }
        
        # Combine texts for analysis
        combined_text = " ".join(texts)
        
        top_keywords = []
        top_bigrams = []
        top_entities = []
        
        # Extract keywords and bigrams
        if NLTK_AVAILABLE:
            # Tokenize and preprocess
            words = word_tokenize(combined_text.lower())
            # Remove punctuation and stopwords
            words = [word for word in words if word.isalpha() and word not in self.stop_words]
            
            # Extract keywords
            word_freq = CollectionsCounter(words)
            top_keywords = [{"word": word, "count": count} for word, count in word_freq.most_common(10)]
            
            # Extract bigrams
            bigrams = list(nltk.bigrams(words))
            bigram_freq = CollectionsCounter(bigrams)
            top_bigrams = [
                {"bigram": f"{w1} {w2}", "count": count}
                for (w1, w2), count in bigram_freq.most_common(10)
            ]
        
        # Extract entities if spaCy is available
        if SPACY_AVAILABLE and self.nlp:
            doc = self.nlp(combined_text[:100000])  # Limit text size to avoid memory issues
            entities = [(e.text, e.label_) for e in doc.ents]
            entity_counter = CollectionsCounter(entities)
            top_entities = [
                {"text": text, "type": ent_type, "count": count}
                for (text, ent_type), count in entity_counter.most_common(10)
            ]
        
        return {
            "top_keywords": top_keywords,
            "top_bigrams": top_bigrams,
            "top_entities": top_entities
        }
    
    def _extract_temporal_patterns(self, comments: List[Dict[str, Any]], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract temporal patterns from content.
        
        Args:
            comments: List of comment data
            posts: List of post data
            
        Returns:
            Dictionary with temporal patterns
        """
        # Extract timestamps
        comment_timestamps = [c.get("created_utc", 0) for c in comments if "created_utc" in c]
        post_timestamps = [p.get("created_utc", 0) for p in posts if "created_utc" in p]
        
        all_timestamps = sorted(comment_timestamps + post_timestamps)
        
        if not all_timestamps:
            return {
                "activity_by_hour": {},
                "activity_by_day": {},
                "activity_by_weekday": {},
                "posting_consistency": 0,
                "activity_gaps": []
            }
        
        # Analyze activity by hour of day
        hours = [datetime.fromtimestamp(ts).hour for ts in all_timestamps]
        hour_counts = CollectionsCounter(hours)
        activity_by_hour = {str(h): hour_counts.get(h, 0) for h in range(24)}
        
        # Analyze activity by day of week
        weekdays = [datetime.fromtimestamp(ts).weekday() for ts in all_timestamps]
        weekday_counts = CollectionsCounter(weekdays)
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        activity_by_weekday = {weekday_names[i]: weekday_counts.get(i, 0) for i in range(7)}
        
        # Analyze activity by calendar day
        days = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts in all_timestamps]
        day_counts = CollectionsCounter(days)
        activity_by_day = dict(day_counts.most_common(30))  # Last 30 days with activity
        
        # Calculate posting consistency (lower standard deviation means more consistent)
        if len(all_timestamps) > 1:
            # Calculate time gaps between posts in hours
            time_gaps = []
            for i in range(1, len(all_timestamps)):
                gap_hours = (all_timestamps[i] - all_timestamps[i-1]) / 3600
                if gap_hours < 24 * 7:  # Ignore gaps longer than a week
                    time_gaps.append(gap_hours)
            
            # Calculate consistency score (100 = perfectly consistent, 0 = highly irregular)
            if time_gaps:
                mean_gap = sum(time_gaps) / len(time_gaps)
                gap_stddev = statistics.stdev(time_gaps) if len(time_gaps) > 1 else 0
                
                # Normalize: lower stddev relative to mean = higher consistency
                consistency_ratio = gap_stddev / mean_gap if mean_gap > 0 else 0
                posting_consistency = max(0, 100 - min(100, consistency_ratio * 25))
            else:
                posting_consistency = 0
                
            # Extract significant activity gaps (gaps > 24 hours)
            activity_gaps = []
            for i in range(1, len(all_timestamps)):
                gap_hours = (all_timestamps[i] - all_timestamps[i-1]) / 3600
                if gap_hours > 24:
                    start_date = datetime.fromtimestamp(all_timestamps[i-1]).strftime("%Y-%m-%d")
                    end_date = datetime.fromtimestamp(all_timestamps[i]).strftime("%Y-%m-%d")
                    activity_gaps.append({
                        "start": start_date,
                        "end": end_date,
                        "duration_hours": gap_hours
                    })
            
            # Limit to top 10 gaps
            activity_gaps = sorted(activity_gaps, key=lambda x: x["duration_hours"], reverse=True)[:10]
        else:
            posting_consistency = 0
            activity_gaps = []
        
        return {
            "activity_by_hour": activity_by_hour,
            "activity_by_day": activity_by_day,
            "activity_by_weekday": activity_by_weekday,
            "posting_consistency": posting_consistency,
            "activity_gaps": activity_gaps
        }
    
    def extract_behavior_patterns(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract behavioral patterns from user content.
        
        Args:
            profile_data: User profile data from extract_user_profile
            
        Returns:
            Dictionary with behavioral patterns
        """
        username = profile_data.get("username", "unknown")
        
        # Try to load from cache first
        cached_data = self._load_from_cache(username, "behavior")
        if cached_data:
            logger.info(f"Loaded behavior patterns for {username} from cache")
            return cached_data
        
        comments = profile_data.get("comments", [])
        posts = profile_data.get("posts", [])
        
        # Extract behavior patterns
        result = {
            "username": username,
            "engagement_patterns": self._extract_engagement_patterns(comments, posts),
            "subreddit_analysis": self._extract_subreddit_analysis(comments, posts),
            "interaction_patterns": self._extract_interaction_patterns(comments),
            "content_patterns": self._extract_content_patterns(comments, posts),
            "metadata": {
                "analyzed_at": datetime.now().isoformat(),
                "comment_count": len(comments),
                "post_count": len(posts)
            }
        }
        
        # Save to cache
        self._save_to_cache(username, "behavior", result)
        
        logger.info(f"Extracted behavior patterns for {username}")
        return result
    
    def _extract_engagement_patterns(self, comments: List[Dict[str, Any]], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract engagement patterns from user content.
        
        Args:
            comments: List of comment data
            posts: List of post data
            
        Returns:
            Dictionary with engagement patterns
        """
        if not comments and not posts:
            return {
                "comment_to_post_ratio": 0,
                "response_rate": 0,
                "engagement_depth": 0,
                "karma_per_comment": 0,
                "karma_per_post": 0,
                "controversy_score": 0
            }
        
        # Calculate comment to post ratio
        comment_count = len(comments)
        post_count = len(posts)
        comment_post_ratio = comment_count / post_count if post_count > 0 else float('inf')
        
        # Calculate karma metrics
        comment_karma = sum(c.get("score", 0) for c in comments)
        post_karma = sum(p.get("score", 0) for p in posts)
        
        karma_per_comment = comment_karma / comment_count if comment_count > 0 else 0
        karma_per_post = post_karma / post_count if post_count > 0 else 0
        
        # Calculate response rate (percentage of comments that are responses to others)
        response_comments = [c for c in comments if c.get("parent_id", "").startswith("t1_")]
        response_rate = len(response_comments) / comment_count if comment_count > 0 else 0
        
        # Calculate engagement depth (how deep in comment chains the user typically goes)
        comment_depths = []
        for comment in comments:
            # Extract depth from comment data if available
            depth = 0
            parent_id = comment.get("parent_id", "")
            if parent_id.startswith("t1_"):
                depth = 1
                # Note: To get the actual depth, we would need to recursively
                # fetch parent comments, which is not practical here
            comment_depths.append(depth)
        
        engagement_depth = sum(comment_depths) / len(comment_depths) if comment_depths else 0
        
        # Calculate controversy score (variance in karma)
        comment_scores = [c.get("score", 0) for c in comments]
        post_scores = [p.get("score", 0) for p in posts]
        all_scores = comment_scores + post_scores
        
        if all_scores and len(all_scores) > 1:
            score_variance = statistics.variance(all_scores)
            mean_score = statistics.mean(all_scores)
            
            # Normalize controversy score: higher variance relative to mean = more controversial
            controversy_score = min(100, (score_variance / max(1, abs(mean_score))) * 10)
        else:
            controversy_score = 0
        
        return {
            "comment_to_post_ratio": comment_post_ratio,
            "response_rate": response_rate,
            "engagement_depth": engagement_depth,
            "karma_per_comment": karma_per_comment,
            "karma_per_post": karma_per_post,
            "controversy_score": controversy_score
        }
    
    def _extract_subreddit_analysis(self, comments: List[Dict[str, Any]], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract subreddit analysis from user content.
        
        Args:
            comments: List of comment data
            posts: List of post data
            
        Returns:
            Dictionary with subreddit analysis
        """
        # Extract subreddits from comments and posts
        comment_subreddits = [c.get("subreddit", "") for c in comments if "subreddit" in c]
        post_subreddits = [p.get("subreddit", "") for p in posts if "subreddit" in p]
        
        all_subreddits = comment_subreddits + post_subreddits
        
        if not all_subreddits:
            return {
                "subreddit_count": 0,
                "top_subreddits": {},
                "subreddit_categories": {},
                "focus_score": 0
            }
        
        # Count subreddit occurrences
        subreddit_counts = CollectionsCounter(all_subreddits)
        unique_subreddits = set(all_subreddits)
        
        # Calculate top subreddits
        top_subreddits = dict(subreddit_counts.most_common(10))
        
        # Calculate focus score (higher = more focused on fewer subreddits)
        # Using Herfindahl-Hirschman Index (HHI) for concentration
        total_posts = len(all_subreddits)
        subreddit_shares = [(count / total_posts) ** 2 for count in subreddit_counts.values()]
        focus_score = sum(subreddit_shares) * 100  # Scale to 0-100
        
        # Simple subreddit categorization
        # Note: A more comprehensive implementation would use a subreddit categorization database
        categories = defaultdict(int)
        
        # Basic category keywords (very simplified)
        category_keywords = {
            "tech": ["programming", "technology", "python", "javascript", "webdev", "sysadmin", "techsupport"],
            "gaming": ["gaming", "games", "steam", "pcgaming", "ps4", "xboxone", "nintendo"],
            "news": ["news", "worldnews", "politics", "science", "environment"],
            "entertainment": ["movies", "television", "music", "books", "anime"],
            "lifestyle": ["fitness", "food", "cooking", "travel", "fashion", "relationships"],
            "finance": ["investing", "personalfinance", "cryptocurrency", "bitcoin", "wallstreetbets"],
        }
        
        for subreddit in unique_subreddits:
            subreddit_lower = subreddit.lower()
            categorized = False
            
            # Check if subreddit matches any category keywords
            for category, keywords in category_keywords.items():
                if any(keyword in subreddit_lower for keyword in keywords):
                    categories[category] += subreddit_counts[subreddit]
                    categorized = True
                    break
            
            # Add to other if no category matched
            if not categorized:
                categories["other"] += subreddit_counts[subreddit]
        
        # Convert to percentages
        subreddit_categories = {
            category: (count / total_posts) * 100
            for category, count in categories.items()
        }
        
        return {
            "subreddit_count": len(unique_subreddits),
            "top_subreddits": top_subreddits,
            "subreddit_categories": subreddit_categories,
            "focus_score": focus_score
        }
    
    def _extract_interaction_patterns(self, comments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract interaction patterns from user comments.
        
        Args:
            comments: List of comment data
            
        Returns:
            Dictionary with interaction patterns
        """
        if not comments:
            return {
                "unique_interactions": 0,
                "repeat_interaction_rate": 0,
                "top_interactions": [],
                "conversation_initiator_rate": 0
            }
        
        # Extract parent comments and authors to analyze interactions
        parent_ids = [c.get("parent_id", "") for c in comments if "parent_id" in c]
        parent_authors = []
        
        for comment in comments:
            author = None
            if "author" in comment.get("replies", {}):
                author = comment["replies"]["author"]
            parent_authors.append(author)
        
        # Count unique users interacted with
        unique_authors = set(a for a in parent_authors if a)
        unique_interactions = len(unique_authors)
        
        # Calculate repeat interaction rate
        author_counts = CollectionsCounter(a for a in parent_authors if a)
        repeat_interactions = sum(count - 1 for count in author_counts.values() if count > 1)
        repeat_interaction_rate = repeat_interactions / len(comments) if comments else 0
        
        # Identify top interactions
        top_interactions = [
            {"author": author, "count": count}
            for author, count in author_counts.most_common(5)
            if author
        ]
        
        # Calculate conversation initiator rate
        # (comments that are direct responses to posts, not other comments)
        post_responses = [p for p in parent_ids if p.startswith("t3_")]
        conversation_initiator_rate = len(post_responses) / len(comments) if comments else 0
        
        return {
            "unique_interactions": unique_interactions,
            "repeat_interaction_rate": repeat_interaction_rate,
            "top_interactions": top_interactions,
            "conversation_initiator_rate": conversation_initiator_rate
        }
    
    def _extract_content_patterns(self, comments: List[Dict[str, Any]], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract content patterns from user comments and posts.
        
        Args:
            comments: List of comment data
            posts: List of post data
            
        Returns:
            Dictionary with content patterns
        """
        # Extract content types from posts
        post_types = []
        for post in posts:
            if post.get("is_self", False):
                post_types.append("text")
            elif "post_hint" in post:
                post_types.append(post["post_hint"])
            elif post.get("url", "").endswith((".jpg", ".jpeg", ".png", ".gif")):
                post_types.append("image")
            elif post.get("url", "").endswith((".mp4", ".webm", ".avi")):
                post_types.append("video")
            elif "youtube.com" in post.get("url", "") or "youtu.be" in post.get("url", ""):
                post_types.append("video")
            elif post.get("url", "").endswith((".mp3", ".wav", ".ogg")):
                post_types.append("audio")
            else:
                post_types.append("link")
        
        # Count content types
        content_type_counts = CollectionsCounter(post_types)
        content_type_distribution = {
            content_type: count / len(posts) * 100 if posts else 0
            for content_type, count in content_type_counts.items()
        }
        
        # Extract OC (Original Content) ratio
        oc_posts = [p for p in posts if p.get("is_original_content", False)]
        oc_ratio = len(oc_posts) / len(posts) if posts else 0
        
        # Extract comment length distribution
        comment_lengths = [len(c.get("body", "")) for c in comments if "body" in c]
        
        length_distribution = {
            "short": 0,  # <50 chars
            "medium": 0,  # 50-200 chars
            "long": 0,   # >200 chars
        }
        
        if comment_lengths:
            short_count = sum(1 for length in comment_lengths if length < 50)
            medium_count = sum(1 for length in comment_lengths if 50 <= length <= 200)
            long_count = sum(1 for length in comment_lengths if length > 200)
            
            total_comments = len(comment_lengths)
            length_distribution = {
                "short": short_count / total_comments * 100,
                "medium": medium_count / total_comments * 100,
                "long": long_count / total_comments * 100
            }
        
        # Analyze URL sharing patterns
        urls_shared = []
        url_pattern = re.compile(r'https?://\S+')
        
        for comment in comments:
            body = comment.get("body", "")
            if body:
                urls = re.findall(url_pattern, body)
                urls_shared.extend(urls)
                
        for post in posts:
            if not post.get("is_self", False) and "url" in post:
                urls_shared.append(post["url"])
        
        # Extract domains from URLs
        domains = []
        for url in urls_shared:
            try:
                domain = urlparse(url).netloc
                domains.append(domain)
            except:
                pass
        
        domain_counts = CollectionsCounter(domains)
        top_domains = dict(domain_counts.most_common(5))
        
        return {
            "content_type_distribution": content_type_distribution,
            "original_content_ratio": oc_ratio,
            "comment_length_distribution": length_distribution,
            "url_sharing_frequency": len(urls_shared) / (len(comments) + len(posts)) if (comments or posts) else 0,
            "top_shared_domains": top_domains
        }
    
    def get_comprehensive_user_analysis(
        self,
        username: str,
        force_refresh: bool = False,
        include_linguistic: bool = True,
        include_behavior: bool = True
    ) -> Dict[str, Any]:
        """
        Perform comprehensive user analysis.
        
        Args:
            username: Reddit username
            force_refresh: Whether to force a refresh from the API
            include_linguistic: Whether to include linguistic analysis
            include_behavior: Whether to include behavior analysis
            
        Returns:
            Dictionary with comprehensive analysis results
        """
        # Extract user profile data
        profile_data = self.extract_user_profile(
            username=username,
            force_refresh=force_refresh
        )
        
        result = {
            "username": username,
            "profile": profile_data.get("profile", {}),
            "metadata": {
                "analyzed_at": datetime.now().isoformat(),
                "comment_count": profile_data.get("metadata", {}).get("comment_count", 0),
                "post_count": profile_data.get("metadata", {}).get("post_count", 0)
            }
        }
        
        # Include linguistic analysis if requested
        if include_linguistic:
            linguistic_features = self.extract_linguistic_features(profile_data)
            result["linguistic_analysis"] = {
                "vocabulary_metrics": linguistic_features.get("vocabulary_metrics", {}),
                "sentiment_analysis": linguistic_features.get("sentiment_analysis", {}),
                "writing_style": linguistic_features.get("writing_style", {}),
                "topic_analysis": linguistic_features.get("topic_analysis", {}),
                "temporal_patterns": linguistic_features.get("temporal_patterns", {})
            }
        
        # Include behavior analysis if requested
        if include_behavior:
            behavior_patterns = self.extract_behavior_patterns(profile_data)
            result["behavior_analysis"] = {
                "engagement_patterns": behavior_patterns.get("engagement_patterns", {}),
                "subreddit_analysis": behavior_patterns.get("subreddit_analysis", {}),
                "interaction_patterns": behavior_patterns.get("interaction_patterns", {}),
                "content_patterns": behavior_patterns.get("content_patterns", {})
            }
        
        logger.info(f"Completed comprehensive analysis for {username}")
        return result
    
    def close(self) -> None:
        """Clean up resources."""
        if self.reddit_client:
            self.reddit_client.close()
