from fastapi import HTTPException, Request, Depends
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import re
import redis
import json
import logging
import secrets
import hashlib
import time
from typing import Optional, List
from datetime import datetime, timedelta
from collections import defaultdict

# Redis client for rate limiting
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Export security dependencies
security_dependencies: List[Depends] = []

class SecurityMiddleware:
    def __init__(self):
        self.ddos_protection = DDoSProtection()
        self.auth_manager = AuthenticationManager()
        self.request_validator = RequestValidator()
    
    async def process_request(self, request: Request):
        # DDoS protection check
        if await self.ddos_protection.is_attack(request):
            security_logger.warning(f"Potential DDoS attack detected from IP: {request.client.host}")
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests", "retry_after": 300}
            )
        
        # Enhanced API authentication
        auth_result = await self.auth_manager.validate_request(request)
        if not auth_result['valid']:
            security_logger.warning(
                f"Authentication failed for IP: {request.client.host}, "
                f"Reason: {auth_result['reason']}"
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication failed", "detail": auth_result['reason']}
            )
        
        # Advanced request validation
        validation_result = await self.request_validator.validate(request)
        if not validation_result['valid']:
            security_logger.warning(
                f"Request validation failed for IP: {request.client.host}, "
                f"Reason: {validation_result['reason']}"
            )
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid request", "detail": validation_result['reason']}
            )
        
        return None

class DDoSProtection:
    def __init__(self):
        self.request_threshold = 1000  # Base requests per minute threshold
        self.ip_history = defaultdict(list)
        self.blocked_ips = set()
        self.block_duration = timedelta(hours=1)
        self.traffic_patterns = defaultdict(lambda: {'count': 0, 'burst': 0, 'avg_interval': 0})
        self.adaptive_thresholds = {'normal': 1000, 'suspicious': 800, 'high_risk': 500}
        self.pattern_window = 300  # 5 minutes window for pattern analysis
    
    async def is_attack(self, request: Request) -> bool:
        ip = request.client.host
        current_time = time.time()
        
        # Clean up old records
        self._cleanup(current_time)
        
        if ip in self.blocked_ips:
            return True
        
        # Record and analyze request
        self.ip_history[ip].append(current_time)
        self._update_traffic_pattern(ip, current_time)
        
        # Enhanced attack detection
        if await self._analyze_traffic_pattern(ip, request):
            self.blocked_ips.add(ip)
            return True
        
        return False
    
    async def _analyze_traffic_pattern(self, ip: str, request: Request) -> bool:
        pattern = self.traffic_patterns[ip]
        current_time = time.time()
        recent_requests = [t for t in self.ip_history[ip] if current_time - t <= 60]
        
        # Analyze request patterns
        risk_level = self._calculate_risk_level(ip, request)
        threshold = self.adaptive_thresholds[risk_level]
        
        # Check against adaptive threshold
        if len(recent_requests) > threshold:
            return True
        
        # Advanced pattern analysis
        if pattern['burst'] > 50 and pattern['avg_interval'] < 0.1:
            return True
        
        # Payload analysis
        if await self._analyze_payload(request):
            return True
        
        return False
        
    def _calculate_risk_level(self, ip: str, request: Request) -> str:
        pattern = self.traffic_patterns[ip]
        
        if pattern['burst'] > 30 or pattern['avg_interval'] < 0.2:
            return 'high_risk'
        elif pattern['burst'] > 15 or pattern['avg_interval'] < 0.5:
            return 'suspicious'
        return 'normal'
        
    async def _analyze_payload(self, request: Request) -> bool:
        # Analyze request payload for suspicious patterns
        try:
            body = await request.json() if request.method in ['POST', 'PUT', 'PATCH'] else {}
            headers = dict(request.headers)
            
            # Check for suspicious patterns in payload
            suspicious_patterns = [
                len(str(body)) > 1000000,  # Large payload
                any(len(str(v)) > 10000 for v in body.values()),  # Large field values
                any(k.lower() in ['script', 'eval', 'function'] for k in str(body).lower().split()),  # Potential XSS
                headers.get('content-length', '0').isdigit() and int(headers['content-length']) > 1000000  # Large content length
            ]
            
            return sum(suspicious_patterns) >= 2
        except:
            return False
            
    def _update_traffic_pattern(self, ip: str, current_time: float):
        pattern = self.traffic_patterns[ip]
        recent_requests = [t for t in self.ip_history[ip] if current_time - t <= self.pattern_window]
        
        if len(recent_requests) >= 2:
            intervals = [recent_requests[i] - recent_requests[i-1] for i in range(1, len(recent_requests))]
            pattern['avg_interval'] = sum(intervals) / len(intervals)
            pattern['burst'] = max(1, len([i for i in intervals if i < 0.1]))
        
        pattern['count'] = len(recent_requests)
        
        # Analyze last 10 requests for suspicious patterns
        if len(recent_requests) >= 10:
            last_10 = sorted(recent_requests[-10:])
            intervals = [last_10[i+1] - last_10[i] for i in range(len(last_10)-1)]
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval < 0.1:  # Suspicious if average interval is less than 100ms
                return True
        
        # Pattern analysis for potential DDoS
        if len(recent_requests) > 50:
            # Check for uniform intervals (bot-like behavior)
            intervals = [recent_requests[i+1] - recent_requests[i] for i in range(len(recent_requests)-1)]
            avg_interval = sum(intervals) / len(intervals)
            variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
            if variance < 0.01:  # Very uniform timing suggests automated attacks
                return True
        
        return False

# CORS Configuration
ALLOWED_ORIGINS = [
    "https://worthit.app",
    "https://api.worthit.app",
    "https://worthit-py.netlify.app",  # Primary Netlify deployment
    "https://worthit-staging.netlify.app",  # Netlify staging
    "http://localhost:3000"  # Development environment
]
ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-API-Key"]

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

class AuthenticationManager:
    def __init__(self):
        self.secret_key = os.getenv('JWT_SECRET_KEY', secrets.token_urlsafe(32))
        self.algorithm = 'HS256'
        self.access_token_expire = timedelta(minutes=30)
        self.refresh_token_expire = timedelta(days=7)
        self.roles = {'admin', 'user', 'free_tier'}
        self.role_permissions = {
            'admin': {'read', 'write', 'delete', 'manage_users'},
            'user': {'read', 'write'},
            'free_tier': {'read'}
        }
        self.token_blacklist = set()
    
    def create_token(self, user_id: str, role: str) -> dict:
        if role not in self.roles:
            raise ValueError(f"Invalid role: {role}")
        
        access_expires = datetime.utcnow() + self.access_token_expire
        refresh_expires = datetime.utcnow() + self.refresh_token_expire
        
        access_payload = {
            'user_id': user_id,
            'role': role,
            'permissions': list(self.role_permissions[role]),
            'exp': access_expires,
            'type': 'access',
            'jti': str(uuid.uuid4())
        }
        
        refresh_payload = {
            'user_id': user_id,
            'exp': refresh_expires,
            'type': 'refresh',
            'jti': str(uuid.uuid4())
        }
        
        return {
            'access_token': jwt.encode(access_payload, self.secret_key, algorithm=self.algorithm),
            'refresh_token': jwt.encode(refresh_payload, self.secret_key, algorithm=self.algorithm),
            'token_type': 'bearer',
            'expires_in': int(self.access_token_expire.total_seconds())
        }
    
    async def validate_request(self, request: Request) -> dict:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return {'valid': False, 'reason': 'Invalid authorization header'}
        
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Check token type and blacklist
            if payload.get('type') != 'access':
                return {'valid': False, 'reason': 'Invalid token type'}
            if payload.get('jti') in self.token_blacklist:
                return {'valid': False, 'reason': 'Token has been revoked'}
            
            # Validate permissions for the requested endpoint
            endpoint_permissions = self._get_endpoint_permissions(request.url.path, request.method)
            user_permissions = set(payload.get('permissions', []))
            
            if not endpoint_permissions.issubset(user_permissions):
                return {'valid': False, 'reason': 'Insufficient permissions'}
            
            # Store user info in request state for RBAC
            request.state.user = {
                'user_id': payload['user_id'],
                'role': payload['role'],
                'permissions': payload.get('permissions', [])
            }
            
            return {'valid': True}
        except jwt.ExpiredSignatureError:
            return {'valid': False, 'reason': 'Token has expired'}
        except jwt.InvalidTokenError:
            return {'valid': False, 'reason': 'Invalid token'}
    
    def _get_endpoint_permissions(self, path: str, method: str) -> set:
        # Define endpoint-specific permissions
        endpoint_permissions = {
            '/api/users': {
                'GET': {'read'},
                'POST': {'manage_users'},
                'PUT': {'manage_users'},
                'DELETE': {'manage_users'}
            },
            '/api/data': {
                'GET': {'read'},
                'POST': {'write'},
                'PUT': {'write'},
                'DELETE': {'delete'}
            }
        }
        
        # Get base path (first two segments)
        base_path = '/'.join(path.split('/')[:3])
        
        # Return required permissions for the endpoint
        return endpoint_permissions.get(base_path, {}).get(method, set())

def validate_url(url: str) -> bool:
    """
    Validates if a URL is from a supported marketplace and is properly formatted.
    
    Args:
        url: The URL to validate
        
    Returns:
        bool: True if the URL is valid, False otherwise
    """
    if not url:
        return False
        
    # Sanitize URL
    url = url.strip().lower()
    if not url.startswith('http'):
        url = 'https://' + url
    
    # Check if URL is from a supported marketplace
    valid_domains = r'^https?://([a-z0-9\.-]+\.)?(amazon|ebay)\.(it|com|co\.uk|de|fr|es|in|ca|com\.au|com\.br|nl|pl|se|sg)'
    return bool(re.match(valid_domains, url, re.IGNORECASE))