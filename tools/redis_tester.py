#!/usr/bin/env python
"""
Redis Connection Tester for WorthIt!

This utility provides a standardized way to test Redis connections,
particularly focusing on Upstash Redis compatibility. It can be used
by various components of the application to ensure consistent Redis testing.
"""

import os
import sys
import asyncio
import argparse
from typing import Dict, Any, Optional, Union
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import Redis clients
from redis.asyncio import Redis as AsyncRedis
import redis

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RedisTester:
    """A utility class for testing Redis connections with support for both
    synchronous and asynchronous Redis clients."""
    
    def __init__(self, redis_url: Optional[str] = None):
        """Initialize the Redis tester with an optional Redis URL.
        
        Args:
            redis_url: The Redis URL to test. If not provided, it will be loaded from environment.
        """
        # Load environment variables if not already loaded
        self._load_environment()
        
        # Use provided URL or get from environment
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        if not self.redis_url:
            raise ValueError("Redis URL not provided and not found in environment variables")
        
        # Store original URL before any modifications
        self.original_url = self.redis_url
        
        # Check if this is an Upstash URL and convert if needed
        self._prepare_upstash_url()
    
    def _load_environment(self):
        """Load environment variables from .env.test or .env file."""
        env_paths = [
            Path(__file__).parent.parent / ".env.test",
            Path(__file__).parent.parent / ".env"
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"Loaded environment from {env_path}")
                break
    
    def _prepare_upstash_url(self):
        """Prepare the Redis URL for Upstash if needed."""
        # For Upstash, we need to use rediss:// protocol instead of explicit ssl parameter
        if 'upstash' in self.redis_url and not self.redis_url.startswith('rediss://'):
            self.redis_url = self.redis_url.replace('redis://', 'rediss://')
            logger.info(f'Converting to SSL URL for Upstash: {self.redis_url}')
    
    def get_connection_settings(self) -> Dict[str, Any]:
        """Get the appropriate connection settings based on the Redis URL."""
        # Base settings for all Redis connections
        settings = {
            "decode_responses": True,
            "socket_timeout": 15.0,
            "socket_connect_timeout": 10.0,
            "retry_on_timeout": True,
            "health_check_interval": 60
        }
        
        # Upstash-specific settings
        if 'upstash' in self.redis_url:
            settings.update({
                "socket_timeout": 30.0,
                "socket_connect_timeout": 20.0,
                "retry_on_timeout": True
            })
        
        return settings
    
    def test_sync(self) -> Dict[str, Any]:
        """Test Redis connection using synchronous client."""
        result = {
            "success": False,
            "url": self.original_url,  # Use original URL in results
            "modified_url": self.redis_url if self.redis_url != self.original_url else None,
            "is_upstash": 'upstash' in self.redis_url,
            "operations": {},
            "error": None
        }
        
        try:
            # Create Redis client
            settings = self.get_connection_settings()
            client = redis.from_url(self.redis_url, **settings)
            
            # Test connection with PING
            ping_result = client.ping()
            result["operations"]["ping"] = ping_result
            
            if ping_result:
                # Test basic operations
                test_key = "worthit_test_key"
                set_result = client.set(test_key, "test_value")
                get_result = client.get(test_key)
                del_result = client.delete(test_key)
                
                result["operations"]["set"] = set_result
                result["operations"]["get"] = get_result
                result["operations"]["delete"] = del_result
                result["operations"]["data_integrity"] = (get_result == "test_value")
                
                # Get server info
                try:
                    info = client.info()
                    result["server_info"] = {
                        "version": info.get('redis_version'),
                        "connected_clients": info.get('connected_clients'),
                        "used_memory_human": info.get('used_memory_human')
                    }
                except Exception as e:
                    result["server_info_error"] = str(e)
                
                # Set overall success
                result["success"] = result["operations"]["data_integrity"]
            
            # Close connection
            client.close()
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    async def test_async(self) -> Dict[str, Any]:
        """Test Redis connection using asynchronous client."""
        result = {
            "success": False,
            "url": self.original_url,  # Use original URL in results
            "modified_url": self.redis_url if self.redis_url != self.original_url else None,
            "is_upstash": 'upstash' in self.redis_url,
            "operations": {},
            "error": None
        }
        
        try:
            # Create Redis client
            settings = self.get_connection_settings()
            client = AsyncRedis.from_url(self.redis_url, **settings)
            
            # Test connection with PING
            ping_result = await client.ping()
            result["operations"]["ping"] = ping_result
            
            if ping_result:
                # Test basic operations
                test_key = "worthit_test_key"
                set_result = await client.set(test_key, "test_value")
                get_result = await client.get(test_key)
                del_result = await client.delete(test_key)
                
                result["operations"]["set"] = set_result
                result["operations"]["get"] = get_result
                result["operations"]["delete"] = del_result
                result["operations"]["data_integrity"] = (get_result == "test_value")
                
                # Set overall success
                result["success"] = result["operations"]["data_integrity"]
            
            # Close connection
            await client.aclose()
            
        except Exception as e:
            result["error"] = str(e)
        
        return result

    def print_results(self, result: Dict[str, Any], verbose: bool = False):
        """Print the test results in a user-friendly format."""
        if result["success"]:
            print("✅ Redis connection successful")
            
            if result["is_upstash"]:
                print("   Using Upstash Redis")
                if result["modified_url"]:
                    print(f"   URL converted to use SSL: {result['modified_url']}")
            
            print("\nOperations:")
            for op, res in result["operations"].items():
                print(f"- {op}: {'✅' if res else '❌'}")
            
            if "server_info" in result and verbose:
                print("\nServer Info:")
                for key, value in result["server_info"].items():
                    print(f"- {key}: {value}")
        else:
            print("❌ Redis connection failed")
            if result["error"]:
                print(f"   Error: {result['error']}")
                
                # Provide helpful suggestions based on error
                if "connection refused" in result["error"].lower():
                    print("\nPossible solutions:")
                    print("1. Check if Redis server is running")
                    print("2. Verify the Redis URL is correct")
                    print("3. Check firewall settings")
                elif "authentication" in result["error"].lower():
                    print("\nPossible solutions:")
                    print("1. Check if the password in the Redis URL is correct")
                    print("2. Verify you have the correct access credentials")
                elif "timeout" in result["error"].lower():
                    print("\nPossible solutions:")
                    print("1. Check network connectivity")
                    print("2. Increase connection timeout settings")
                    print("3. Verify the Redis server is responsive")

# Command-line interface
def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test Redis connection for WorthIt!")
    parser.add_argument(
        "--url", 
        help="Redis URL to test (overrides environment variable)"
    )
    parser.add_argument(
        "--async", 
        dest="async_mode",
        action="store_true", 
        help="Use asynchronous Redis client"
    )
    parser.add_argument(
        "--verbose", 
        "-v", 
        action="store_true", 
        help="Show detailed information"
    )
    return parser.parse_args()

async def main_async(args):
    """Run the async test."""
    tester = RedisTester(args.url)
    result = await tester.test_async()
    tester.print_results(result, args.verbose)
    return result["success"]

def main_sync(args):
    """Run the sync test."""
    tester = RedisTester(args.url)
    result = tester.test_sync()
    tester.print_results(result, args.verbose)
    return result["success"]

# Main entry point
def main():
    """Main entry point for the script."""
    args = parse_args()
    
    if args.async_mode:
        success = asyncio.run(main_async(args))
    else:
        success = main_sync(args)
    
    # Return appropriate exit code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()