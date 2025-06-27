"""Redis-based storage for high-volume deployments.

This module provides a Redis implementation for the caching and storage system,
designed for high-volume deployments where multiple instances of the validator
need to share data.

It implements the same interface as the SQLite-based Database class but uses
Redis for better performance and scalability in distributed environments.
"""

import json
import logging
import pickle
from typing import Dict, List, Any, Optional, Union, Tuple, Set
from datetime import datetime, timedelta

import redis
from redis.exceptions import RedisError
from pydantic import BaseModel, Field

from .config_loader import ConfigLoader
from .database import ValidationRecord, PerformanceMetric, DatabaseConfig

# Setup logging
logger = logging.getLogger("persona-validator-redis")


class RedisConfig(BaseModel):
    """Redis configuration model."""
    
    enabled: bool = Field(False, description="Whether Redis is enabled")
    host: str = Field("localhost", description="Redis host")
    port: int = Field(6379, description="Redis port")
    db: int = Field(0, description="Redis database number")
    password: Optional[str] = Field(None, description="Redis password")
    prefix: str = Field("rpv:", description="Key prefix for Redis keys")
    connection_pool_size: int = Field(10, description="Connection pool size")
    socket_timeout: int = Field(5, description="Socket timeout in seconds")
    socket_connect_timeout: int = Field(5, description="Socket connect timeout in seconds")
    retry_on_timeout: bool = Field(True, description="Whether to retry on timeout")
    health_check_interval: int = Field(30, description="Health check interval in seconds")


class RedisStore:
    """Redis-based storage implementation for Reddit Persona Validator."""
    
    def __init__(self, config: RedisConfig, db_config: DatabaseConfig):
        """
        Initialize Redis store with configuration.
        
        Args:
            config: Redis configuration
            db_config: Database configuration (for shared settings like cache expiry)
        """
        self.config = config
        self.db_config = db_config
        self._redis = None
        self._initialized = False
        
    @classmethod
    def from_config(cls, config_path: str = "config/config.yaml") -> "RedisStore":
        """
        Create a Redis store instance from configuration file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            RedisStore instance
        """
        config_data = ConfigLoader.load_config(config_path)
        redis_config = RedisConfig(**config_data.get("database", {}).get("redis", {}))
        db_config = DatabaseConfig(**config_data.get("database", {}))
        return cls(redis_config, db_config)
    
    async def initialize(self) -> None:
        """
        Initialize the Redis connection.
        
        This method must be called before using the Redis store.
        """
        if self._initialized:
            return
        
        try:
            # Create Redis connection pool
            self._redis = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval,
                connection_pool=redis.ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    max_connections=self.config.connection_pool_size
                )
            )
            
            # Test connection
            self._redis.ping()
            
            self._initialized = True
            logger.info(f"Redis store initialized: {self.config.host}:{self.config.port}/{self.config.db}")
        except RedisError as e:
            logger.error(f"Failed to initialize Redis: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Close Redis connection and release resources."""
        if not self._initialized:
            return
        
        try:
            if self._redis:
                self._redis.close()
            
            self._initialized = False
            logger.info("Redis connection closed")
        except RedisError as e:
            logger.error(f"Error closing Redis connection: {str(e)}")
    
    def _get_key(self, key_type: str, identifier: str) -> str:
        """
        Get Redis key with prefix.
        
        Args:
            key_type: Type of key (validation, performance, etc.)
            identifier: Unique identifier
            
        Returns:
            Prefixed Redis key
        """
        return f"{self.config.prefix}{key_type}:{identifier}"
    
    async def get_cached_validation(self, username: str) -> Optional[ValidationRecord]:
        """
        Get a cached validation result for a username.
        
        Args:
            username: Reddit username
            
        Returns:
            ValidationRecord if found and not expired, None otherwise
        """
        try:
            # Get validation record from Redis
            key = self._get_key("validation", username)
            data = self._redis.get(key)
            
            if not data:
                return None
            
            # Deserialize the data
            record_dict = json.loads(data)
            
            # Check if expired
            expires_at = datetime.fromisoformat(record_dict.get("cache_expires_at"))
            if expires_at < datetime.now():
                # Delete expired key
                self._redis.delete(key)
                return None
            
            # Convert to ValidationRecord
            return ValidationRecord(
                id=record_dict.get("id"),
                username=record_dict.get("username"),
                exists=record_dict.get("exists"),
                trust_score=record_dict.get("trust_score"),
                account_details=record_dict.get("account_details"),
                email_verified=record_dict.get("email_verified"),
                email_details=record_dict.get("email_details"),
                ai_analysis=record_dict.get("ai_analysis"),
                errors=record_dict.get("errors", []),
                warnings=record_dict.get("warnings", [])
            )
        except (RedisError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error getting cached validation for {username}: {str(e)}")
            return None
    
    async def store_validation_result(self, result: ValidationRecord) -> str:
        """
        Store a validation result in Redis.
        
        Args:
            result: Validation result to store
            
        Returns:
            ID of the stored record
        """
        try:
            # Generate ID if not provided
            if result.id is None:
                result.id = f"val_{result.username}_{int(datetime.now().timestamp())}"
            
            # Calculate cache expiry time if not set
            if result.cache_expires_at is None:
                result.cache_expires_at = datetime.now() + timedelta(seconds=self.db_config.cache_expiry)
            
            # Convert to dictionary for storage
            result_dict = {
                "id": result.id,
                "username": result.username,
                "exists": result.exists,
                "trust_score": result.trust_score,
                "account_details": result.account_details,
                "email_verified": result.email_verified,
                "email_details": result.email_details,
                "ai_analysis": result.ai_analysis,
                "errors": result.errors or [],
                "warnings": result.warnings or [],
                "created_at": result.created_at.isoformat(),
                "updated_at": result.updated_at.isoformat(),
                "cache_expires_at": result.cache_expires_at.isoformat()
            }
            
            # Store in Redis with expiry
            key = self._get_key("validation", result.username)
            self._redis.setex(
                name=key,
                time=int((result.cache_expires_at - datetime.now()).total_seconds()),
                value=json.dumps(result_dict)
            )
            
            # Store ID in the list of all validations
            all_validations_key = self._get_key("all_validations", "list")
            self._redis.zadd(
                all_validations_key,
                {result.id: datetime.now().timestamp()}
            )
            
            return result.id
        except (RedisError, TypeError, ValueError) as e:
            logger.error(f"Error storing validation result: {str(e)}")
            raise
    
    async def record_performance_metric(self, metric: PerformanceMetric) -> int:
        """
        Record a performance metric in Redis.
        
        Args:
            metric: Performance metric to record
            
        Returns:
            ID of the recorded metric
        """
        try:
            # Generate ID if not provided
            if metric.id is None:
                metric.id = int(datetime.now().timestamp() * 1000)
            
            # Convert to dictionary for storage
            metric_dict = {
                "id": metric.id,
                "metric_type": metric.metric_type,
                "operation": metric.operation,
                "duration_ms": metric.duration_ms,
                "success": metric.success,
                "error_message": metric.error_message,
                "metadata": metric.metadata,
                "created_at": metric.created_at.isoformat()
            }
            
            # Store in Redis
            key = self._get_key("performance", f"{metric.metric_type}_{metric.id}")
            self._redis.set(key, json.dumps(metric_dict))
            
            # Store in sorted set for querying
            metrics_key = self._get_key("all_metrics", metric.metric_type)
            self._redis.zadd(metrics_key, {str(metric.id): datetime.now().timestamp()})
            
            # Set expiry (keep metrics for 30 days)
            self._redis.expire(key, 60 * 60 * 24 * 30)
            
            return metric.id
        except (RedisError, TypeError, ValueError) as e:
            logger.error(f"Error recording performance metric: {str(e)}")
            raise
    
    async def get_performance_metrics(
        self,
        metric_type: Optional[str] = None,
        operation: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PerformanceMetric]:
        """
        Get performance metrics from Redis.
        
        Args:
            metric_type: Filter by metric type
            operation: Filter by operation
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of results
            offset: Result offset
            
        Returns:
            List of PerformanceMetric objects
        """
        try:
            # Determine which key to use
            if metric_type:
                metrics_key = self._get_key("all_metrics", metric_type)
            else:
                # Combine all metric types
                metrics_key = self._get_key("all_metrics", "*")
                # Get all keys matching the pattern
                metrics_keys = self._redis.keys(metrics_key)
                if not metrics_keys:
                    return []
            
            # Convert time filters to timestamps
            min_score = "-inf"
            max_score = "+inf"
            if start_time:
                min_score = start_time.timestamp()
            if end_time:
                max_score = end_time.timestamp()
            
            # Get IDs from sorted set with time range filter
            if metric_type:
                # Get IDs for specific metric type
                metric_ids = self._redis.zrangebyscore(
                    metrics_key,
                    min_score,
                    max_score,
                    start=offset,
                    num=limit,
                    withscores=False
                )
            else:
                # Get IDs from all metric types
                metric_ids = []
                for key in metrics_keys:
                    key_ids = self._redis.zrangebyscore(
                        key,
                        min_score,
                        max_score,
                        withscores=False
                    )
                    metric_ids.extend(key_ids)
                
                # Sort by time descending, apply offset and limit
                metric_ids = sorted(metric_ids, reverse=True)[offset:offset+limit]
            
            # Get full metrics
            results = []
            for metric_id in metric_ids:
                # Get keys for all metric types if needed
                if not metric_type:
                    # Search for key with this ID
                    pattern = self._get_key("performance", f"*_{metric_id.decode()}")
                    key_matches = self._redis.keys(pattern)
                    if not key_matches:
                        continue
                    key = key_matches[0]
                else:
                    key = self._get_key("performance", f"{metric_type}_{metric_id.decode()}")
                
                # Get metric data
                data = self._redis.get(key)
                if not data:
                    continue
                
                # Parse metric
                metric_dict = json.loads(data)
                
                # Filter by operation if specified
                if operation and metric_dict.get("operation") != operation:
                    continue
                
                # Convert to PerformanceMetric
                results.append(PerformanceMetric(
                    id=metric_dict.get("id"),
                    metric_type=metric_dict.get("metric_type"),
                    operation=metric_dict.get("operation"),
                    duration_ms=metric_dict.get("duration_ms"),
                    success=metric_dict.get("success"),
                    error_message=metric_dict.get("error_message"),
                    metadata=metric_dict.get("metadata"),
                    created_at=datetime.fromisoformat(metric_dict.get("created_at"))
                ))
            
            return results
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error getting performance metrics: {str(e)}")
            return []
    
    async def get_validation_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about validation results.
        
        Args:
            start_time: Filter by start time
            end_time: Filter by end time
            
        Returns:
            Dictionary with statistics
        """
        try:
            # Get all validation IDs
            all_validations_key = self._get_key("all_validations", "list")
            
            # Convert time filters to timestamps
            min_score = "-inf"
            max_score = "+inf"
            if start_time:
                min_score = start_time.timestamp()
            if end_time:
                max_score = end_time.timestamp()
            
            # Get IDs from sorted set with time range filter
            validation_ids = self._redis.zrangebyscore(
                all_validations_key,
                min_score,
                max_score,
                withscores=False
            )
            
            if not validation_ids:
                return {
                    "total_validations": 0,
                    "existing_accounts": 0,
                    "verified_emails": 0,
                    "avg_trust_score": 0,
                    "trust_score_distribution": {}
                }
            
            # Process all validation records
            total_validations = len(validation_ids)
            existing_accounts = 0
            verified_emails = 0
            trust_scores = []
            trust_score_distribution = {
                "0-20": 0,
                "20-40": 0,
                "40-60": 0,
                "60-80": 0,
                "80-100": 0,
                "unknown": 0
            }
            
            for val_id in validation_ids:
                # Extract username from ID
                # Format: val_username_timestamp
                parts = val_id.decode().split("_")
                if len(parts) < 2:
                    continue
                
                username = parts[1]
                key = self._get_key("validation", username)
                data = self._redis.get(key)
                
                if not data:
                    continue
                
                record_dict = json.loads(data)
                
                if record_dict.get("exists"):
                    existing_accounts += 1
                
                if record_dict.get("email_verified"):
                    verified_emails += 1
                
                trust_score = record_dict.get("trust_score")
                if trust_score is not None:
                    trust_scores.append(trust_score)
                    
                    # Update distribution
                    if 0 <= trust_score < 20:
                        trust_score_distribution["0-20"] += 1
                    elif 20 <= trust_score < 40:
                        trust_score_distribution["20-40"] += 1
                    elif 40 <= trust_score < 60:
                        trust_score_distribution["40-60"] += 1
                    elif 60 <= trust_score < 80:
                        trust_score_distribution["60-80"] += 1
                    elif 80 <= trust_score <= 100:
                        trust_score_distribution["80-100"] += 1
                    else:
                        trust_score_distribution["unknown"] += 1
            
            # Calculate average trust score
            avg_trust_score = sum(trust_scores) / len(trust_scores) if trust_scores else 0
            
            return {
                "total_validations": total_validations,
                "existing_accounts": existing_accounts,
                "verified_emails": verified_emails,
                "avg_trust_score": avg_trust_score,
                "trust_score_distribution": trust_score_distribution
            }
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error getting validation statistics: {str(e)}")
            return {
                "total_validations": 0,
                "existing_accounts": 0,
                "verified_emails": 0,
                "avg_trust_score": 0,
                "trust_score_distribution": {},
                "error": str(e)
            }
    
    async def clean_expired_cache(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of removed entries
        """
        try:
            # Redis automatically handles expiry, but we still need to remove
            # expired entries from the all_validations set
            all_validations_key = self._get_key("all_validations", "list")
            validation_ids = self._redis.zrange(all_validations_key, 0, -1)
            
            removed = 0
            for val_id in validation_ids:
                # Extract username from ID
                # Format: val_username_timestamp
                parts = val_id.decode().split("_")
                if len(parts) < 2:
                    continue
                
                username = parts[1]
                key = self._get_key("validation", username)
                
                # Check if key exists
                if not self._redis.exists(key):
                    # Remove from all_validations set
                    self._redis.zrem(all_validations_key, val_id)
                    removed += 1
            
            return removed
        except RedisError as e:
            logger.error(f"Error cleaning expired cache: {str(e)}")
            return 0
    
    async def get_recent_validations(
        self,
        limit: int = 10,
        offset: int = 0
    ) -> List[ValidationRecord]:
        """
        Get recent validation results.
        
        Args:
            limit: Maximum number of results
            offset: Result offset
            
        Returns:
            List of ValidationRecord objects
        """
        try:
            # Get recent validation IDs from sorted set
            all_validations_key = self._get_key("all_validations", "list")
            validation_ids = self._redis.zrevrange(
                all_validations_key,
                offset,
                offset + limit - 1,
                withscores=False
            )
            
            results = []
            for val_id in validation_ids:
                # Extract username from ID
                # Format: val_username_timestamp
                parts = val_id.decode().split("_")
                if len(parts) < 2:
                    continue
                
                username = parts[1]
                key = self._get_key("validation", username)
                data = self._redis.get(key)
                
                if not data:
                    continue
                
                record_dict = json.loads(data)
                
                # Convert to ValidationRecord
                results.append(ValidationRecord(
                    id=record_dict.get("id"),
                    username=record_dict.get("username"),
                    exists=record_dict.get("exists"),
                    trust_score=record_dict.get("trust_score"),
                    account_details=record_dict.get("account_details"),
                    email_verified=record_dict.get("email_verified"),
                    email_details=record_dict.get("email_details"),
                    ai_analysis=record_dict.get("ai_analysis"),
                    errors=record_dict.get("errors", []),
                    warnings=record_dict.get("warnings", []),
                    created_at=datetime.fromisoformat(record_dict.get("created_at")),
                    updated_at=datetime.fromisoformat(record_dict.get("updated_at")),
                    cache_expires_at=datetime.fromisoformat(record_dict.get("cache_expires_at"))
                ))
            
            return results
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error getting recent validations: {str(e)}")
            return []
