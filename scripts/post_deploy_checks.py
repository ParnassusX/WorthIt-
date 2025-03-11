#!/usr/bin/env python
"""
WorthIt! Post-Deployment Verification Script

This script should be run immediately after deployment to verify that
all components are properly configured and working as expected.
"""

import os
import sys
import json
import asyncio
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import Redis tester
from tools.redis_tester import RedisTester

class PostDeploymentChecker:
    """Verifies the deployment of WorthIt! application."""
    
    def __init__(self, base_url=None, verbose=False):
        """Initialize the deployment verifier."""
        load_dotenv()
        self.verbose = verbose
        self.base_url = base_url or os.getenv('WEBHOOK_URL', 'https://worthit-py.netlify.app').rsplit('/webhook', 1)[0]
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.redis_url = os.getenv('REDIS_URL')
        self.webhook_url = os.getenv('WEBHOOK_URL')
        self.results = {
            'environment_variables': {},
            'webhook_registration': {},
            'redis_connection': {},
            'function_endpoints': {},
            'web_app_status': {},
            'overall_status': 'pending'
        }
    
    def log(self, message):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(message)
        
    def check_environment_variables(self):
        """Check if all required environment variables are set."""
        required_vars = [
            'TELEGRAM_TOKEN',
            'REDIS_URL',
            'WEBHOOK_URL',
            'APIFY_TOKEN',
            'HF_TOKEN'
        ]
        
        self.log("\nChecking environment variables...")
        all_present = True
        
        for var in required_vars:
            value = os.getenv(var)
            is_present = bool(value)
            self.results['environment_variables'][var] = is_present
            
            if not is_present:
                all_present = False
                self.log(f"❌ {var} is not set")
            else:
                self.log(f"✅ {var} is set")
                
                # Additional checks for specific variables
                if var == 'REDIS_URL' and 'upstash' in value and not value.startswith('rediss://'):
                    self.log(f"⚠️ {var} should use rediss:// protocol for Upstash")
                    all_present = False
        
        self.results['environment_variables']['status'] = 'pass' if all_present else 'fail'
        return all_present
    
    def check_webhook_registration(self):
        """Check if the webhook is properly registered with Telegram."""
        if not self.telegram_token:
            self.log("\n❌ Cannot check webhook registration: TELEGRAM_TOKEN is not set")
            self.results['webhook_registration']['status'] = 'fail'
            self.results['webhook_registration']['error'] = 'TELEGRAM_TOKEN is not set'
            return False
        
        self.log("\nChecking webhook registration...")
        api_url = f"https://api.telegram.org/bot{self.telegram_token}/getWebhookInfo"
        
        try:
            response = requests.get(api_url)
            webhook_info = response.json()
            
            if response.status_code != 200 or not webhook_info.get('ok'):
                self.log(f"❌ Failed to get webhook info: {webhook_info.get('description')}")
                self.results['webhook_registration']['status'] = 'fail'
                self.results['webhook_registration']['error'] = webhook_info.get('description')
                return False
            
            current_url = webhook_info.get('result', {}).get('url', '')
            self.results['webhook_registration']['current_url'] = current_url
            
            if not current_url:
                self.log("❌ No webhook URL is currently set")
                self.results['webhook_registration']['status'] = 'fail'
                return False
            
            expected_url = self.webhook_url
            if current_url != expected_url:
                self.log(f"⚠️ Current webhook URL ({current_url}) doesn't match expected URL ({expected_url})")
                self.results['webhook_registration']['status'] = 'warning'
                return False
            
            self.log(f"✅ Webhook is properly registered: {current_url}")
            self.results['webhook_registration']['status'] = 'pass'
            return True
            
        except Exception as e:
            self.log(f"❌ Error checking webhook registration: {str(e)}")
            self.results['webhook_registration']['status'] = 'fail'
            self.results['webhook_registration']['error'] = str(e)
            return False
    
    async def check_redis_connection(self):
        """Check if Redis connection is working."""
        if not self.redis_url:
            self.log("\n❌ Cannot check Redis connection: REDIS_URL is not set")
            self.results['redis_connection']['status'] = 'fail'
            self.results['redis_connection']['error'] = 'REDIS_URL is not set'
            return False
        
        self.log("\nChecking Redis connection...")
        redis_tester = RedisTester(redis_url=self.redis_url)
        
        # Test async connection
        async_result = await redis_tester.test_async()
        self.results['redis_connection']['async'] = async_result.get('success', False)
        
        # Test sync connection
        sync_result = redis_tester.test_sync()
        self.results['redis_connection']['sync'] = sync_result.get('success', False)
        
        if async_result and sync_result:
            self.log("✅ Redis connection is working (both async and sync)")
            self.results['redis_connection']['status'] = 'pass'
            return True
        elif async_result or sync_result:
            self.log("⚠️ Redis connection is partially working")
            self.results['redis_connection']['status'] = 'warning'
            return False
        else:
            self.log("❌ Redis connection is not working")
            self.results['redis_connection']['status'] = 'fail'
            return False
    
    def check_function_endpoints(self):
        """Check if Netlify function endpoints are accessible."""
        self.log("\nChecking function endpoints...")
        endpoints = [
            '/webhook',
            '/.netlify/functions/webhook',
            '/.netlify/functions/analyze'
        ]
        
        all_accessible = True
        for endpoint in endpoints:
            url = f"{self.base_url}{endpoint}"
            try:
                # Just check if the endpoint exists, don't worry about the response code
                # since these endpoints might require POST requests with specific data
                response = requests.head(url)
                status = response.status_code
                
                # 405 Method Not Allowed is actually good - it means the endpoint exists
                # but just doesn't accept HEAD requests
                if status != 404:
                    self.log(f"✅ Endpoint {endpoint} is accessible (status: {status})")
                    self.results['function_endpoints'][endpoint] = 'pass'
                else:
                    self.log(f"❌ Endpoint {endpoint} returned 404 Not Found")
                    self.results['function_endpoints'][endpoint] = 'fail'
                    all_accessible = False
                    
            except Exception as e:
                self.log(f"❌ Error checking endpoint {endpoint}: {str(e)}")
                self.results['function_endpoints'][endpoint] = 'fail'
                self.results['function_endpoints'][f"{endpoint}_error"] = str(e)
                all_accessible = False
        
        self.results['function_endpoints']['status'] = 'pass' if all_accessible else 'fail'
        return all_accessible
    
    def check_web_app(self):
        """Check if the web app is accessible and properly configured."""
        self.log("\nChecking web app...")
        try:
            response = requests.get(self.base_url)
            status = response.status_code
            
            if status == 200:
                self.log(f"✅ Web app is accessible (status: {status})")
                self.results['web_app_status']['status'] = 'pass'
                return True
            else:
                self.log(f"❌ Web app returned unexpected status code: {status}")
                self.results['web_app_status']['status'] = 'fail'
                self.results['web_app_status']['error'] = f"Unexpected status code: {status}"
                return False
                
        except Exception as e:
            self.log(f"❌ Error checking web app: {str(e)}")
            self.results['web_app_status']['status'] = 'fail'
            self.results['web_app_status']['error'] = str(e)
            return False
    
    async def run_checks(self):
        """Run all verification checks."""
        print("\n===== WorthIt! Post-Deployment Verification =====\n")
        
        env_check = self.check_environment_variables()
        webhook_check = self.check_webhook_registration()
        redis_check = await self.check_redis_connection()
        endpoint_check = self.check_function_endpoints()
        web_app_check = self.check_web_app()
        
        # Determine overall status
        if env_check and webhook_check and redis_check and endpoint_check and web_app_check:
            self.results['overall_status'] = 'pass'
            print("\n✅ All checks passed! Deployment is verified.")
        elif not env_check or not endpoint_check or not web_app_check:
            self.results['overall_status'] = 'fail'
            print("\n❌ Critical checks failed! Deployment has issues.")
        else:
            self.results['overall_status'] = 'warning'
            print("\n⚠️ Some checks failed! Deployment may have issues.")
        
        # Print detailed results
        if self.verbose:
            print("\nDetailed Results:")
            print(json.dumps(self.results, indent=2))
        
        return self.results

async def main():
    """Main function to run the deployment verification."""
    parser = argparse.ArgumentParser(description="Run post-deployment checks for WorthIt!")
    parser.add_argument(
        "--base-url", 
        help="Base URL of the deployed application"
    )
    parser.add_argument(
        "--verbose", 
        "-v", 
        action="store_true", 
        help="Show detailed information"
    )
    parser.add_argument(
        "--output",
        help="Output file for results (JSON format)"
    )
    args = parser.parse_args()
    
    checker = PostDeploymentChecker(base_url=args.base_url, verbose=args.verbose)
    results = await checker.run_checks()
    
    # Save results to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")

if __name__ == "__main__":
    asyncio.run(main())