import re
import logging
from fastapi import Request, HTTPException
from pydantic import BaseModel, validator, HttpUrl, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import json
import urllib.parse

# Configure logging
logger = logging.getLogger(__name__)

# Common validation patterns
URL_PATTERN = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+'
EMAIL_PATTERN = r'^[\w\.-]+@([\w-]+\.)+[\w-]{2,4}$'
PHONE_PATTERN = r'^\+?[0-9]{8,15}$'

class ValidationError(HTTPException):
    """Custom validation error with detailed context"""
    def __init__(self, detail: str, field: Optional[str] = None):
        status_code = 400
        if field:
            detail = f"Validation error in field '{field}': {detail}"
        super().__init__(status_code=status_code, detail=detail)
        self.field = field

class ProductURLInput(BaseModel):
    """Validate product URL input"""
    url: HttpUrl = Field(..., description="Product URL to analyze")
    
    @validator('url')
    def validate_url(cls, v):
        # Convert to string for regex validation
        url_str = str(v)
        
        # Check if URL matches pattern
        if not re.match(URL_PATTERN, url_str):
            raise ValueError("Invalid URL format")
        
        # Check for malicious patterns
        malicious_patterns = [
            'javascript:',
            'data:',
            'vbscript:',
            '<script',
            'onload=',
            'onerror='
        ]
        
        for pattern in malicious_patterns:
            if pattern in url_str.lower():
                logger.warning(f"Potentially malicious URL detected: {url_str}")
                raise ValueError("URL contains potentially malicious content")
        
        # Validate URL length
        if len(url_str) > 2048:
            raise ValueError("URL exceeds maximum length of 2048 characters")
        
        # Validate URL scheme
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("URL must use HTTP or HTTPS protocol")
        
        return v

class ImageAnalysisInput(BaseModel):
    """Validate image analysis input"""
    # This will be validated by FastAPI's File handling
    # Additional validation happens in the endpoint handler
    pass

class FeedbackInput(BaseModel):
    """Validate user feedback input"""
    product_id: str = Field(..., description="ID of the analyzed product")
    rating: int = Field(..., description="User rating (1-5)")
    comment: Optional[str] = Field(None, description="User comment")
    
    @validator('product_id')
    def validate_product_id(cls, v):
        if not v or not isinstance(v, str) or len(v) < 5:
            raise ValueError("Invalid product ID")
        return v
    
    @validator('rating')
    def validate_rating(cls, v):
        if not isinstance(v, int) or v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5")
        return v
    
    @validator('comment')
    def validate_comment(cls, v):
        if v and len(v) > 1000:
            raise ValueError("Comment exceeds maximum length of 1000 characters")
        return v

class ContactInput(BaseModel):
    """Validate contact form input"""
    name: str = Field(..., description="User's name")
    email: str = Field(..., description="User's email")
    message: str = Field(..., description="User's message")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v) > 100:
            raise ValueError("Name must be between 1 and 100 characters")
        return v
    
    @validator('email')
    def validate_email(cls, v):
        if not re.match(EMAIL_PATTERN, v):
            raise ValueError("Invalid email format")
        return v
    
    @validator('message')
    def validate_message(cls, v):
        if not v or len(v) > 2000:
            raise ValueError("Message must be between 1 and 2000 characters")
        return v

async def validate_request_body(request: Request) -> Dict[str, Any]:
    """Validate request body and return parsed JSON"""
    try:
        body = await request.json()
        return body
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in request body")
        raise ValidationError("Invalid JSON in request body")

async def validate_request_params(request: Request) -> Dict[str, str]:
    """Validate request query parameters"""
    params = dict(request.query_params)
    
    # Validate each parameter
    for key, value in params.items():
        # Check for SQL injection patterns
        sql_patterns = [
            "'--",
            "OR 1=1",
            "DROP TABLE",
            ";",
            "UNION SELECT",
            "EXEC(",
            "EXECUTE("
        ]
        
        for pattern in sql_patterns:
            if pattern.lower() in value.lower():
                logger.warning(f"Potential SQL injection detected in parameter '{key}': {value}")
                raise ValidationError(f"Invalid characters in parameter '{key}'")
        
        # Check for XSS patterns
        xss_patterns = [
            "<script",
            "javascript:",
            "onload=",
            "onerror=",
            "onclick=",
            "alert("
        ]
        
        for pattern in xss_patterns:
            if pattern.lower() in value.lower():
                logger.warning(f"Potential XSS detected in parameter '{key}': {value}")
                raise ValidationError(f"Invalid characters in parameter '{key}'")
    
    return params

async def validate_headers(request: Request) -> None:
    """Validate request headers"""
    headers = request.headers
    
    # Check for required headers
    if 'content-type' in headers and 'application/json' in headers['content-type'].lower():
        if request.method in ['POST', 'PUT', 'PATCH'] and not headers.get('content-length'):
            raise ValidationError("Missing Content-Length header for request with body")
    
    # Check for suspicious headers
    suspicious_headers = [
        'X-Forwarded-For',
        'X-Real-IP',
        'X-Remote-Addr'
    ]
    
    for header in suspicious_headers:
        if header in headers and headers[header] != request.client.host:
            logger.warning(f"Suspicious header detected: {header}={headers[header]}")
    
    return None

async def validate_request(request: Request) -> Dict[str, Any]:
    """Comprehensive request validation"""
    # Validate headers
    await validate_headers(request)
    
    # Validate query parameters
    params = await validate_request_params(request)
    
    # Validate request body for appropriate methods
    body = None
    if request.method in ['POST', 'PUT', 'PATCH']:
        content_type = request.headers.get('content-type', '')
        if 'application/json' in content_type.lower():
            body = await validate_request_body(request)
    
    return {
        'params': params,
        'body': body
    }

async def validation_middleware(request: Request, call_next):
    """Middleware to validate all incoming requests"""
    try:
        # Validate the request
        await validate_request(request)
        
        # Process the request
        response = await call_next(request)
        return response
    
    except ValidationError as e:
        logger.warning(f"Validation error: {e.detail}")
        return HTTPException(status_code=400, detail=e.detail)
    
    except Exception as e:
        logger.error(f"Unexpected error in validation middleware: {e}")
        return HTTPException(status_code=500, detail="Internal server error")