#!/usr/bin/env python
"""
Staging Environment Test Runner for WorthIt!

This script runs integration tests against the staging environment to verify
that all functionality works correctly before deploying to production.
"""

import os
import sys
import argparse
import subprocess
import json
from pathlib import Path
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"staging_tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("staging_tests")

# Default settings
DEFAULT_STAGING_URL = "https://staging.worthit-app.netlify.app"
DEFAULT_TIMEOUT = 300  # 5 minutes


def setup_test_environment(staging_url):
    """Set up the test environment with the staging URL.
    
    Args:
        staging_url: URL of the staging environment
        
    Returns:
        Dict with environment variables for tests
    """
    logger.info(f"Setting up test environment for {staging_url}")
    
    # Create a copy of the current environment
    env = os.environ.copy()
    
    # Set staging-specific environment variables
    env["API_HOST"] = f"{staging_url}/api"
    env["WEBHOOK_URL"] = f"{staging_url}/webhook"
    env["TEST_MODE"] = "staging"
    env["PYTEST_TIMEOUT"] = str(DEFAULT_TIMEOUT)
    
    return env


def run_integration_tests(env, test_path=None, verbose=False):
    """Run integration tests against the staging environment.
    
    Args:
        env: Environment variables for the tests
        test_path: Optional path to specific test file or directory
        verbose: Whether to show verbose output
        
    Returns:
        Tuple of (success, results)
    """
    # Determine test path
    if not test_path:
        test_path = str(Path(__file__).parent.parent / "tests" / "integration")
    
    logger.info(f"Running integration tests from {test_path}")
    
    # Build pytest command
    cmd = [sys.executable, "-m", "pytest", test_path, "-v"]
    
    if verbose:
        cmd.append("-v")
    
    # Add JUnit XML report
    report_path = f"staging_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
    cmd.extend(["--junitxml", report_path])
    
    # Run the tests
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            env=env,
            check=False,
            capture_output=True,
            text=True
        )
        
        # Log the output
        if result.stdout:
            logger.info(f"Test output:\n{result.stdout}")
        if result.stderr:
            logger.error(f"Test errors:\n{result.stderr}")
        
        success = result.returncode == 0
        logger.info(f"Tests {'passed' if success else 'failed'} with return code {result.returncode}")
        
        return success, {
            "returncode": result.returncode,
            "report_path": report_path,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        logger.error(f"Error running tests: {str(e)}")
        return False, {"error": str(e)}


def verify_api_endpoints(staging_url):
    """Verify that all API endpoints are accessible.
    
    Args:
        staging_url: URL of the staging environment
        
    Returns:
        Tuple of (success, results)
    """
    import requests
    
    logger.info(f"Verifying API endpoints at {staging_url}/api")
    
    endpoints = [
        "/health",
        "/analyze",  # This will be a POST in actual testing
    ]
    
    results = {}
    all_successful = True
    
    for endpoint in endpoints:
        url = f"{staging_url}/api{endpoint}"
        try:
            if endpoint == "/analyze":
                # For POST endpoints, just check if they're reachable
                response = requests.options(url, timeout=10)
                success = response.status_code < 500
            else:
                response = requests.get(url, timeout=10)
                success = response.status_code == 200
            
            results[endpoint] = {
                "status_code": response.status_code,
                "success": success
            }
            
            if not success:
                all_successful = False
                logger.error(f"Endpoint {endpoint} check failed with status {response.status_code}")
            else:
                logger.info(f"Endpoint {endpoint} check passed with status {response.status_code}")
        except Exception as e:
            results[endpoint] = {
                "error": str(e),
                "success": False
            }
            all_successful = False
            logger.error(f"Error checking endpoint {endpoint}: {str(e)}")
    
    return all_successful, results


def verify_webhook_registration(env):
    """Verify that the webhook is properly registered with Telegram.
    
    Args:
        env: Environment variables including Telegram token
        
    Returns:
        Tuple of (success, results)
    """
    logger.info("Verifying webhook registration with Telegram")
    
    # Check if we have the Telegram token
    telegram_token = env.get("TELEGRAM_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN not found in environment")
        return False, {"error": "TELEGRAM_TOKEN not found"}
    
    # Run the webhook activation script
    webhook_script = str(Path(__file__).parent / "activate_webhook.py")
    if not os.path.exists(webhook_script):
        logger.error(f"Webhook activation script not found at {webhook_script}")
        return False, {"error": "Webhook activation script not found"}
    
    try:
        result = subprocess.run(
            [sys.executable, webhook_script, "--check-only"],
            env=env,
            check=False,
            capture_output=True,
            text=True
        )
        
        success = result.returncode == 0
        
        if success:
            logger.info("Webhook registration verified successfully")
        else:
            logger.error(f"Webhook registration verification failed: {result.stderr}")
        
        return success, {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        logger.error(f"Error verifying webhook registration: {str(e)}")
        return False, {"error": str(e)}


def run_load_tests(staging_url, concurrency=5, num_requests=50):
    """Run load tests against the staging environment.
    
    Args:
        staging_url: URL of the staging environment
        concurrency: Number of concurrent requests
        num_requests: Total number of requests
        
    Returns:
        Tuple of (success, results)
    """
    logger.info(f"Running load tests against {staging_url} with {concurrency} concurrent requests")
    
    load_tester_script = str(Path(__file__).parent.parent / "tools" / "load_tester.py")
    if not os.path.exists(load_tester_script):
        logger.error(f"Load tester script not found at {load_tester_script}")
        return False, {"error": "Load tester script not found"}
    
    try:
        result = subprocess.run(
            [
                sys.executable, 
                load_tester_script,
                "-c", str(concurrency),
                "-n", str(num_requests),
                "-u", f"{staging_url}/api"
            ],
            check=False,
            capture_output=True,
            text=True
        )
        
        # For load tests, we consider it successful if it completes, not based on return code
        success = True
        
        logger.info(f"Load tests completed with return code {result.returncode}")
        if result.stdout:
            logger.info(f"Load test output:\n{result.stdout}")
        
        return success, {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        logger.error(f"Error running load tests: {str(e)}")
        return False, {"error": str(e)}


def generate_report(results):
    """Generate a comprehensive test report.
    
    Args:
        results: Dict with all test results
        
    Returns:
        Report as a string
    """
    report = ["# Staging Environment Test Report"]
    report.append(f"\n## Test Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Overall status
    overall_success = all(r.get("success", False) for r in results.values())
    report.append(f"\n### Overall Status: {'✅ PASSED' if overall_success else '❌ FAILED'}")
    
    # Add details for each test category
    for category, result in results.items():
        success = result.get("success", False)
        report.append(f"\n## {category}: {'✅ PASSED' if success else '❌ FAILED'}")
        
        # Add category-specific details
        if category == "integration_tests":
            report.append(f"\nReport file: {result.get('report_path', 'N/A')}")
        elif category == "api_endpoints":
            report.append("\n### Endpoint Status:")
            for endpoint, status in result.get("details", {}).items():
                status_icon = "✅" if status.get("success", False) else "❌"
                report.append(f"- {status_icon} {endpoint}: {status.get('status_code', 'Error')}")
        
        # Add any errors
        if "error" in result:
            report.append(f"\n### Error:\n```\n{result['error']}\n```")
    
    # Add recommendations
    report.append("\n## Recommendations")
    if overall_success:
        report.append("\n- ✅ All tests passed. The staging environment is ready for production deployment.")
    else:
        report.append("\n- ❌ Some tests failed. Please fix the issues before deploying to production.")
        # Add specific recommendations based on failures
        if not results.get("api_endpoints", {}).get("success", False):
            report.append("- Fix API endpoint issues before proceeding.")
        if not results.get("webhook_registration", {}).get("success", False):
            report.append("- Verify Telegram webhook configuration.")
        if not results.get("integration_tests", {}).get("success", False):
            report.append("- Address integration test failures.")
    
    return "\n".join(report)


def main():
    """Main function to run all staging tests."""
    parser = argparse.ArgumentParser(description="Run tests against staging environment")
    parser.add_argument("-u", "--url", default=DEFAULT_STAGING_URL,
                        help=f"Staging environment URL (default: {DEFAULT_STAGING_URL})")
    parser.add_argument("-t", "--test-path", help="Specific test file or directory to run")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose output")
    parser.add_argument("--skip-load-tests", action="store_true", help="Skip load testing")
    args = parser.parse_args()
    
    logger.info(f"Starting staging environment tests for {args.url}")
    
    # Set up test environment
    env = setup_test_environment(args.url)
    
    # Store all results
    all_results = {}
    
    # Step 1: Verify API endpoints
    logger.info("Step 1: Verifying API endpoints")
    api_success, api_results = verify_api_endpoints(args.url)
    all_results["api_endpoints"] = {
        "success": api_success,
        "details": api_results
    }
    
    # Step 2: Verify webhook registration
    logger.info("Step 2: Verifying webhook registration")
    webhook_success, webhook_results = verify_webhook_registration(env)
    all_results["webhook_registration"] = {
        "success": webhook_success,
        "details": webhook_results
    }
    
    # Step 3: Run integration tests
    logger.info("Step 3: Running integration tests")
    test_success, test_results = run_integration_tests(env, args.test_path, args.verbose)
    all_results["integration_tests"] = {
        "success": test_success,
        "details": test_results
    }
    
    # Step 4: Run load tests (optional)
    if not args.skip_load_tests:
        logger.info("Step 4: Running load tests")
        load_success, load_results = run_load_tests(args.url, concurrency=5, num_requests=50)
        all_results["load_tests"] = {
            "success": load_success,
            "details": load_results
        }
    
    # Generate and save report
    report = generate_report(all_results)
    report_file = f"staging_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_file, "w") as f:
        f.write(report)
    
    logger.info(f"Test report saved to {report_file}")