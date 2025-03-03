#!/usr/bin/env python
"""
Redis Connectivity Diagnostics for WorthIt!

This script provides detailed diagnostics for Redis connectivity issues,
including DNS resolution, port connectivity, and authentication testing.
"""

import os
import sys
import socket
import time
import redis
import subprocess
import platform
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_paths = [
    Path(__file__).parent.parent / ".env",
    Path(__file__).parent.parent / ".env.test"
]

env_loaded = False
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
        env_loaded = True
        break

if not env_loaded:
    print("Warning: No .env or .env.test file found!")

# Get Redis URL
redis_url = os.getenv("REDIS_URL")
if not redis_url:
    print("Error: REDIS_URL environment variable not found!")
    sys.exit(1)

# Parse Redis URL
print(f"\n=== Redis URL Analysis ===")
print(f"Original URL: {redis_url}")

try:
    # Handle redis:// URL format
    if redis_url.startswith("redis://"):
        parsed = urllib.parse.urlparse(redis_url)
        password = None
        if '@' in parsed.netloc:
            auth_part, host_part = parsed.netloc.split('@')
            if ':' in auth_part:
                user, password = auth_part.split(':', 1)
            else:
                user = auth_part
            host = host_part
        else:
            host = parsed.netloc
        
        if ':' in host:
            hostname, port = host.split(':')
        else:
            hostname = host
            port = "6379"  # Default Redis port
    else:
        print("Error: Unsupported Redis URL format")
        sys.exit(1)
        
    print(f"Hostname: {hostname}")
    print(f"Port: {port}")
    print(f"Password: {'*' * 8 if password else 'None'}")
    
    # DNS Resolution Test
    print("\n=== DNS Resolution Test ===")
    try:
        print(f"Resolving hostname {hostname}...")
        ip_address = socket.gethostbyname(hostname)
        print(f"✅ DNS Resolution successful: {hostname} -> {ip_address}")
    except socket.gaierror as e:
        print(f"❌ DNS Resolution failed: {e}")
        print("\nPossible solutions:")
        print("1. Check if the hostname is correct")
        print("2. Verify your DNS settings")
        print("3. Try using nslookup or dig to troubleshoot DNS issues")
        print("4. Check if your network blocks external DNS resolution")
        
        # Try to use system tools for DNS lookup
        if platform.system() == "Windows":
            try:
                print("\nAttempting DNS lookup with nslookup...")
                result = subprocess.run(["nslookup", hostname], capture_output=True, text=True)
                print(result.stdout)
            except Exception as e:
                print(f"Failed to run nslookup: {e}")
        else:
            try:
                print("\nAttempting DNS lookup with dig...")
                result = subprocess.run(["dig", hostname], capture_output=True, text=True)
                print(result.stdout)
            except Exception:
                try:
                    print("dig not found, trying nslookup...")
                    result = subprocess.run(["nslookup", hostname], capture_output=True, text=True)
                    print(result.stdout)
                except Exception as e:
                    print(f"Failed to run DNS tools: {e}")
    
    # Socket Connection Test
    print("\n=== Socket Connection Test ===")
    try:
        print(f"Testing TCP connection to {hostname}:{port}...")
        start_time = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)  # 5 second timeout
        s.connect((hostname, int(port)))
        s.close()
        end_time = time.time()
        print(f"✅ Socket connection successful (latency: {(end_time - start_time)*1000:.2f}ms)")
    except socket.timeout:
        print("❌ Socket connection timed out")
        print("\nPossible solutions:")
        print("1. Check if the Redis server is running")
        print("2. Verify firewall settings")
        print("3. Check if your network blocks outbound connections to this port")
    except socket.error as e:
        print(f"❌ Socket connection failed: {e}")
        print("\nPossible solutions:")
        print("1. Check if the port number is correct")
        print("2. Verify firewall settings")
        print("3. Check if the Redis server is running")
        print("4. Check if your network blocks outbound connections to this port")
        
        # Try to use system tools for port connectivity
        if platform.system() == "Windows":
            try:
                print("\nAttempting port connectivity check with PowerShell...")
                ps_cmd = f"Test-NetConnection -ComputerName {hostname} -Port {port}"
                result = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
                print(result.stdout)
            except Exception as e:
                print(f"Failed to run PowerShell test: {e}")
        else:
            try:
                print("\nAttempting port connectivity check with telnet...")
                result = subprocess.run(["telnet", hostname, port], capture_output=True, text=True)
                print(result.stdout)
            except Exception:
                try:
                    print("telnet not found, trying nc...")
                    result = subprocess.run(["nc", "-zv", hostname, port], capture_output=True, text=True)
                    print(result.stdout)
                except Exception as e:
                    print(f"Failed to run connectivity tools: {e}")
    
    # Redis Client Test
    print("\n=== Redis Client Test ===")
    try:
        print(f"Connecting to Redis at {redis_url}...")
        start_time = time.time()
        r = redis.from_url(redis_url, socket_timeout=5.0, socket_connect_timeout=5.0)
        ping_result = r.ping()
        end_time = time.time()
        
        if ping_result:
            print(f"✅ Redis connection successful (latency: {(end_time - start_time)*1000:.2f}ms)")
            
            # Get server info
            info = r.info()
            print(f"\nRedis Server Info:")
            print(f"- Version: {info.get('redis_version', 'Unknown')}")
            print(f"- Connected clients: {info.get('connected_clients', 'Unknown')}")
            print(f"- Memory used: {info.get('used_memory_human', 'Unknown')}")
            print(f"- Uptime: {info.get('uptime_in_days', 'Unknown')} days")
            
            # Test basic operations
            test_key = "worthit_diagnostics_test_key"
            r.set(test_key, "test_value")
            value = r.get(test_key)
            r.delete(test_key)
            
            if value == b"test_value":
                print("✅ Redis read/write operations successful")
            else:
                print(f"❌ Redis read/write operations failed. Got: {value}")
        else:
            print("❌ Redis ping failed")
    except redis.AuthenticationError as e:
        print(f"❌ Redis authentication failed: {e}")
        print("\nPossible solutions:")
        print("1. Check if the password in the Redis URL is correct")
        print("2. Verify Redis server authentication settings")
    except redis.ConnectionError as e:
        print(f"❌ Redis connection error: {e}")
        print("\nPossible solutions:")
        print("1. Check if Redis URL format is correct")
        print("2. Verify network connectivity")
        print("3. Check if Redis server is running")
        print("4. Verify firewall settings")
    except redis.TimeoutError as e:
        print(f"❌ Redis timeout error: {e}")
        print("\nPossible solutions:")
        print("1. Check network latency to Redis server")
        print("2. Increase timeout settings in your application")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    # Vercel and Redis compatibility check
    print("\n=== Vercel and Redis Compatibility Check ===")
    print("Note: Vercel Serverless Functions have the following limitations:")
    print("1. Execution timeout: 10 seconds maximum")
    print("2. Memory: 1024 MB maximum")
    print("3. Ephemeral filesystem: No persistent storage")
    print("4. Cold starts: Functions may need to establish new connections")
    print("\nRecommendations for Vercel + Redis:")
    print("1. Use connection pooling with appropriate timeouts")
    print("2. Implement retry logic for connection failures")
    print("3. Consider using Upstash Redis (Vercel integration) instead")
    print("4. For background processing, use a separate worker service on Render")
    
    # Render and Redis compatibility check
    print("\n=== Render and Redis Compatibility Check ===")
    print("Note: Render Web Services have the following characteristics:")
    print("1. Persistent connections: Can maintain long-lived Redis connections")
    print("2. Background processing: Suitable for worker processes")
    print("3. Sleep mode: Free tier services sleep after inactivity")
    print("\nRecommendations for Render + Redis:")
    print("1. Use connection pooling with appropriate timeouts")
    print("2. Implement reconnection logic for sleep mode recovery")
    print("3. Consider using a paid plan for critical worker processes")
    
except Exception as e:
    print(f"Error parsing Redis URL: {e}")
    sys.exit(1)

print("\n=== Diagnostics Complete ===")