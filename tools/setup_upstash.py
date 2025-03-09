#!/usr/bin/env python
"""
Upstash Redis Setup Script for WorthIt!

This script helps set up Upstash Redis as an alternative to Docker for WorthIt! project.
It guides through the process of creating an Upstash account, setting up a Redis database,
and configuring the application to use it.
"""

import os
import sys
import webbrowser
import subprocess
import time
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

def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f" {text} ".center(60, "="))
    print("=" * 60 + "\n")

def print_step(step_num, text):
    """Print a formatted step"""
    print(f"\n[Step {step_num}] {text}")
    print("-" * 60)

def update_env_files(redis_url):
    """Update .env and .env.test files with the new Redis URL"""
    for env_path in env_paths:
        if env_path.exists():
            # Read the current content
            with open(env_path, 'r') as f:
                content = f.read()
            
            # Check if REDIS_URL already exists
            if "REDIS_URL=" in content:
                # Replace the existing REDIS_URL
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if line.startswith("REDIS_URL="):
                        new_lines.append(f"REDIS_URL={redis_url}")
                    else:
                        new_lines.append(line)
                new_content = '\n'.join(new_lines)
            else:
                # Add the REDIS_URL at the end
                new_content = content.rstrip() + f"\nREDIS_URL={redis_url}\n"
            
            # Write the updated content
            with open(env_path, 'w') as f:
                f.write(new_content)
            
            print(f"✅ Updated {env_path} with new Redis URL")

def install_upstash_redis():
    """Install the upstash-redis package"""
    print("Installing upstash-redis package...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "upstash-redis"],
            check=True
        )
        print("✅ upstash-redis package installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install upstash-redis: {e}")
        return False

def test_redis_connection(redis_url):
    """Test the Redis connection using the redis-py package"""
    try:
        import redis
        print(f"Testing Redis connection to {redis_url}")
        
        # Create Redis client with appropriate settings
        connection_settings = {
            "decode_responses": True,
            "socket_timeout": 15.0,
            "socket_connect_timeout": 10.0,
            "retry_on_timeout": True
        }
        
        # Add Upstash-specific settings
        if "upstash" in redis_url:
            connection_settings.update({
                "socket_timeout": 30.0,
                "socket_connect_timeout": 20.0,
                "retry_on_timeout": True,
                "health_check_interval": 30
            })
        
        # Create Redis client
        r = redis.from_url(redis_url, **connection_settings)
        
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
            
            if value == "test_value":  # Changed from b"test_value" since we use decode_responses=True
                print("✅ Redis read/write operations successful")
                return True
            else:
                print("❌ Redis read/write operations failed")
                return False
    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        # Provide more helpful error messages for common issues
        if "connection refused" in str(e).lower():
            print("\nPossible solutions:")
            print("1. Check if the Redis URL is correct")
            print("2. Verify network connectivity")
            print("3. Ensure your IP is not blocked by Upstash")
        elif "authentication" in str(e).lower():
            print("\nPossible solutions:")
            print("1. Check if the password in the Redis URL is correct")
            print("2. Verify you have the correct access credentials")
        elif "timeout" in str(e).lower():
            print("\nPossible solutions:")
            print("1. Check network connectivity")
            print("2. Try increasing the connection timeout settings")
        return False

def main():
    print_header("Upstash Redis Setup for WorthIt!")
    print("This script will help you set up Upstash Redis as an alternative to Docker.")
    print("Follow the steps below to create an Upstash account, set up a Redis database,")
    print("and configure your application to use it.")
    
    # Step 1: Create Upstash Account
    print_step(1, "Create an Upstash Account")
    print("1. Go to https://console.upstash.com/")
    print("2. Sign up or log in")
    print("3. Click 'Create Database'")
    print("4. Choose the region closest to your deployment")
    print("5. Select the free tier plan")
    
    open_browser = input("\nWould you like to open the Upstash website now? (y/n): ")
    if open_browser.lower() == 'y':
        webbrowser.open("https://console.upstash.com/")
    
    # Step 2: Get Connection Details
    print_step(2, "Get Connection Details")
    print("Once you've created your database:")
    print("1. Find the 'Connect to your database' section")
    print("2. Copy the Redis connection string (UPSTASH_REDIS_URL)")
    
    redis_url = input("\nPaste your Upstash Redis URL here: ")
    if not redis_url or (not redis_url.startswith("redis://") and not redis_url.startswith("rediss://")):
        print("❌ Invalid Redis URL. It should start with 'redis://' or 'rediss://'.")
        return
    
    # For Upstash, we need to use rediss:// protocol for SSL connections
    if "upstash" in redis_url and not redis_url.startswith("rediss://"):
        redis_url = redis_url.replace("redis://", "rediss://")
        print(f"✅ Converted Redis URL to use SSL: {redis_url}")
    
    # Step 3: Update Environment Variables
    print_step(3, "Update Environment Variables")
    update_env_files(redis_url)
    
    # Step 4: Install upstash-redis package
    print_step(4, "Install upstash-redis Package")
    if not install_upstash_redis():
        print("\nYou can manually install it later with:")
        print("pip install upstash-redis")
    
    # Step 5: Test Connection
    print_step(5, "Test Connection")
    if test_redis_connection(redis_url):
        print("\n🎉 Upstash Redis setup completed successfully!")
        print("You can now use Redis in your application without Docker.")
    else:
        print("\n❌ Failed to connect to Upstash Redis.")
        print("Please check your connection details and try again.")
    
    print("\nFor more information, refer to the Upstash documentation:")
    print("https://docs.upstash.com/redis")

if __name__ == "__main__":
    main()