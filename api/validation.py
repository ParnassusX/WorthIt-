from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError, HttpUrl
from typing import Dict, List, Any, Optional
import re
import logging
import json
from datetime import datetime
import uuid

# Configure validation logger with enhanced formatting and security
validation_logger = logging.getLogger('validation')
file_handler = logging.FileHandler('validation.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(context)s'))
validation_logger.addHandler(file_handler)
validation_logger.setLevel(logging.INFO)

# Token rotation and rate limiting settings
from datetime import timedelta
from fastapi import HTTPException
from typing import Dict, Set
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.blocked_ips: Set[str] = set()
        self.block_duration = timedelta(minutes=30)  # Increased from 15 to 30 minutes
        self.last_cleanup = time.time()
        self.suspicious_activity: Dict[str, int] = defaultdict(int)
        self.max_suspicious_count = 3  # Block after 3 suspicious activities
    
    def is_rate_limited(self, ip: str, request: Request = None) -> bool:
        current_time = time.time()
        
        # Cleanup old records every minute
        if current_time - self.last_cleanup > 60:
            self._cleanup()
            self.last_cleanup = current_time
        
        # Check if IP is blocked
        if ip in self.blocked_ips:
            validation_logger.warning(f"Blocked IP attempting request: {ip}")
            return True
        
        # Enhanced request pattern analysis
        if request:
            if self._detect_suspicious_pattern(ip, request):
                self.suspicious_activity[ip] += 1
                if self.suspicious_activity[ip] >= self.max_suspicious_count:
                    self.blocked_ips.add(ip)
                    validation_logger.warning(f"IP blocked due to suspicious activity: {ip}")
                    return True
        
        # Remove requests older than 1 minute
        self.requests[ip] = [req_time for req_time in self.requests[ip] 
                            if current_time - req_time < 60]
        
        # Add current request
        self.requests[ip].append(current_time)
        
        # Progressive rate limiting
        request_count = len(self.requests[ip])
        if request_count > self.requests_per_minute:
            self.blocked_ips.add(ip)
            validation_logger.warning(f"IP blocked for exceeding rate limit: {ip}")
            return True
        elif request_count > (self.requests_per_minute * 0.8):
            validation_logger.warning(f"IP approaching rate limit: {ip}")
        
        return False
    
    def _detect_suspicious_pattern(self, ip: str, request: Request) -> bool:
        # Check for rapid successive requests
        if len(self.requests[ip]) >= 5:
            last_5_requests = sorted(self.requests[ip][-5:])
            if last_5_requests[-1] - last_5_requests[0] < 1:  # 5 requests within 1 second
                return True
        
        # Check for suspicious headers or patterns
        headers = request.headers
        suspicious_patterns = [
            not headers.get('User-Agent'),
            headers.get('User-Agent', '').lower() in ['', 'python-requests', 'curl'],
            not headers.get('Accept'),
            headers.get('X-Forwarded-For') and headers.get('X-Forwarded-For') != ip
        ]
        
        return sum(suspicious_patterns) >= 2
    
    def _cleanup(self):
        current_time = time.time()
        # Remove old blocked IPs
        self.blocked_ips = {ip for ip in self.blocked_ips 
                           if current_time - min(self.requests[ip]) < self.block_duration.total_seconds()}
        # Cleanup old request records
        for ip in list(self.requests.keys()):
            if not self.requests[ip]:
                del self.requests[ip]

# Initialize rate limiter
rate_limiter = RateLimiter()

# Base Models for Request Validation
class ProductURL(BaseModel):
    url: HttpUrl
    
    @classmethod
    def validate_marketplace(cls, url: str) -> bool:
        valid_domains = r'^https?://([a-z0-9\.-]+\.)?(amazon|ebay)\.(it|com|co\.uk|de|fr|es|in|ca|com\.au|com\.br|nl|pl|se|sg)'
        return bool(re.match(valid_domains, url, re.IGNORECASE))
    
    @classmethod
    def sanitize_url(cls, url: str) -> str:
        # Remove any whitespace and normalize
        url = url.strip().lower()
        # Ensure proper protocol
        if not url.startswith('http'):
            url = 'https://' + url
        return url

class ReviewData(BaseModel):
    text: str
    rating: float
    date: str
    verified: bool = False
    
    @classmethod
    def sanitize_text(cls, text: str) -> str:
        # Remove any HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Remove excessive whitespace
        text = ' '.join(text.split())
        return text
    
    @classmethod
    def validate_rating(cls, rating: float) -> bool:
        return 0.0 <= rating <= 5.0

# Enhanced validation middleware with security audit logging
async def validation_middleware(request: Request, call_next):
    try:
        # Rate limiting check
        client_ip = request.client.host
        if rate_limiter.is_rate_limited(client_ip):
            validation_logger.warning(
                'Rate limit exceeded',
                extra={'context': json.dumps({'client_ip': client_ip})}
            )
            return JSONResponse(
                status_code=429,
                content={
                    'error': 'Too many requests',
                    'message': 'Rate limit exceeded. Please try again later.',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
        
        # Security audit logging
        request_id = str(uuid.uuid4())
        audit_context = {
            'request_id': request_id,
            'client_ip': client_ip,
            'method': request.method,
            'path': str(request.url.path),
            'user_agent': request.headers.get('user-agent', 'unknown'),
            'origin': request.headers.get('origin', 'unknown'),
            'timestamp': datetime.utcnow().isoformat()
        }
        validation_logger.info(
            'Request received',
            extra={'audit': json.dumps(audit_context)}
        )
        
        # Get request body
        body = await request.json()
        
        # Enhanced security logging with origin validation
        context = {
            'endpoint': str(request.url),
            'method': request.method,
            'client_host': request.client.host,
            'origin': request.headers.get('origin', 'unknown'),
            'user_agent': request.headers.get('user-agent', 'unknown'),
            'x_forwarded_for': request.headers.get('x-forwarded-for', 'unknown'),
            'timestamp': datetime.utcnow().isoformat(),
            'request_id': request.headers.get('x-request-id', str(uuid.uuid4()))
        }
        
        # Validate request origin
        allowed_origins = ['https://worthit-app.com', 'https://api.worthit-app.com']
        origin = request.headers.get('origin')
        if origin and origin not in allowed_origins:
            validation_logger.warning(
                'Invalid request origin',
                extra={'context': json.dumps({**context, 'error': 'Invalid origin'})}
            )
            return JSONResponse(
                status_code=403,
                content={
                    'error': 'Invalid request origin',
                    'timestamp': datetime.utcnow().isoformat()
                }
            )
        
        # Validate based on endpoint
        if 'product' in str(request.url):
            ProductURL(**body)
        elif 'review' in str(request.url):
            ReviewData(**body)
        
        # Log successful validation with enhanced context
        validation_logger.info(
            'Request validation successful',
            extra={'context': json.dumps(context)}
        )
        
        response = await call_next(request)
        return response
        
    except ValidationError as e:
        # Enhanced error logging with security context
        error_context = {
            **context,
            'error_type': 'ValidationError',
            'error_details': str(e),
            'invalid_fields': [err['loc'][0] for err in e.errors()]
        }
        validation_logger.error(
            'Request validation failed',
            extra={'context': json.dumps(error_context)}
        )
        return JSONResponse(
            status_code=400,
            content={
                'error': 'Validation Error',
                'details': e.errors(),
                'timestamp': datetime.utcnow().isoformat(),
                'request_id': context['request_id']
            }
        )
    except Exception as e:
        # Log unexpected errors with security context
        error_context = {
            **context,
            'error_type': type(e).__name__,
            'error_details': str(e)
        }
        validation_logger.error(
            'Unexpected validation error',
            extra={'context': json.dumps(error_context)}
        )
        return JSONResponse(
            status_code=500,
            content={
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred during validation',
                'timestamp': datetime.utcnow().isoformat(),
                'request_id': context['request_id']
            }
        )

class ProductData(BaseModel):
    title: str
    price: float
    currency: str
    description: Optional[str]
    reviews: List[ReviewData]
    metadata: Dict[str, Any] = {}

# Request Sanitization
def sanitize_request_data(data: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Remove any potential script tags and normalize whitespace
            value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.DOTALL)
            value = ' '.join(value.split())
        sanitized[key] = value
    return sanitized

# Validation Middleware
async def validation_middleware(request: Request, call_next):
    try:
        # Skip validation for GET requests or documentation endpoints
        path = request.url.path
        if request.method == "GET" or path in ["/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
            
        # Get and sanitize request body
        body = await request.json()
        body = sanitize_request_data(body)
        
        # Validate based on endpoint
        path = request.url.path
        if path.endswith('/scrape') or path.endswith('/analyze/product'):
            # Sanitize and validate URL
            if 'url' in body:
                body['url'] = ProductURL.sanitize_url(body['url'])
            url = ProductURL(url=body['url'])
            if not ProductURL.validate_marketplace(str(url.url)):
                validation_logger.warning(f"Invalid marketplace URL: {url.url}")
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid marketplace URL"}
                )
        
        elif path.endswith('/analyze/pros-cons'):
            # Validate and sanitize product data
            if 'product_data' in body:
                product_data = ProductData(**body['product_data'])
            
            # Validate and sanitize reviews
            if 'reviews' in body:
                sanitized_reviews = []
                for review in body['reviews']:
                    if isinstance(review, str):
                        # Handle string reviews (from tests)
                        sanitized_reviews.append(ReviewData.sanitize_text(review))
                    else:
                        # Handle review objects
                        if 'text' in review:
                            review['text'] = ReviewData.sanitize_text(review['text'])
                        if 'rating' in review and not ReviewData.validate_rating(review['rating']):
                            validation_logger.warning(f"Invalid rating value: {review['rating']}")
                            return JSONResponse(
                                status_code=400,
                                content={"error": "Invalid rating value. Must be between 0 and 5"}
                            )
                        sanitized_reviews.append(ReviewData(**review))
                reviews = sanitized_reviews
            
        validation_logger.info(f"Validation successful for {path}")
        response = await call_next(request)
        return response
        
    except ValidationError as e:
        validation_logger.error(f"Validation error: {str(e)}")
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation error",
                "detail": e.errors()
            }
        )
    except Exception as e:
        validation_logger.error(f"Unexpected error during validation: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Validation error: {str(e)}"}
        )

class ValidationMonitor:
    def __init__(self):
        self.validation_stats = defaultdict(lambda: defaultdict(int))
        self.last_cleanup = datetime.now()
        self.cleanup_interval = timedelta(hours=1)
    
    def record_validation(self, validation_type: str, success: bool, details: Optional[Dict] = None):
        current_time = datetime.now()
        if current_time - self.last_cleanup > self.cleanup_interval:
            self._cleanup()
        
        status = 'success' if success else 'failure'
        self.validation_stats[validation_type][status] += 1
        
        # Log validation event
        log_data = {
            'validation_type': validation_type,
            'status': status,
            'timestamp': current_time.isoformat(),
            'details': details or {}
        }
        validation_logger.info(json.dumps(log_data))
    
    def _cleanup(self):
        self.validation_stats.clear()
        self.last_cleanup = datetime.now()

# Initialize validation monitor
validation_monitor = ValidationMonitor()

class EnhancedValidation:
    @staticmethod
    def validate_input(value: Any, validation_type: str, rules: Dict = None) -> tuple[bool, str]:
        try:
            if rules is None:
                rules = {}
            
            # Basic type validation
            if not isinstance(value, (str, int, float, bool, dict, list)):
                raise ValueError(f"Unsupported input type: {type(value)}")
            
            # Length validation for strings
            if isinstance(value, str):
                max_length = rules.get('max_length', 1000)
                if len(value) > max_length:
                    raise ValueError(f"Input exceeds maximum length of {max_length}")
                
                # Pattern validation if specified
                if pattern := rules.get('pattern'):
                    if not re.match(pattern, value):
                        raise ValueError("Input does not match required pattern")
            
            # Range validation for numbers
            if isinstance(value, (int, float)):
                min_val = rules.get('min', float('-inf'))
                max_val = rules.get('max', float('inf'))
                if not (min_val <= value <= max_val):
                    raise ValueError(f"Value must be between {min_val} and {max_val}")
            
            validation_monitor.record_validation(validation_type, True)
            return True, ""
            
        except Exception as e:
            validation_monitor.record_validation(validation_type, False, {'error': str(e)})
            return False, str(e)

    @staticmethod
    def validate_request_data(data: Dict, schema: Dict) -> tuple[bool, List[str]]:
        errors = []
        for field, rules in schema.items():
            if field not in data and rules.get('required', False):
                errors.append(f"Missing required field: {field}")
                continue
                
            if field in data:
                success, error = EnhancedValidation.validate_input(
                    data[field],
                    f"field_{field}",
                    rules
                )
                if not success:
                    errors.append(f"Validation failed for {field}: {error}")
        
        return len(errors) == 0, errors