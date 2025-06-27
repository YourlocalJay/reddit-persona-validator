"""Database module for caching and persistent storage.

This module provides database functionality for the Reddit Persona Validator,
supporting both SQL and NoSQL backends. It handles:
- Caching validation results
- Storing user data
- Managing performance metrics
- Supporting visualization data needs

The module implements connection pooling and transaction management
for optimal performance.

Example usage:
    # Initialize the database
    db = Database.from_config(config_path="config/config.yaml")
    
    # Store validation result
    result_id = await db.store_validation_result(validation_result)
    
    # Retrieve cached result
    cached_result = await db.get_cached_validation("username123")
"""

import os
import json
import logging
import sqlite3
import asyncio
import pickle
from typing import Dict, List, Any, Optional, Union, Tuple, Set, cast, Protocol, Type
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager

import aiosqlite
from pydantic import BaseModel, Field

from ..utils.config_loader import ConfigLoader

# Setup logging
logger = logging.getLogger("persona-validator-db")


class DatabaseConfig(BaseModel):
    """Database configuration model."""
    
    engine: str = Field("sqlite", description="Database engine (sqlite or redis)")
    path: str = Field("data/validator.db", description="Database file path")
    cache_expiry: int = Field(86400, description="Cache expiry time in seconds (default: 24h)")
    pool_size: int = Field(5, description="Connection pool size")
    enable_query_logging: bool = Field(False, description="Enable SQL query logging")
    migration_path: str = Field("migrations", description="Database migration files path")


class ValidationRecord(BaseModel):
    """Model for validation record in the database."""
    
    id: Optional[str] = Field(None, description="Unique ID")
    username: str = Field(..., description="Reddit username")
    exists: bool = Field(..., description="Whether the account exists")
    trust_score: Optional[float] = Field(None, description="Trust score (0-100)")
    account_details: Optional[Dict[str, Any]] = Field(None, description="Account details")
    email_verified: Optional[bool] = Field(None, description="Whether email was verified")
    email_details: Optional[Dict[str, Any]] = Field(None, description="Email verification details")
    ai_analysis: Optional[Dict[str, Any]] = Field(None, description="AI analysis results")
    errors: List[str] = Field(default_factory=list, description="Error messages")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    cache_expires_at: datetime = Field(default_factory=lambda: datetime.now() + timedelta(days=1), 
                                      description="Cache expiry timestamp")


class PerformanceMetric(BaseModel):
    """Model for performance metrics in the database."""
    
    id: Optional[int] = Field(None, description="Unique ID")
    metric_type: str = Field(..., description="Type of metric (validation, api_request, analysis)")
    operation: str = Field(..., description="Operation name")
    duration_ms: float = Field(..., description="Duration in milliseconds")
    success: bool = Field(True, description="Whether the operation succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")


class DatabaseInterface(Protocol):
    """Protocol defining the database interface."""
    
    async def initialize(self) -> None:
        """Initialize the database."""
        ...
    
    async def close(self) -> None:
        """Close database connections."""
        ...
    
    async def get_cached_validation(self, username: str) -> Optional[ValidationRecord]:
        """Get cached validation result."""
        ...
    
    async def store_validation_result(self, result: ValidationRecord) -> str:
        """Store validation result."""
        ...
    
    async def record_performance_metric(self, metric: PerformanceMetric) -> int:
        """Record performance metric."""
        ...
    
    async def get_performance_metrics(
        self,
        metric_type: Optional[str] = None,
        operation: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PerformanceMetric]:
        """Get performance metrics."""
        ...
    
    async def get_validation_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get validation statistics."""
        ...
    
    async def clean_expired_cache(self) -> int:
        """Clean expired cache entries."""
        ...
    
    async def get_recent_validations(
        self,
        limit: int = 10,
        offset: int = 0
    ) -> List[ValidationRecord]:
        """Get recent validations."""
        ...


class Database:
    """Database manager for the Reddit Persona Validator."""
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize the database manager.
        
        Args:
            config: Database configuration
        """
        self.config = config
        self._connection_pool: List[aiosqlite.Connection] = []
        self._pool_lock = asyncio.Lock()
        self._initialized = False
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(config.path), exist_ok=True)
    
    @classmethod
    def from_config(cls, config_path: str = "config/config.yaml") -> Union["Database", "DatabaseInterface"]:
        """
        Create a database instance from configuration file.
        
        This factory method returns either a SQLite or Redis implementation
        based on the configuration.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Database instance (SQLite or Redis)
        """
        config_data = ConfigLoader.load_config(config_path)
        db_config = DatabaseConfig(**config_data.get("database", {}))
        
        # Check if Redis is enabled and available
        redis_config = config_data.get("database", {}).get("redis", {})
        if db_config.engine == "redis" or redis_config.get("enabled", False):
            try:
                # Import Redis implementation
                from .redis_store import RedisStore
                logger.info("Using Redis storage backend")
                return RedisStore.from_config(config_path)
            except ImportError:
                logger.warning("Redis package not installed, falling back to SQLite")
                return cls(db_config)
        
        # Default to SQLite
        logger.info("Using SQLite storage backend")
        return cls(db_config)
    
    async def initialize(self) -> None:
        """
        Initialize the database: create tables, indexes, and connection pool.
        
        This method must be called before using the database.
        """
        if self._initialized:
            return
        
        async with self._get_connection() as conn:
            # Create tables if they don't exist
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS validation_results (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                exists BOOLEAN NOT NULL,
                trust_score REAL,
                account_details TEXT,
                email_verified BOOLEAN,
                email_details TEXT,
                ai_analysis TEXT,
                errors TEXT,
                warnings TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                cache_expires_at TIMESTAMP NOT NULL
            )
            """)
            
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_type TEXT NOT NULL,
                operation TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                metadata TEXT,
                created_at TIMESTAMP NOT NULL
            )
            """)
            
            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_validation_username ON validation_results(username)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_validation_expiry ON validation_results(cache_expires_at)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_performance_type_op ON performance_metrics(metric_type, operation)")
            
            await conn.commit()
        
        # Initialize connection pool
        for _ in range(self.config.pool_size):
            conn = await self._create_connection()
            self._connection_pool.append(conn)
        
        self._initialized = True
        logger.info(f"Database initialized: {self.config.path}")
    
    async def close(self) -> None:
        """Close all database connections and release resources."""
        if not self._initialized:
            return
        
        async with self._pool_lock:
            for conn in self._connection_pool:
                await conn.close()
            self._connection_pool.clear()
        
        self._initialized = False
        logger.info("Database connections closed")
    
    async def _create_connection(self) -> aiosqlite.Connection:
        """
        Create a new database connection.
        
        Returns:
            SQLite connection
        """
        conn = await aiosqlite.connect(self.config.path)
        # Enable foreign keys
        await conn.execute("PRAGMA foreign_keys = ON")
        # Use WAL mode for better concurrency
        await conn.execute("PRAGMA journal_mode = WAL")
        # Set busy timeout to avoid "database is locked" errors
        await conn.execute("PRAGMA busy_timeout = 5000")
        return conn
    
    @asynccontextmanager
    async def _get_connection(self):
        """
        Get a connection from the pool.
        
        Yields:
            Database connection
        """
        if not self._initialized and not self._connection_pool:
            # Create a single connection if not initialized
            conn = await self._create_connection()
            try:
                yield conn
            finally:
                await conn.close()
            return
        
        # Get connection from pool
        async with self._pool_lock:
            if not self._connection_pool:
                # All connections are in use, create a new one
                conn = await self._create_connection()
                try:
                    yield conn
                finally:
                    await conn.close()
                return
            
            # Use connection from pool
            conn = self._connection_pool.pop(0)
        
        try:
            yield conn
        finally:
            # Return connection to pool
            async with self._pool_lock:
                self._connection_pool.append(conn)
    
    async def get_cached_validation(self, username: str) -> Optional[ValidationRecord]:
        """
        Get a cached validation result for a username.
        
        Args:
            username: Reddit username
            
        Returns:
            ValidationRecord if found and not expired, None otherwise
        """
        async with self._get_connection() as conn:
            # Query for non-expired cache entry
            cursor = await conn.execute(
                """
                SELECT id, username, exists, trust_score, account_details, 
                       email_verified, email_details, ai_analysis, errors,
                       warnings, created_at, updated_at, cache_expires_at
                FROM validation_results
                WHERE username = ? AND cache_expires_at > ?
                """,
                (username, datetime.now())
            )
            
            row = await cursor.fetchone()
            if not row:
                return None
            
            # Convert row to ValidationRecord
            return ValidationRecord(
                id=row[0],
                username=row[1],
                exists=bool(row[2]),
                trust_score=row[3],
                account_details=json.loads(row[4]) if row[4] else None,
                email_verified=bool(row[5]) if row[5] is not None else None,
                email_details=json.loads(row[6]) if row[6] else None,
                ai_analysis=json.loads(row[7]) if row[7] else None,
                errors=json.loads(row[8]) if row[8] else [],
                warnings=json.loads(row[9]) if row[9] else [],
                created_at=datetime.fromisoformat(row[10]),
                updated_at=datetime.fromisoformat(row[11]),
                cache_expires_at=datetime.fromisoformat(row[12])
            )
    
    async def store_validation_result(self, result: ValidationRecord) -> str:
        """
        Store a validation result in the database.
        
        Args:
            result: Validation result to store
            
        Returns:
            ID of the stored record
        """
        # Generate ID if not provided
        if result.id is None:
            result.id = f"val_{result.username}_{int(datetime.now().timestamp())}"
        
        # Calculate cache expiry time if not set
        if result.cache_expires_at is None:
            result.cache_expires_at = datetime.now() + timedelta(seconds=self.config.cache_expiry)
        
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO validation_results
                (id, username, exists, trust_score, account_details, email_verified,
                 email_details, ai_analysis, errors, warnings, created_at, 
                 updated_at, cache_expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.id,
                    result.username,
                    result.exists,
                    result.trust_score,
                    json.dumps(result.account_details) if result.account_details else None,
                    result.email_verified,
                    json.dumps(result.email_details) if result.email_details else None,
                    json.dumps(result.ai_analysis) if result.ai_analysis else None,
                    json.dumps(result.errors) if result.errors else "[]",
                    json.dumps(result.warnings) if result.warnings else "[]",
                    result.created_at.isoformat(),
                    result.updated_at.isoformat(),
                    result.cache_expires_at.isoformat()
                )
            )
            await conn.commit()
        
        return result.id
    
    async def record_performance_metric(self, metric: PerformanceMetric) -> int:
        """
        Record a performance metric in the database.
        
        Args:
            metric: Performance metric to record
            
        Returns:
            ID of the recorded metric
        """
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO performance_metrics
                (metric_type, operation, duration_ms, success, error_message,
                 metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric.metric_type,
                    metric.operation,
                    metric.duration_ms,
                    metric.success,
                    metric.error_message,
                    json.dumps(metric.metadata) if metric.metadata else None,
                    metric.created_at.isoformat()
                )
            )
            await conn.commit()
            
            return cursor.lastrowid
    
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
        Get performance metrics from the database.
        
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
        query = "SELECT * FROM performance_metrics WHERE 1=1"
        params = []
        
        if metric_type:
            query += " AND metric_type = ?"
            params.append(metric_type)
        
        if operation:
            query += " AND operation = ?"
            params.append(operation)
        
        if start_time:
            query += " AND created_at >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND created_at <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(PerformanceMetric(
                    id=row[0],
                    metric_type=row[1],
                    operation=row[2],
                    duration_ms=row[3],
                    success=bool(row[4]),
                    error_message=row[5],
                    metadata=json.loads(row[6]) if row[6] else None,
                    created_at=datetime.fromisoformat(row[7])
                ))
            
            return results
    
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
        query = """
        SELECT 
            COUNT(*) as total_validations,
            SUM(CASE WHEN exists = 1 THEN 1 ELSE 0 END) as existing_accounts,
            SUM(CASE WHEN email_verified = 1 THEN 1 ELSE 0 END) as verified_emails,
            AVG(trust_score) as avg_trust_score
        FROM validation_results
        WHERE 1=1
        """
        params = []
        
        if start_time:
            query += " AND created_at >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND created_at <= ?"
            params.append(end_time.isoformat())
        
        async with self._get_connection() as conn:
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            
            # Get distribution of trust scores
            trust_score_query = """
            SELECT 
                CASE 
                    WHEN trust_score BETWEEN 0 AND 20 THEN '0-20'
                    WHEN trust_score BETWEEN 20 AND 40 THEN '20-40'
                    WHEN trust_score BETWEEN 40 AND 60 THEN '40-60'
                    WHEN trust_score BETWEEN 60 AND 80 THEN '60-80'
                    WHEN trust_score BETWEEN 80 AND 100 THEN '80-100'
                    ELSE 'unknown'
                END as score_range,
                COUNT(*) as count
            FROM validation_results
            WHERE trust_score IS NOT NULL
            """
            
            if start_time:
                trust_score_query += " AND created_at >= ?"
            
            if end_time:
                trust_score_query += " AND created_at <= ?"
            
            trust_score_query += " GROUP BY score_range ORDER BY score_range"
            
            cursor = await conn.execute(trust_score_query, params)
            trust_score_rows = await cursor.fetchall()
            
            trust_score_distribution = {row[0]: row[1] for row in trust_score_rows}
            
            return {
                "total_validations": row[0],
                "existing_accounts": row[1] or 0,
                "verified_emails": row[2] or 0,
                "avg_trust_score": row[3] or 0,
                "trust_score_distribution": trust_score_distribution
            }
    
    async def clean_expired_cache(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of removed entries
        """
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM validation_results WHERE cache_expires_at < ?",
                (datetime.now().isoformat(),)
            )
            await conn.commit()
            
            return cursor.rowcount
    
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
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, username, exists, trust_score, account_details, 
                       email_verified, email_details, ai_analysis, errors,
                       warnings, created_at, updated_at, cache_expires_at
                FROM validation_results
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset)
            )
            
            rows = await cursor.fetchall()
            
            results = []
            for row in rows:
                results.append(ValidationRecord(
                    id=row[0],
                    username=row[1],
                    exists=bool(row[2]),
                    trust_score=row[3],
                    account_details=json.loads(row[4]) if row[4] else None,
                    email_verified=bool(row[5]) if row[5] is not None else None,
                    email_details=json.loads(row[6]) if row[6] else None,
                    ai_analysis=json.loads(row[7]) if row[7] else None,
                    errors=json.loads(row[8]) if row[8] else [],
                    warnings=json.loads(row[9]) if row[9] else [],
                    created_at=datetime.fromisoformat(row[10]),
                    updated_at=datetime.fromisoformat(row[11]),
                    cache_expires_at=datetime.fromisoformat(row[12])
                ))
            
            return results
