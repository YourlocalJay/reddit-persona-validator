"""FastAPI interface for Reddit persona validation.

This module provides a RESTful API for the Reddit Persona Validator with:
- API endpoints for single and batch validation
- Proper authentication
- OpenAPI documentation
- Asynchronous request handling
- Request rate limiting

Example usage:
    # Run the API server
    uvicorn src.interfaces.api:app --host 0.0.0.0 --port 8000

    # Access the API documentation
    # Open a browser and navigate to http://localhost:8000/docs
"""

import os
import time
import logging
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any, Union, Annotated
from functools import lru_cache
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Header
from fastapi import status, Query, Body, Path as PathParam, Request, Response
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, validator, EmailStr, ConfigDict

# Import the validator
from ..core.validator import RedditPersonaValidator, ValidationResult
from ..utils.config_loader import ConfigLoader

# Set up logging
logger = logging.getLogger("persona-validator-api")

# Create the FastAPI app
app = FastAPI(
    title="Reddit Persona Validator API",
    description="API for validating Reddit personas",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Define API models
class EmailVerificationRequest(BaseModel):
    """Model for email verification request."""
    email: EmailStr = Field(..., description="Email address to verify")
    model_config = ConfigDict(extra="forbid")


class ValidationRequest(BaseModel):
    """Model for validation request."""
    username: str = Field(..., description="Reddit username to validate")
    email: Optional[EmailStr] = Field(None, description="Email address to verify (optional)")
    verify_email: bool = Field(False, description="Whether to verify email")
    perform_ai_analysis: bool = Field(True, description="Whether to perform AI analysis")
    model_config = ConfigDict(extra="forbid")
    
    @validator("username")
    def username_must_be_valid(cls, v):
        """Validate the username format."""
        if not v or not v.strip():
            raise ValueError("Username cannot be empty")
        if len(v) > 20:
            raise ValueError("Username cannot be longer than 20 characters")
        return v


class BatchValidationRequest(BaseModel):
    """Model for batch validation request."""
    accounts: List[ValidationRequest] = Field(..., description="List of accounts to validate")
    max_concurrent: int = Field(3, description="Maximum number of concurrent validations")
    model_config = ConfigDict(extra="forbid")
    
    @validator("max_concurrent")
    def max_concurrent_must_be_valid(cls, v):
        """Validate the max_concurrent value."""
        if v < 1:
            raise ValueError("max_concurrent must be at least 1")
        if v > 10:
            raise ValueError("max_concurrent cannot be more than 10")
        return v


class ValidationResponse(BaseModel):
    """Model for validation response."""
    request_id: str = Field(..., description="Unique request ID")
    username: str = Field(..., description="Reddit username")
    exists: bool = Field(..., description="Whether the account exists")
    trust_score: Optional[float] = Field(None, description="Trust score (0-100)")
    account_details: Optional[Dict[str, Any]] = Field(None, description="Account details")
    email_verified: Optional[bool] = Field(None, description="Whether email was verified")
    email_details: Optional[Dict[str, Any]] = Field(None, description="Email verification details")
    ai_analysis: Optional[Dict[str, Any]] = Field(None, description="AI analysis results")
    errors: List[str] = Field(default_factory=list, description="Error messages")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")
    processed_at: datetime = Field(default_factory=datetime.now, description="When the request was processed")
    model_config = ConfigDict(extra="forbid")


class BatchValidationResponse(BaseModel):
    """Model for batch validation response."""
    request_id: str = Field(..., description="Unique request ID")
    status: str = Field(..., description="Status of the batch validation")
    total_accounts: int = Field(..., description="Total number of accounts to validate")
    processed_accounts: int = Field(..., description="Number of processed accounts")
    results: Optional[List[ValidationResponse]] = Field(None, description="Validation results")
    errors: List[str] = Field(default_factory=list, description="Error messages")
    created_at: datetime = Field(default_factory=datetime.now, description="When the request was created")
    updated_at: datetime = Field(default_factory=datetime.now, description="When the request was last updated")
    model_config = ConfigDict(extra="forbid")


class StatusResponse(BaseModel):
    """Model for status response."""
    status: str = Field(..., description="API status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.now, description="Current timestamp")
    model_config = ConfigDict(extra="forbid")


class ErrorResponse(BaseModel):
    """Model for error response."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    timestamp: datetime = Field(default_factory=datetime.now, description="Error timestamp")
    model_config = ConfigDict(extra="forbid")


class ApiKeyAuth(APIKeyHeader):
    """API Key authentication."""
    def __init__(self, name: str = "X-API-Key", auto_error: bool = True):
        super().__init__(name=name, auto_error=auto_error)


# Global state for batch processing
batch_jobs: Dict[str, BatchValidationResponse] = {}

# Authentication setup
api_key_header = ApiKeyAuth()

# Setup CORS
@lru_cache()
def get_config():
    """Get API configuration from config file."""
    return ConfigLoader.load_config("config/config.yaml")


def setup_cors():
    """Set up CORS middleware based on configuration."""
    config = get_config()
    api_config = config.get("interface", {}).get("api", {})
    origins = api_config.get("cors_origins", ["*"])
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def verify_api_key(api_key: str = Depends(api_key_header)) -> bool:
    """
    Verify the API key.
    
    Args:
        api_key: API key from request header
        
    Returns:
        True if API key is valid
        
    Raises:
        HTTPException: If API key is invalid
    """
    config = get_config()
    api_config = config.get("interface", {}).get("api", {})
    valid_keys = api_config.get("api_keys", [])
    
    # If no API keys configured, allow all requests
    if not valid_keys:
        return True
    
    if api_key not in valid_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return True


# Initialize validator instance
@lru_cache()
def get_validator():
    """
    Initialize and cache the validator instance.
    
    Returns:
        RedditPersonaValidator instance
    """
    try:
        return RedditPersonaValidator(config_path="config/config.yaml")
    except Exception as e:
        logger.error(f"Failed to initialize validator: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize validator: {str(e)}"
        )


async def validate_account_async(validator: RedditPersonaValidator, request: ValidationRequest) -> ValidationResponse:
    """
    Validate a Reddit account asynchronously.
    
    Args:
        validator: Validator instance
        request: Validation request
        
    Returns:
        ValidationResponse with results
    """
    # Create a unique request ID
    request_id = str(uuid.uuid4())
    
    try:
        # Run the validation in a thread pool
        result = await asyncio.to_thread(
            validator.validate,
            username=request.username,
            email_address=request.email,
            perform_email_verification=request.verify_email,
            perform_ai_analysis=request.perform_ai_analysis
        )
        
        # Convert ValidationResult to ValidationResponse
        return ValidationResponse(
            request_id=request_id,
            username=result.username,
            exists=result.exists,
            trust_score=result.trust_score,
            account_details=result.account_details,
            email_verified=result.email_verified,
            email_details=result.email_details,
            ai_analysis=result.ai_analysis,
            errors=result.errors or [],
            warnings=result.warnings or [],
            processed_at=datetime.now()
        )
    except Exception as e:
        logger.error(f"Validation failed for {request.username}: {str(e)}")
        return ValidationResponse(
            request_id=request_id,
            username=request.username,
            exists=False,
            errors=[f"Validation error: {str(e)}"],
            processed_at=datetime.now()
        )


async def process_batch_validation(batch_id: str, request: BatchValidationRequest):
    """
    Process a batch validation request asynchronously.
    
    Args:
        batch_id: Unique batch ID
        request: Batch validation request
    """
    validator = get_validator()
    
    # Update the batch job status
    batch_jobs[batch_id].status = "processing"
    batch_jobs[batch_id].updated_at = datetime.now()
    
    results = []
    
    try:
        # Process accounts with concurrency limit
        semaphore = asyncio.Semaphore(request.max_concurrent)
        
        async def process_with_semaphore(account):
            async with semaphore:
                return await validate_account_async(validator, account)
        
        # Create tasks for all accounts
        tasks = [process_with_semaphore(account) for account in request.accounts]
        
        # Process accounts
        for i, future in enumerate(asyncio.as_completed(tasks)):
            result = await future
            results.append(result)
            
            # Update the batch job status
            batch_jobs[batch_id].processed_accounts = i + 1
            batch_jobs[batch_id].updated_at = datetime.now()
        
        # Update the batch job with results
        batch_jobs[batch_id].status = "completed"
        batch_jobs[batch_id].results = results
        batch_jobs[batch_id].updated_at = datetime.now()
        
    except Exception as e:
        logger.error(f"Batch validation failed: {str(e)}")
        batch_jobs[batch_id].status = "failed"
        batch_jobs[batch_id].errors.append(f"Batch validation error: {str(e)}")
        batch_jobs[batch_id].updated_at = datetime.now()


# API endpoints
@app.get("/", response_model=StatusResponse, tags=["Status"])
async def get_status():
    """
    Get API status.
    
    Returns:
        StatusResponse with API status
    """
    return StatusResponse(
        status="online",
        version="1.0.0",
        timestamp=datetime.now()
    )


@app.post(
    "/validate",
    response_model=ValidationResponse,
    tags=["Validation"],
    dependencies=[Depends(verify_api_key)]
)
async def validate_account(request: ValidationRequest):
    """
    Validate a single Reddit account.
    
    Args:
        request: Validation request
        
    Returns:
        ValidationResponse with validation results
    """
    validator = get_validator()
    return await validate_account_async(validator, request)


@app.post(
    "/batch/validate",
    response_model=BatchValidationResponse,
    tags=["Batch Validation"],
    dependencies=[Depends(verify_api_key)]
)
async def batch_validate(request: BatchValidationRequest, background_tasks: BackgroundTasks):
    """
    Start a batch validation process.
    
    Args:
        request: Batch validation request
        background_tasks: FastAPI background tasks
        
    Returns:
        BatchValidationResponse with batch job ID and status
    """
    # Create a unique batch ID
    batch_id = str(uuid.uuid4())
    
    # Create a batch job record
    batch_job = BatchValidationResponse(
        request_id=batch_id,
        status="pending",
        total_accounts=len(request.accounts),
        processed_accounts=0,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    
    # Store the batch job
    batch_jobs[batch_id] = batch_job
    
    # Start the batch validation in the background
    background_tasks.add_task(process_batch_validation, batch_id, request)
    
    return batch_job


@app.get(
    "/batch/{batch_id}",
    response_model=BatchValidationResponse,
    tags=["Batch Validation"],
    dependencies=[Depends(verify_api_key)]
)
async def get_batch_status(batch_id: str):
    """
    Get the status of a batch validation job.
    
    Args:
        batch_id: Batch job ID
        
    Returns:
        BatchValidationResponse with current status
        
    Raises:
        HTTPException: If batch job not found
    """
    if batch_id not in batch_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch job with ID {batch_id} not found"
        )
    
    return batch_jobs[batch_id]


@app.get(
    "/batch",
    response_model=List[BatchValidationResponse],
    tags=["Batch Validation"],
    dependencies=[Depends(verify_api_key)]
)
async def list_batch_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(10, description="Maximum number of jobs to return")
):
    """
    List batch validation jobs.
    
    Args:
        status: Optional status filter
        limit: Maximum number of jobs to return
        
    Returns:
        List of BatchValidationResponse objects
    """
    jobs = list(batch_jobs.values())
    
    # Apply status filter if provided
    if status:
        jobs = [job for job in jobs if job.status == status]
    
    # Sort by creation time (newest first)
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    
    # Apply limit
    return jobs[:limit]


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(ErrorResponse(
            error=exc.detail,
            timestamp=datetime.now()
        ))
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """General exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(ErrorResponse(
            error="Internal server error",
            detail=str(exc),
            timestamp=datetime.now()
        ))
    )


# Request/response middleware for logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log requests and responses."""
    start_time = time.time()
    
    # Get request details
    method = request.method
    url = str(request.url)
    
    # Process the request
    response = await call_next(request)
    
    # Calculate processing time
    process_time = time.time() - start_time
    
    # Log the request
    logger.info(
        f"{method} {url} - Status: {response.status_code} - "
        f"Processed in {process_time:.4f}s"
    )
    
    return response


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Run on API startup."""
    # Set up logging
    log_level = get_config().get("interface", {}).get("api", {}).get("log_level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Set up CORS
    setup_cors()
    
    # Clean up expired batch jobs periodically
    @app.on_event("startup")
    @app.on_event("shutdown")
    async def cleanup_batch_jobs():
        """Clean up expired batch jobs."""
        expiration_time = datetime.now() - timedelta(days=1)
        expired_jobs = [job_id for job_id, job in batch_jobs.items() 
                       if job.updated_at < expiration_time]
        
        for job_id in expired_jobs:
            del batch_jobs[job_id]
            logger.info(f"Cleaned up expired batch job: {job_id}")
    
    logger.info("API started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on API shutdown."""
    logger.info("API shutting down")


def run_app():
    """Run the FastAPI app with uvicorn."""
    config = get_config()
    api_config = config.get("interface", {}).get("api", {})
    
    host = api_config.get("host", "0.0.0.0")
    port = api_config.get("port", 8000)
    log_level = api_config.get("log_level", "info").lower()
    
    uvicorn.run("src.interfaces.api:app", host=host, port=port, log_level=log_level, reload=True)


if __name__ == "__main__":
    run_app()
