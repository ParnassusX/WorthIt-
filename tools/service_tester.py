#!/usr/bin/env python
"""
Test Services CLI Script for WorthIt!

This script provides CLI commands to test various services used by WorthIt! without
requiring local installations. It uses environment variables from .env.test file.
"""

import os
import sys
import argparse
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv
import redis

# Load test environment variables
env_test_path = Path(__file__).parent.parent / ".env.test"
if env_test_path.exists():
    load_dotenv(env_test_path)
else:
    print("Error: .env.test file not found!")
    sys.exit(1)

def test_redis():
    """Test Redis connection using redis-py"""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("Error: REDIS_URL not found in .env.test")
        return False
    
    print(f"Testing Redis connection to {redis_url}")
    
    try:
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Test connection with PING
        if r.ping():
            print("✅ Redis connection successful")
            
            # Additional diagnostics
            info = r.info()
            print(f"\nRedis Server Info:")
            print(f"- Version: {info['redis_version']}")
            print(f"- Connected clients: {info['connected_clients']}")
            print(f"- Memory used: {info['used_memory_human']}")
            
            # Test basic operations
            test_key = "worthit_test_key"
            r.set(test_key, "test_value")
            value = r.get(test_key)
            r.delete(test_key)
            
            if value == b"test_value":
                print("✅ Redis read/write operations successful")
            else:
                print("❌ Redis read/write operations failed")
                return False
            
            return True
    except redis.ConnectionError as e:
        print("❌ Redis connection error:")
        print(f"  - {str(e)}")
        print("\nPossible solutions:")
        print("1. Check if Redis URL is correct")
        print("2. Verify network connectivity")
        print("3. Check if Redis server is running")
        print("4. Verify firewall settings")
        return False
    except redis.RedisError as e:
        print(f"❌ Redis operation error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

    # For local Redis
    if "localhost" in redis_url:
        try:
            # Simple ping test using redis-cli
            result = subprocess.run(
                ["redis-cli", "ping"],
                capture_output=True,
                text=True,
                check=True
            )
            if "PONG" in result.stdout:
                print("✅ Redis local connection successful")
                return True
            else:
                print("❌ Redis local connection failed")
                return False
        except subprocess.CalledProcessError:
            print("❌ Redis local connection failed. Is redis-server running?")
            print("   Try: docker run --name redis-test -p 6379:6379 -d redis")
            return False
        except FileNotFoundError:
            print("❌ redis-cli not found. Using Docker instead:")
            try:
                # Try using Docker for Redis testing
                result = subprocess.run(
                    ["docker", "run", "--rm", "redis", "redis-cli", "-h", "host.docker.internal", "ping"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                if "PONG" in result.stdout:
                    print("✅ Redis connection via Docker successful")
                    return True
                else:
                    print("❌ Redis connection via Docker failed")
                    return False
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("❌ Docker not available. Please install Redis or Docker.")
                return False
    # For remote Redis
    else:
        # Extract host and port from Redis URL
        # Format: redis://default:password@hostname:port
        try:
            parts = redis_url.split('@')[1].split(':')  
            host = parts[0]
            port = parts[1]
            
            # Test using curl to Redis info endpoint
            print(f"Testing remote Redis at {host}:{port}")
            print("Note: This is a basic connectivity test only")
            
            # We'll just check if the host is reachable
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", f"{host}:{port}"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("✅ Remote Redis host is reachable")
                return True
            else:
                print("❌ Remote Redis host connection failed")
                return False
        except Exception as e:
            print(f"❌ Error parsing or connecting to Redis URL: {e}")
            return False

def test_vercel():
    """Test Vercel CLI"""
    print("Testing Vercel CLI...")
    try:
        # Check if Vercel CLI is installed
        result = subprocess.run(
            ["npx", "--yes", "vercel", "--version"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✅ Vercel CLI available: {result.stdout.strip()}")
            
            # Test project info (doesn't require authentication for public projects)
            print("\nChecking project deployment status:")
            webhook_url = os.getenv("WEBHOOK_URL", "")
            project_name = webhook_url.split("/")[2].split(".")[0] if webhook_url else "worth-it-bot"
            
            result = subprocess.run(
                ["npx", "--yes", "vercel", "inspect", project_name],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ Project '{project_name}' info retrieved successfully")
                return True
            else:
                print(f"❌ Could not retrieve project info: {result.stderr}")
                print("Note: This may require authentication. Run 'npx vercel login' first.")
                return False
        else:
            print(f"❌ Vercel CLI not available: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error testing Vercel: {e}")
        return False

def test_render():
    """Test Render.com API using their CLI equivalent"""
    render_api_key = os.getenv("RENDER_API_KEY")
    if not render_api_key:
        print("Error: RENDER_API_KEY not found in .env.test")
        return False
    
    print("Testing Render.com API...")
    
    # Using curl as CLI equivalent for Render API
    try:
        # List services (basic API test)
        cmd = [
            "curl", "-s", 
            "-H", f"Authorization: Bearer {render_api_key}",
            "https://api.render.com/v1/services"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        try:
            # Try to parse as JSON to verify it's a valid response
            services = json.loads(result.stdout)
            print(f"✅ Render API connection successful. Found {len(services)} services.")
            return True
        except json.JSONDecodeError:
            print(f"❌ Render API returned invalid JSON: {result.stdout[:100]}...")
            return False
    except Exception as e:
        print(f"❌ Error testing Render API: {e}")
        return False

def test_huggingface():
    """Test Hugging Face API token"""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("Error: HF_TOKEN not found in .env.test")
        return False
    
    print("Testing Hugging Face API token...")
    
    try:
        # Test API token with a simple model list request
        cmd = [
            "curl", "-s",
            "-H", f"Authorization: Bearer {hf_token}",
            "https://huggingface.co/api/models?limit=1"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        try:
            # Try to parse as JSON to verify it's a valid response
            response = json.loads(result.stdout)
            if isinstance(response, list) and len(response) > 0:
                print("✅ Hugging Face API token is valid")
                return True
            else:
                print(f"❌ Hugging Face API returned unexpected response: {result.stdout[:100]}...")
                return False
        except json.JSONDecodeError:
            print(f"❌ Hugging Face API returned invalid JSON: {result.stdout[:100]}...")
            return False
    except Exception as e:
        print(f"❌ Error testing Hugging Face API: {e}")
        return False

def test_apify():
    """Test Apify API token"""
    apify_token = os.getenv("APIFY_TOKEN")
    if not apify_token:
        print("Error: APIFY_TOKEN not found in .env.test")
        return False
    
    print("Testing Apify API token...")
    
    try:
        # Test API token with a simple user info request
        cmd = [
            "curl", "-s",
            "-H", f"Authorization: Bearer {apify_token}",
            "https://api.apify.com/v2/user/me"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        try:
            # Try to parse as JSON to verify it's a valid response
            response = json.loads(result.stdout)
            if "userId" in response:
                print(f"✅ Apify API token is valid. User ID: {response['userId']}")
                return True
            else:
                print(f"❌ Apify API token is invalid: {response.get('error', 'Unknown error')}")
                return False
        except json.JSONDecodeError:
            print(f"❌ Apify API returned invalid JSON: {result.stdout[:100]}...")
            return False
    except Exception as e:
        print(f"❌ Error testing Apify API: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test WorthIt! services using CLI tools")
    parser.add_argument("--all", action="store_true", help="Test all services")
    parser.add_argument("--redis", action="store_true", help="Test Redis connection")
    parser.add_argument("--vercel", action="store_true", help="Test Vercel CLI")
    parser.add_argument("--render", action="store_true", help="Test Render.com API")
    parser.add_argument("--hf", action="store_true", help="Test Hugging Face API token")
    parser.add_argument("--apify", action="store_true", help="Test Apify API token")
    
    args = parser.parse_args()
    
    # If no specific test is selected, show help
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    results = {}
    
    # Run selected tests
    if args.all or args.redis:
        results["Redis"] = test_redis()
    
    if args.all or args.vercel:
        results["Vercel"] = test_vercel()
    
    if args.all or args.render:
        results["Render"] = test_render()
    
    if args.all or args.hf:
        results["Hugging Face"] = test_huggingface()
    
    if args.all or args.apify:
        results["Apify"] = test_apify()
    
    # Print summary
    print("\n" + "=" * 50)
    print("Test Results Summary:")
    print("=" * 50)
    
    for service, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{service}: {status}")
    
    # Overall result
    if all(results.values()):
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed. See details above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())