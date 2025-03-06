from fastapi import HTTPException, Request, Depends
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
import re
import redis
import json
import logging
import secrets
import hashlib
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict

# Redis client for rate limiting
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Rate limiting configuration
MAX_REQUESTS = 100  # Maximum requests per window
TIME_WINDOW = 3600  # Time window in seconds (1 hour)
BURST_LIMIT = 10  # Maximum burst requests per minute
BURST_WINDOW = 60  # Burst window in seconds

# Rate limit bypass protection
MAX_IPS_PER_KEY = 5  # Maximum number of IPs per API key
IP_TRACKING_WINDOW = 3600  # Window for tracking IPs (1 hour)
SUSPICIOUS_REQUESTS_THRESHOLD = 50  # Threshold for suspicious activity

# Degradation thresholds
DEGRADATION_THRESHOLD = 0.9  # Start degrading at 90% of limit
DEGRADATION_TTL = 300  # Degradation time to live (5 minutes)

# API Key rotation configuration
KEY_ROTATION_INTERVAL = timedelta(days=30)  # Default rotation interval
KEY_GRACE_PERIOD = timedelta(days=7)  # Grace period for old keys

# Setup security audit logger
security_logger = logging.getLogger('security_audit')
file_handler = logging.FileHandler('security_audit.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
security_logger.addHandler(file_handler)
security_logger.setLevel(logging.INFO)

class KeyRotationManager:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.rotation_interval = KEY_ROTATION_INTERVAL
        self.grace_period = KEY_GRACE_PERIOD

    async def generate_api_key(self) -> str:
        """Generate a new API key with enhanced entropy"""
        return secrets.token_urlsafe(32)

    async def store_api_key(self, api_key: str, user_id: str, expiry: datetime) -> bool:
        """Store API key with metadata in Redis"""
        key_data = {
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': expiry.isoformat(),
            'is_active': True
        }
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        try:
            await self.redis_client.setex(
                f'api_key:{key_hash}',
                int((expiry - datetime.utcnow()).total_seconds()),
                json.dumps(key_data)
            )
            await log_security_event('api_key_created', {
                'user_id': user_id,
                'expiry': expiry.isoformat()
            })
            return True
        except Exception as e:
            await log_security_event('api_key_creation_failed', {
                'error': str(e)
            }, 'ERROR')
            return False

    async def rotate_key(self, user_id: str) -> tuple[str, str]:
        """Generate a new API key and invalidate the old one after grace period"""
        new_key = await self.generate_api_key()
        expiry = datetime.utcnow() + self.rotation_interval
        
        if await self.store_api_key(new_key, user_id, expiry):
            # Schedule old key invalidation
            old_key_expiry = datetime.utcnow() + self.grace_period
            await self.schedule_key_invalidation(user_id, old_key_expiry)
            
            await log_security_event('api_key_rotated', {
                'user_id': user_id,
                'grace_period_ends': old_key_expiry.isoformat()
            })
            return new_key, expiry.isoformat()
        raise HTTPException(status_code=500, detail="Failed to rotate API key")

    async def schedule_key_invalidation(self, user_id: str, expiry: datetime) -> None:
        """Schedule invalidation of old API keys"""
        await self.redis_client.setex(
            f'key_invalidation:{user_id}',
            int((expiry - datetime.utcnow()).total_seconds()),
            'pending'
        )

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate API key and check if it's active"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_data = await self.redis_client.get(f'api_key:{key_hash}')
        
        if not key_data:
            await log_security_event('api_key_validation_failed', {
                'reason': 'key_not_found'
            }, 'WARNING')
            return False
        
        key_info = json.loads(key_data)
        if not key_info.get('is_active', False):
            await log_security_event('api_key_validation_failed', {
                'reason': 'key_inactive',
                'user_id': key_info.get('user_id')
            }, 'WARNING')
            return False
        
        return True

# Security audit functions
async def log_security_event(event_type: str, details: dict, severity: str = 'INFO'):
    """Log security-related events with context"""
    log_data = {
        'event_type': event_type,
        'timestamp': datetime.utcnow().isoformat(),
        'details': details,
        'severity': severity
    }
    security_logger.info(json.dumps(log_data))

# CORS and Origin validation configuration
ALLOWED_ORIGINS = {
    'https://worthit-app.com',
    'https://api.worthit-app.com',
    'https://bot.worthit-app.com'
}

# CORS middleware configuration
def setup_cors(app):
    """Configure CORS middleware for the application"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600
    )
    return app

async def validate_origin(request: Request) -> bool:
    """Validate request origin against allowed origins"""
    origin = request.headers.get('Origin')
    if not origin:
        await log_security_event('origin_validation_failed', 
            {'reason': 'missing_origin'}, 'WARNING')
        raise HTTPException(status_code=403, detail="Origin validation failed")
    
    if origin not in ALLOWED_ORIGINS:
        await log_security_event('origin_validation_failed',
            {'reason': 'invalid_origin', 'origin': origin}, 'WARNING')
        raise HTTPException(status_code=403, detail="Invalid origin")
    
    return True

def sanitize_input(value: str) -> str:
    """Enhanced input sanitization to prevent injection attacks"""
    if not isinstance(value, str):
        return str(value)

    # Remove any potential script tags and event handlers
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r'on\w+=".*?"', '', value, flags=re.IGNORECASE)
    
    # Remove other potentially dangerous HTML tags and attributes
    value = re.sub(r'<[^>]+>', '', value)
    
    # Remove potentially dangerous URL schemes
    value = re.sub(r'(javascript|data|vbscript):', '', value, flags=re.IGNORECASE)
    
    # Normalize whitespace and remove control characters
    value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
    value = ' '.join(value.split())
    
    # Escape special characters
    value = value.replace('&', '&amp;')
    return value

def validate_url(url: str) -> bool:
    """Validate if the URL is from a supported marketplace"""
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    
    # Sanitize URL
    url = sanitize_input(url)
    
    # Validate URL format and supported marketplaces
    valid_domains = r'^https?://([a-z0-9\.-]+\.)?(amazon|ebay)\.(it|com|co\.uk|de|fr|es|in|ca|com\.au|com\.br|nl|pl|se|sg)'
    if not re.match(valid_domains, url, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="URL not supported. Please provide a valid Amazon or eBay URL."
        )
    return True

# Token rotation configuration
TOKEN_ROTATION_INTERVAL = 24 * 3600  # 24 hours in seconds
TOKEN_BLACKLIST_TTL = 48 * 3600  # 48 hours in seconds

class TokenManager:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def rotate_token(self, token: str) -> str:
        """Generate a new token and invalidate the old one"""
        new_token = secrets.token_urlsafe(32)
        blacklist_key = f"token:blacklist:{token}"
        
        # Add old token to blacklist with TTL
        await self.redis.setex(blacklist_key, TOKEN_BLACKLIST_TTL, '1')
        
        # Log token rotation
        security_logger.info({
            'event': 'token_rotation',
            'old_token_hash': hashlib.sha256(token.encode()).hexdigest()
        })
        
        return new_token

    async def is_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted"""
        blacklist_key = f"token:blacklist:{token}"
        return bool(await self.redis.get(blacklist_key))

async def rate_limiter(request: Request):
    """Redis-based rate limiter with bypass protection and graceful degradation"""
    client_ip = request.client.host
    api_key = request.headers.get('X-API-Key')
    hour_key = f"rate_limit:hour:{client_ip}"
    burst_key = f"rate_limit:burst:{client_ip}"
    degradation_key = f"rate_limit:degraded:{client_ip}"
    ip_tracking_key = f"ip_tracking:{api_key}" if api_key else None
    
    # Track IPs per API key
    if api_key:
        # Add IP to the sorted set with timestamp
        await redis_client.zadd(ip_tracking_key, {client_ip: datetime.now().timestamp()})
        await redis_client.expire(ip_tracking_key, IP_TRACKING_WINDOW)
        
        # Remove old entries
        await redis_client.zremrangebyscore(
            ip_tracking_key,
            0,
            datetime.now().timestamp() - IP_TRACKING_WINDOW
        )
        
        # Check number of unique IPs
        unique_ips = await redis_client.zcard(ip_tracking_key)
        if unique_ips > MAX_IPS_PER_KEY:
            await log_security_event(
                'rate_limit_bypass_detected',
                {
                    'api_key_hash': hashlib.sha256(api_key.encode()).hexdigest(),
                    'ip_count': unique_ips
                },
                'WARNING'
            )
            raise HTTPException(
                status_code=403,
                detail="Too many IPs using the same API key"
            )
    
    # Use Redis pipeline for atomic operations
    pipe = redis_client.pipeline()
    now = datetime.now().timestamp()
    
    # Check if service is in degraded mode
    is_degraded = await redis_client.get(degradation_key)
    
    # Hourly limit check
    pipe.zremrangebyscore(hour_key, 0, now - TIME_WINDOW)
    pipe.zcard(hour_key)
    pipe.zadd(hour_key, {str(now): now})
    pipe.expire(hour_key, TIME_WINDOW)
    
    # Burst limit check
    pipe.zremrangebyscore(burst_key, 0, now - BURST_WINDOW)
    pipe.zcard(burst_key)
    pipe.zadd(burst_key, {str(now): now})
    pipe.expire(burst_key, BURST_WINDOW)
    
    # Execute pipeline
    results = pipe.execute()
    hour_count = results[1]
    burst_count = results[5]
    
    # Calculate limits and reset times
    hour_remaining = max(0, MAX_REQUESTS - hour_count)
    burst_remaining = max(0, BURST_LIMIT - burst_count)
    hour_reset = int(now + TIME_WINDOW)
    burst_reset = int(now + BURST_WINDOW)
    reset_time = hour_reset  # Define reset_time for use in error response
    
    # Check for degradation threshold
    if hour_count >= int(MAX_REQUESTS * DEGRADATION_THRESHOLD) and not is_degraded:
        await redis_client.setex(degradation_key, DEGRADATION_TTL, '1')
        security_logger.warning({
            'event': 'service_degradation',
            'ip': client_ip,
            'hour_count': hour_count
        })
    
    # Set enhanced rate limit headers
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(MAX_REQUESTS),
        "X-RateLimit-Remaining": str(hour_remaining),
        "X-RateLimit-Reset": str(hour_reset),
        "X-RateLimit-Burst-Limit": str(BURST_LIMIT),
        "X-RateLimit-Burst-Remaining": str(burst_remaining),
        "X-RateLimit-Burst-Reset": str(burst_reset),
        "X-RateLimit-Degraded": '1' if is_degraded else '0'
    }
    
    # Log request for security audit
    security_logger.info({
        'event': 'rate_limit_check',
        'ip': client_ip,
        'request_count': hour_count,
        'endpoint': str(request.url),
        'headers': dict(request.headers)
    })
    
    # Check both hourly and burst limits
    if hour_count >= MAX_REQUESTS or burst_count >= BURST_LIMIT:
        security_logger.warning({
            'event': 'rate_limit_exceeded',
            'ip': client_ip,
            'request_count': hour_count
        })
        headers = {
            "X-RateLimit-Limit": str(MAX_REQUESTS),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_time),
            "Retry-After": str(reset_time - int(now))
        }
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS} requests per hour.",
            headers=headers
        )

# API Key security and rotation
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_ROTATION_INTERVAL = 7 * 24 * 3600  # 7 days in seconds
API_KEY_EXPIRY_BUFFER = 24 * 3600  # 24 hours buffer before expiry

class APIKeyManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "api:key:"

    async def create_api_key(self) -> tuple[str, datetime]:
        """Create a new API key with expiration"""
        api_key = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(seconds=API_KEY_ROTATION_INTERVAL)
        key_data = {
            "key": api_key,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expiry.isoformat()
        }
        await self.redis.setex(
            f"{self.prefix}{api_key}",
            API_KEY_ROTATION_INTERVAL,
            json.dumps(key_data)
        )
        return api_key, expiry

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate API key and check expiration"""
        key_data = await self.redis.get(f"{self.prefix}{api_key}")
        if not key_data:
            return False
        
        data = json.loads(key_data)
        expires_at = datetime.fromisoformat(data['expires_at'])
        
        # Check if key is approaching expiration
        if datetime.utcnow() + timedelta(seconds=API_KEY_EXPIRY_BUFFER) >= expires_at:
            await log_security_event(
                'api_key_near_expiry',
                {'key_hash': hashlib.sha256(api_key.encode()).hexdigest()},
                'WARNING'
            )
        
        return datetime.utcnow() < expires_at

    async def rotate_api_key(self, old_key: str) -> tuple[str, datetime]:
        """Rotate API key while maintaining a grace period"""
        if not await self.validate_api_key(old_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        new_key, expiry = await self.create_api_key()
        
        # Keep old key valid for a grace period
        grace_period = 3600  # 1 hour
        await self.redis.expire(f"{self.prefix}{old_key}", grace_period)
        
        await log_security_event(
            'api_key_rotation',
            {
                'old_key_hash': hashlib.sha256(old_key.encode()).hexdigest(),
                'new_key_hash': hashlib.sha256(new_key.encode()).hexdigest()
            }
        )
        
        return new_key, expiry

# Initialize API key manager
api_key_manager = APIKeyManager(redis_client)

async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)):
    """Verify API key if present"""
    if not api_key:
        return None
    
    is_valid = await api_key_manager.validate_api_key(api_key)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    return api_key

# Security middleware dependencies
async def security_dependencies(request: Request, api_key: Optional[str] = Depends(verify_api_key)):
    """Combine all security checks"""
    await rate_limiter(request)
    return True

# Token rotation configuration
TOKEN_ROTATION_INTERVAL = 24 * 3600  # 24 hours in seconds
TOKEN_BLACKLIST_TTL = 48 * 3600  # 48 hours in seconds

class TokenManager:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def rotate_token(self, token: str) -> str:
        """Generate a new token and invalidate the old one"""
        new_token = secrets.token_urlsafe(32)
        blacklist_key = f"token:blacklist:{token}"
        
        # Add old token to blacklist with TTL
        await self.redis.setex(blacklist_key, TOKEN_BLACKLIST_TTL, '1')
        
        # Log token rotation
        security_logger.info({
            'event': 'token_rotation',
            'old_token_hash': hashlib.sha256(token.encode()).hexdigest()
        })
        
        return new_token

    async def is_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted"""
        blacklist_key = f"token:blacklist:{token}"
        return bool(await self.redis.get(blacklist_key))

async def rate_limiter(request: Request):
    """Redis-based rate limiter with bypass protection and graceful degradation"""
    client_ip = request.client.host
    api_key = request.headers.get('X-API-Key')
    hour_key = f"rate_limit:hour:{client_ip}"
    burst_key = f"rate_limit:burst:{client_ip}"
    degradation_key = f"rate_limit:degraded:{client_ip}"
    ip_tracking_key = f"ip_tracking:{api_key}" if api_key else None
    
    # Track IPs per API key
    if api_key:
        # Add IP to the sorted set with timestamp
        await redis_client.zadd(ip_tracking_key, {client_ip: datetime.now().timestamp()})
        await redis_client.expire(ip_tracking_key, IP_TRACKING_WINDOW)
        
        # Remove old entries
        await redis_client.zremrangebyscore(
            ip_tracking_key,
            0,
            datetime.now().timestamp() - IP_TRACKING_WINDOW
        )
        
        # Check number of unique IPs
        unique_ips = await redis_client.zcard(ip_tracking_key)
        if unique_ips > MAX_IPS_PER_KEY:
            await log_security_event(
                'rate_limit_bypass_detected',
                {
                    'api_key_hash': hashlib.sha256(api_key.encode()).hexdigest(),
                    'ip_count': unique_ips
                },
                'WARNING'
            )
            raise HTTPException(
                status_code=403,
                detail="Too many IPs using the same API key"
            )
    
    # Use Redis pipeline for atomic operations
    pipe = redis_client.pipeline()
    now = datetime.now().timestamp()
    
    # Check if service is in degraded mode
    is_degraded = await redis_client.get(degradation_key)
    
    # Hourly limit check
    pipe.zremrangebyscore(hour_key, 0, now - TIME_WINDOW)
    pipe.zcard(hour_key)
    pipe.zadd(hour_key, {str(now): now})
    pipe.expire(hour_key, TIME_WINDOW)
    
    # Burst limit check
    pipe.zremrangebyscore(burst_key, 0, now - BURST_WINDOW)
    pipe.zcard(burst_key)
    pipe.zadd(burst_key, {str(now): now})
    pipe.expire(burst_key, BURST_WINDOW)
    
    # Execute pipeline
    results = pipe.execute()
    hour_count = results[1]
    burst_count = results[5]
    
    # Calculate limits and reset times
    hour_remaining = max(0, MAX_REQUESTS - hour_count)
    burst_remaining = max(0, BURST_LIMIT - burst_count)
    hour_reset = int(now + TIME_WINDOW)
    burst_reset = int(now + BURST_WINDOW)
    reset_time = hour_reset  # Define reset_time for use in error response
    
    # Check for degradation threshold
    if hour_count >= int(MAX_REQUESTS * DEGRADATION_THRESHOLD) and not is_degraded:
        await redis_client.setex(degradation_key, DEGRADATION_TTL, '1')
        security_logger.warning({
            'event': 'service_degradation',
            'ip': client_ip,
            'hour_count': hour_count
        })
    
    # Set enhanced rate limit headers
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(MAX_REQUESTS),
        "X-RateLimit-Remaining": str(hour_remaining),
        "X-RateLimit-Reset": str(hour_reset),
        "X-RateLimit-Burst-Limit": str(BURST_LIMIT),
        "X-RateLimit-Burst-Remaining": str(burst_remaining),
        "X-RateLimit-Burst-Reset": str(burst_reset),
        "X-RateLimit-Degraded": '1' if is_degraded else '0'
    }
    
    # Log request for security audit
    security_logger.info({
        'event': 'rate_limit_check',
        'ip': client_ip,
        'request_count': hour_count,  # Fixed: using hour_count instead of undefined request_count
        'endpoint': str(request.url),
        'headers': dict(request.headers)
    })
    
    # Check both hourly and burst limits
    if hour_count >= MAX_REQUESTS or burst_count >= BURST_LIMIT:
        security_logger.warning({
            'event': 'rate_limit_exceeded',
            'ip': client_ip,
            'request_count': hour_count  # Fixed: using hour_count
        })
        headers = {
            "X-RateLimit-Limit": str(MAX_REQUESTS),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_time),
            "Retry-After": str(reset_time - int(now))
        }
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS} requests per hour.",
            headers=headers
        )

# API Key security and rotation
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_ROTATION_INTERVAL = 7 * 24 * 3600  # 7 days in seconds
API_KEY_EXPIRY_BUFFER = 24 * 3600  # 24 hours buffer before expiry

class APIKeyManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "api:key:"

    async def create_api_key(self) -> tuple[str, datetime]:
        """Create a new API key with expiration"""
        api_key = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(seconds=API_KEY_ROTATION_INTERVAL)
        key_data = {
            "key": api_key,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expiry.isoformat()
        }
        await self.redis.setex(
            f"{self.prefix}{api_key}",
            API_KEY_ROTATION_INTERVAL,
            json.dumps(key_data)
        )
        return api_key, expiry

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate API key and check expiration"""
        key_data = await self.redis.get(f"{self.prefix}{api_key}")
        if not key_data:
            return False
        
        data = json.loads(key_data)
        expires_at = datetime.fromisoformat(data['expires_at'])
        
        # Check if key is approaching expiration
        if datetime.utcnow() + timedelta(seconds=API_KEY_EXPIRY_BUFFER) >= expires_at:
            await log_security_event(
                'api_key_near_expiry',
                {'key_hash': hashlib.sha256(api_key.encode()).hexdigest()},
                'WARNING'
            )
        
        return datetime.utcnow() < expires_at

    async def rotate_api_key(self, old_key: str) -> tuple[str, datetime]:
        """Rotate API key while maintaining a grace period"""
        if not await self.validate_api_key(old_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        new_key, expiry = await self.create_api_key()
        
        # Keep old key valid for a grace period
        grace_period = 3600  # 1 hour
        await self.redis.expire(f"{self.prefix}{old_key}", grace_period)
        
        await log_security_event(
            'api_key_rotation',
            {
                'old_key_hash': hashlib.sha256(old_key.encode()).hexdigest(),
                'new_key_hash': hashlib.sha256(new_key.encode()).hexdigest()
            }
        )
        
        return new_key, expiry

# Initialize API key manager
api_key_manager = APIKeyManager(redis_client)

async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)):
    """Verify API key if present"""
    if not api_key:
        return None
    
    is_valid = await api_key_manager.validate_api_key(api_key)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    return api_key

# Security middleware dependencies
async def security_dependencies(request: Request, api_key: Optional[str] = Depends(verify_api_key)):
    """Combine all security checks"""
    await rate_limiter(request)
    return True

# CORS Configuration
CORS_ORIGINS = [
    "https://worthit.app",
    "https://api.worthit.app",
    "https://dashboard.worthit.app"
]

CORS_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Request-ID",
    "X-API-Key"
]

CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]

async def setup_cors(app):
    """Configure CORS middleware with strict security settings"""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=CORS_METHODS,
        allow_headers=CORS_HEADERS,
        allow_credentials=True,
        max_age=3600
    )
    await log_security_event('cors_configured', {
        'origins': CORS_ORIGINS,
        'methods': CORS_METHODS
    })

async def validate_origin(request: Request) -> bool:
    """Validate request origin against allowed origins"""
    origin = request.headers.get('origin')
    if not origin:
        await log_security_event('origin_validation_failed', {
            'reason': 'missing_origin',
            'ip': request.client.host
        })
        return False

    if origin not in CORS_ORIGINS:
        await log_security_event('origin_validation_failed', {
            'reason': 'invalid_origin',
            'origin': origin,
            'ip': request.client.host
        })
        return False

    await log_security_event('origin_validated', {
        'origin': origin,
        'ip': request.client.host
    })
    return True

def sanitize_input(value: str) -> str:
    """Enhanced input sanitization to prevent injection attacks"""
    if not isinstance(value, str):
        return str(value)

    # Remove any potential script tags and event handlers
    value = re.sub(r'<script[^>]*>.*?</script>', '', value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r'on\w+=".*?"', '', value, flags=re.IGNORECASE)
    
    # Remove other potentially dangerous HTML tags and attributes
    value = re.sub(r'<[^>]+>', '', value)
    
    # Remove potentially dangerous URL schemes
    value = re.sub(r'(javascript|data|vbscript):', '', value, flags=re.IGNORECASE)
    
    # Normalize whitespace and remove control characters
    value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', value)
    value = ' '.join(value.split())
    
    # Escape special characters
    value = value.replace('&', '&amp;')
    return value

def validate_url(url: str) -> bool:
    """Validate if the URL is from a supported marketplace"""
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty")
    
    # Sanitize URL
    url = sanitize_input(url)
    
    # Validate URL format and supported marketplaces
    valid_domains = r'^https?://([a-z0-9\.-]+\.)?(amazon|ebay)\.(it|com|co\.uk|de|fr|es|in|ca|com\.au|com\.br|nl|pl|se|sg)'
    if not re.match(valid_domains, url, re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail="URL not supported. Please provide a valid Amazon or eBay URL."
        )
    return True

# Token rotation configuration
TOKEN_ROTATION_INTERVAL = 24 * 3600  # 24 hours in seconds
TOKEN_BLACKLIST_TTL = 48 * 3600  # 48 hours in seconds

class TokenManager:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def rotate_token(self, token: str) -> str:
        """Generate a new token and invalidate the old one"""
        new_token = secrets.token_urlsafe(32)
        blacklist_key = f"token:blacklist:{token}"
        
        # Add old token to blacklist with TTL
        await self.redis.setex(blacklist_key, TOKEN_BLACKLIST_TTL, '1')
        
        # Log token rotation
        security_logger.info({
            'event': 'token_rotation',
            'old_token_hash': hashlib.sha256(token.encode()).hexdigest()
        })
        
        return new_token

    async def is_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted"""
        blacklist_key = f"token:blacklist:{token}"
        return bool(await self.redis.get(blacklist_key))

async def rate_limiter(request: Request):
    """Redis-based rate limiter with bypass protection and graceful degradation"""
    client_ip = request.client.host
    api_key = request.headers.get('X-API-Key')
    hour_key = f"rate_limit:hour:{client_ip}"
    burst_key = f"rate_limit:burst:{client_ip}"
    degradation_key = f"rate_limit:degraded:{client_ip}"
    ip_tracking_key = f"ip_tracking:{api_key}" if api_key else None
    
    # Track IPs per API key
    if api_key:
        # Add IP to the sorted set with timestamp
        await redis_client.zadd(ip_tracking_key, {client_ip: datetime.now().timestamp()})
        await redis_client.expire(ip_tracking_key, IP_TRACKING_WINDOW)
        
        # Remove old entries
        await redis_client.zremrangebyscore(
            ip_tracking_key,
            0,
            datetime.now().timestamp() - IP_TRACKING_WINDOW
        )
        
        # Check number of unique IPs
        unique_ips = await redis_client.zcard(ip_tracking_key)
        if unique_ips > MAX_IPS_PER_KEY:
            await log_security_event(
                'rate_limit_bypass_detected',
                {
                    'api_key_hash': hashlib.sha256(api_key.encode()).hexdigest(),
                    'ip_count': unique_ips
                },
                'WARNING'
            )
            raise HTTPException(
                status_code=403,
                detail="Too many IPs using the same API key"
            )
    
    # Use Redis pipeline for atomic operations
    pipe = redis_client.pipeline()
    now = datetime.now().timestamp()
    
    # Check if service is in degraded mode
    is_degraded = await redis_client.get(degradation_key)
    
    # Hourly limit check
    pipe.zremrangebyscore(hour_key, 0, now - TIME_WINDOW)
    pipe.zcard(hour_key)
    pipe.zadd(hour_key, {str(now): now})
    pipe.expire(hour_key, TIME_WINDOW)
    
    # Burst limit check
    pipe.zremrangebyscore(burst_key, 0, now - BURST_WINDOW)
    pipe.zcard(burst_key)
    pipe.zadd(burst_key, {str(now): now})
    pipe.expire(burst_key, BURST_WINDOW)
    
    # Execute pipeline
    results = pipe.execute()
    hour_count = results[1]
    burst_count = results[5]
    
    # Calculate limits and reset times
    hour_remaining = max(0, MAX_REQUESTS - hour_count)
    burst_remaining = max(0, BURST_LIMIT - burst_count)
    hour_reset = int(now + TIME_WINDOW)
    burst_reset = int(now + BURST_WINDOW)
    reset_time = hour_reset  # Define reset_time for use in error response
    
    # Check for degradation threshold
    if hour_count >= int(MAX_REQUESTS * DEGRADATION_THRESHOLD) and not is_degraded:
        await redis_client.setex(degradation_key, DEGRADATION_TTL, '1')
        security_logger.warning({
            'event': 'service_degradation',
            'ip': client_ip,
            'hour_count': hour_count
        })
    
    # Set enhanced rate limit headers
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(MAX_REQUESTS),
        "X-RateLimit-Remaining": str(hour_remaining),
        "X-RateLimit-Reset": str(hour_reset),
        "X-RateLimit-Burst-Limit": str(BURST_LIMIT),
        "X-RateLimit-Burst-Remaining": str(burst_remaining),
        "X-RateLimit-Burst-Reset": str(burst_reset),
        "X-RateLimit-Degraded": '1' if is_degraded else '0'
    }
    
    # Log request for security audit
    security_logger.info({
        'event': 'rate_limit_check',
        'ip': client_ip,
        'request_count': hour_count,  # Fixed: using hour_count instead of undefined request_count
        'endpoint': str(request.url),
        'headers': dict(request.headers)
    })
    
    # Check both hourly and burst limits
    if hour_count >= MAX_REQUESTS or burst_count >= BURST_LIMIT:
        security_logger.warning({
            'event': 'rate_limit_exceeded',
            'ip': client_ip,
            'request_count': hour_count  # Fixed: using hour_count
        })
        headers = {
            "X-RateLimit-Limit": str(MAX_REQUESTS),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_time),
            "Retry-After": str(reset_time - int(now))
        }
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS} requests per hour.",
            headers=headers
        )

# API Key security and rotation
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_ROTATION_INTERVAL = 7 * 24 * 3600  # 7 days in seconds
API_KEY_EXPIRY_BUFFER = 24 * 3600  # 24 hours buffer before expiry

class APIKeyManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "api:key:"

    async def create_api_key(self) -> tuple[str, datetime]:
        """Create a new API key with expiration"""
        api_key = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(seconds=API_KEY_ROTATION_INTERVAL)
        key_data = {
            "key": api_key,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expiry.isoformat()
        }
        await self.redis.setex(
            f"{self.prefix}{api_key}",
            API_KEY_ROTATION_INTERVAL,
            json.dumps(key_data)
        )
        return api_key, expiry

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate API key and check expiration"""
        key_data = await self.redis.get(f"{self.prefix}{api_key}")
        if not key_data:
            return False
        
        data = json.loads(key_data)
        expires_at = datetime.fromisoformat(data['expires_at'])
        
        # Check if key is approaching expiration
        if datetime.utcnow() + timedelta(seconds=API_KEY_EXPIRY_BUFFER) >= expires_at:
            await log_security_event(
                'api_key_near_expiry',
                {'key_hash': hashlib.sha256(api_key.encode()).hexdigest()},
                'WARNING'
            )
        
        return datetime.utcnow() < expires_at

    async def rotate_api_key(self, old_key: str) -> tuple[str, datetime]:
        """Rotate API key while maintaining a grace period"""
        if not await self.validate_api_key(old_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        new_key, expiry = await self.create_api_key()
        
        # Keep old key valid for a grace period
        grace_period = 3600  # 1 hour
        await self.redis.expire(f"{self.prefix}{old_key}", grace_period)
        
        await log_security_event(
            'api_key_rotation',
            {
                'old_key_hash': hashlib.sha256(old_key.encode()).hexdigest(),
                'new_key_hash': hashlib.sha256(new_key.encode()).hexdigest()
            }
        )
        
        return new_key, expiry

# Initialize API key manager
api_key_manager = APIKeyManager(redis_client)

async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)):
    """Verify API key if present"""
    if not api_key:
        return None
    
    is_valid = await api_key_manager.validate_api_key(api_key)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    return api_key

# Security middleware dependencies
async def security_dependencies(request: Request, api_key: Optional[str] = Depends(verify_api_key)):
    """Combine all security checks"""
    await rate_limiter(request)
    return True

# Token rotation configuration
TOKEN_ROTATION_INTERVAL = 24 * 3600  # 24 hours in seconds
TOKEN_BLACKLIST_TTL = 48 * 3600  # 48 hours in seconds

class TokenManager:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def rotate_token(self, token: str) -> str:
        """Generate a new token and invalidate the old one"""
        new_token = secrets.token_urlsafe(32)
        blacklist_key = f"token:blacklist:{token}"
        
        # Add old token to blacklist with TTL
        await self.redis.setex(blacklist_key, TOKEN_BLACKLIST_TTL, '1')
        
        # Log token rotation
        security_logger.info({
            'event': 'token_rotation',
            'old_token_hash': hashlib.sha256(token.encode()).hexdigest()
        })
        
        return new_token

    async def is_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted"""
        blacklist_key = f"token:blacklist:{token}"
        return bool(await self.redis.get(blacklist_key))

async def rate_limiter(request: Request):
    """Redis-based rate limiter with bypass protection and graceful degradation"""
    client_ip = request.client.host
    api_key = request.headers.get('X-API-Key')
    hour_key = f"rate_limit:hour:{client_ip}"
    burst_key = f"rate_limit:burst:{client_ip}"
    degradation_key = f"rate_limit:degraded:{client_ip}"
    ip_tracking_key = f"ip_tracking:{api_key}" if api_key else None
    
    # Track IPs per API key
    if api_key:
        # Add IP to the sorted set with timestamp
        await redis_client.zadd(ip_tracking_key, {client_ip: datetime.now().timestamp()})
        await redis_client.expire(ip_tracking_key, IP_TRACKING_WINDOW)
        
        # Remove old entries
        await redis_client.zremrangebyscore(
            ip_tracking_key,
            0,
            datetime.now().timestamp() - IP_TRACKING_WINDOW
        )
        
        # Check number of unique IPs
        unique_ips = await redis_client.zcard(ip_tracking_key)
        if unique_ips > MAX_IPS_PER_KEY:
            await log_security_event(
                'rate_limit_bypass_detected',
                {
                    'api_key_hash': hashlib.sha256(api_key.encode()).hexdigest(),
                    'ip_count': unique_ips
                },
                'WARNING'
            )
            raise HTTPException(
                status_code=403,
                detail="Too many IPs using the same API key"
            )
    
    # Use Redis pipeline for atomic operations
    pipe = redis_client.pipeline()
    now = datetime.now().timestamp()
    
    # Check if service is in degraded mode
    is_degraded = await redis_client.get(degradation_key)
    
    # Hourly limit check
    pipe.zremrangebyscore(hour_key, 0, now - TIME_WINDOW)
    pipe.zcard(hour_key)
    pipe.zadd(hour_key, {str(now): now})
    pipe.expire(hour_key, TIME_WINDOW)
    
    # Burst limit check
    pipe.zremrangebyscore(burst_key, 0, now - BURST_WINDOW)
    pipe.zcard(burst_key)
    pipe.zadd(burst_key, {str(now): now})
    pipe.expire(burst_key, BURST_WINDOW)
    
    # Execute pipeline
    results = pipe.execute()
    hour_count = results[1]
    burst_count = results[5]
    
    # Calculate limits and reset times
    hour_remaining = max(0, MAX_REQUESTS - hour_count)
    burst_remaining = max(0, BURST_LIMIT - burst_count)
    hour_reset = int(now + TIME_WINDOW)
    burst_reset = int(now + BURST_WINDOW)
    reset_time = hour_reset  # Define reset_time for use in error response
    
    # Check for degradation threshold
    if hour_count >= int(MAX_REQUESTS * DEGRADATION_THRESHOLD) and not is_degraded:
        await redis_client.setex(degradation_key, DEGRADATION_TTL, '1')
        security_logger.warning({
            'event': 'service_degradation',
            'ip': client_ip,
            'hour_count': hour_count
        })
    
    # Set enhanced rate limit headers
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(MAX_REQUESTS),
        "X-RateLimit-Remaining": str(hour_remaining),
        "X-RateLimit-Reset": str(hour_reset),
        "X-RateLimit-Burst-Limit": str(BURST_LIMIT),
        "X-RateLimit-Burst-Remaining": str(burst_remaining),
        "X-RateLimit-Burst-Reset": str(burst_reset),
        "X-RateLimit-Degraded": '1' if is_degraded else '0'
    }
    
    # Log request for security audit
    security_logger.info({
        'event': 'rate_limit_check',
        'ip': client_ip,
        'request_count': hour_count,  # Fixed: using hour_count instead of undefined request_count
        'endpoint': str(request.url),
        'headers': dict(request.headers)
    })
    
    # Check both hourly and burst limits
    if hour_count >= MAX_REQUESTS or burst_count >= BURST_LIMIT:
        security_logger.warning({
            'event': 'rate_limit_exceeded',
            'ip': client_ip,
            'request_count': hour_count  # Fixed: using hour_count
        })
        headers = {
            "X-RateLimit-Limit": str(MAX_REQUESTS),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_time),
            "Retry-After": str(reset_time - int(now))
        }
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {MAX_REQUESTS} requests per hour.",
            headers=headers
        )

# API Key security and rotation
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_ROTATION_INTERVAL = 7 * 24 * 3600  # 7 days in seconds
API_KEY_EXPIRY_BUFFER = 24 * 3600  # 24 hours buffer before expiry

class APIKeyManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.prefix = "api:key:"

    async def create_api_key(self) -> tuple[str, datetime]:
        """Create a new API key with expiration"""
        api_key = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(seconds=API_KEY_ROTATION_INTERVAL)
        key_data = {
            "key": api_key,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expiry.isoformat()
        }
        await self.redis.setex(
            f"{self.prefix}{api_key}",
            API_KEY_ROTATION_INTERVAL,
            json.dumps(key_data)
        )
        return api_key, expiry

    async def validate_api_key(self, api_key: str) -> bool:
        """Validate API key and check expiration"""
        key_data = await self.redis.get(f"{self.prefix}{api_key}")
        if not key_data:
            return False
        
        data = json.loads(key_data)
        expires_at = datetime.fromisoformat(data['expires_at'])
        
        # Check if key is approaching expiration
        if datetime.utcnow() + timedelta(seconds=API_KEY_EXPIRY_BUFFER) >= expires_at:
            await log_security_event(
                'api_key_near_expiry',
                {'key_hash': hashlib.sha256(api_key.encode()).hexdigest()},
                'WARNING'
            )
        
        return datetime.utcnow() < expires_at

    async def rotate_api_key(self, old_key: str) -> tuple[str, datetime]:
        """Rotate API key while maintaining a grace period"""
        if not await self.validate_api_key(old_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        new_key, expiry = await self.create_api_key()
        
        # Keep old key valid for a grace period
        grace_period = 3600  # 1 hour
        await self.redis.expire(f"{self.prefix}{old_key}", grace_period)
        
        await log_security_event(
            'api_key_rotation',
            {
                'old_key_hash': hashlib.sha256(old_key.encode()).hexdigest(),
                'new_key_hash': hashlib.sha256(new_key.encode()).hexdigest()
            }
        )
        
        return new_key, expiry

# Initialize API key manager
api_key_manager = APIKeyManager(redis_client)

async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)):
    """Verify API key if present"""
    if not api_key:
        return None
    
    is_valid = await api_key_manager.validate_api_key(api_key)
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    
    return api_key

# Security middleware dependencies
async def security_dependencies(request: Request, api_key: Optional[str] = Depends(verify_api_key)):
    """Combine all security checks"""
    await rate_limiter(request)
    return True