#!/usr/bin/env python
"""
Redis Connection Test Script for WorthIt!

This script provides a comprehensive test for Redis connections,
specifically optimized for Upstash Redis. It tests both synchronous
and asynchronous connections and provides detailed diagnostics.
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

# Import the Redis tester utility
from tools.redis_tester import RedisTester

def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Test Redis connection for WorthIt!")
    parser.add_argument(
        "--url", 
        help="Redis URL to test (overrides environment variable)"
    )
    parser.add_argument(
        "--env-file",
        help="Path to .env file to load"
    )
    parser.add_argument(
        "--async-only", 
        action="store_true", 
        help="Only test asynchronous Redis client"
    )
    parser.add_argument(
        "--sync-only", 
        action="store_true", 
        help="Only test synchronous Redis client"
    )
    parser.add_argument(
        "--verbose", 
        "-v", 
        action="store_true", 
        help="Show detailed information"
    )
    return parser.parse_args()

async def run_tests(args):
    """Run the Redis connection tests."""
    # Load environment variables
    if args.env_file and os.path.exists(args.env_file):
        load_dotenv(args.env_file)
        print(f"Loaded environment from {args.env_file}")
    else:
        # Try to load from default locations
        env_paths = [
            Path(__file__).parent / ".env.test",
            Path(__file__).parent / ".env"
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                print(f"Loaded environment from {env_path}")
                break
    
    # Create the Redis tester
    tester = RedisTester(args.url)
    
    # Print test header
    print("\n" + "=" * 60)
    print(" Redis Connection Test ".center(60, "="))
    print("=" * 60)
    
    # Show connection details
    print(f"\nTesting connection to: {tester.original_url}")
    if tester.redis_url != tester.original_url:
        print(f"URL converted for SSL: {tester.redis_url}")
    
    print("\nRunning tests...")
    
    success = True
    
    # Run synchronous test if requested
    if not args.async_only:
        print("\n" + "-" * 60)
        print(" Synchronous Redis Client Test ".center(60, "-"))
        print("-" * 60)
        
        sync_result = tester.test_sync()
        tester.print_results(sync_result, args.verbose)
        success = success and sync_result["success"]
    
    # Run asynchronous test if requested
    if not args.sync_only:
        print("\n" + "-" * 60)
        print(" Asynchronous Redis Client Test ".center(60, "-"))
        print("-" * 60)
        
        async_result = await tester.test_async()
        tester.print_results(async_result, args.verbose)
        success = success and async_result["success"]
    
    # Print overall result
    print("\n" + "=" * 60)
    if success:
        print(" ✅ All Redis tests passed successfully! ".center(60, "="))
    else:
        print(" ❌ Some Redis tests failed! ".center(60, "="))
    print("=" * 60 + "\n")
    
    return success

async def main():
    """Main entry point for the script."""
    args = parse_args()
    success = await run_tests(args)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())