#!/usr/bin/env python
"""
Integration Test Runner for WorthIt!

This script runs all integration tests against the staging environment to verify
that all user journeys work correctly before deploying to production.
"""

import os
import sys
import argparse
import subprocess
import json
import logging
from pathlib import Path
from datetime import datetime
import asyncio
import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"integration_tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("integration_tests")

# Default settings
DEFAULT_STAGING_URL = "https://staging.worthit-app.netlify.app"
DEFAULT_TIMEOUT = 300  # 5 minutes


def parse_arguments():
    """Parse command line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(description="Run integration tests against staging environment")
    parser.add_argument(
        "--staging-url",
        default=os.getenv("STAGING_URL", DEFAULT_STAGING_URL),
        help=f"URL of the staging environment (default: {DEFAULT_STAGING_URL})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Timeout in seconds for each test (default: {DEFAULT_TIMEOUT})"
    )
    parser.add_argument(
        "--report-file",
        default=f"integration_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="File to write test results to"
    )
    parser.add_argument(
        "--verify-user-journeys",
        action="store_true",
        help="Run tests that verify all user journeys"
    )
    parser.add_argument(
        "--test-path",
        default="tests/integration",
        help="Path to integration tests (default: tests/integration)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    return parser.parse_args()


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
    env["TEST_MODE"] = "1"
    env["TESTING_ENVIRONMENT"] = "staging"
    
    return env


def run_integration_tests(args, env):
    """Run integration tests using pytest.
    
    Args:
        args: Command line arguments
        env: Environment variables for tests
        
    Returns:
        Tuple of (success, report)
    """
    logger.info(f"Running integration tests from {args.test_path}")
    
    # Prepare pytest arguments
    pytest_args = [
        args.test_path,
        "-v" if args.verbose else "",
        f"--timeout={args.timeout}",
        "--json-report",
        f"--json-report-file={args.report_file}"
    ]
    
    # Filter out empty arguments
    pytest_args = [arg for arg in pytest_args if arg]
    
    try:
        # Run pytest
        result = pytest.main(pytest_args)
        success = result == 0
        
        # Load the JSON report
        report = {}
        if os.path.exists(args.report_file):
            with open(args.report_file, 'r') as f:
                report = json.load(f)
        
        return success, report
    except Exception as e:
        logger.error(f"Error running tests: {str(e)}")
        return False, {"error": str(e)}


def verify_user_journeys(report):
    """Verify that all user journeys are working correctly.
    
    Args:
        report: Test report from pytest
        
    Returns:
        Tuple of (success, failed_journeys)
    """
    logger.info("Verifying user journeys")
    
    # List of critical user journeys that must pass
    critical_journeys = [
        "test_complete_user_journey",
        "test_product_analysis_workflow",
        "test_payment_processing"
    ]
    
    failed_journeys = []
    
    # Check if all critical journeys passed
    for test in report.get("tests", []):
        test_name = test.get("name", "")
        outcome = test.get("outcome", "")
        
        for journey in critical_journeys:
            if journey in test_name and outcome != "passed":
                failed_journeys.append({
                    "name": test_name,
                    "outcome": outcome,
                    "message": test.get("call", {}).get("longrepr", "No error message")
                })
    
    success = len(failed_journeys) == 0
    return success, failed_journeys


def generate_summary(success, report, failed_journeys=None):
    """Generate a summary of the test results.
    
    Args:
        success: Whether all tests passed
        report: Test report from pytest
        failed_journeys: List of failed user journeys
        
    Returns:
        Summary string
    """
    summary = ["\n=== Integration Test Summary ==="]
    
    # Overall status
    if success:
        summary.append("✅ All integration tests passed!")
    else:
        summary.append("❌ Some integration tests failed!")
    
    # Test statistics
    summary.append("\nTest Statistics:")
    summary.append(f"  Total tests: {report.get('summary', {}).get('total', 0)}")
    summary.append(f"  Passed: {report.get('summary', {}).get('passed', 0)}")
    summary.append(f"  Failed: {report.get('summary', {}).get('failed', 0)}")
    summary.append(f"  Skipped: {report.get('summary', {}).get('skipped', 0)}")
    summary.append(f"  Duration: {report.get('duration', 0):.2f} seconds")
    
    # Failed user journeys
    if failed_journeys:
        summary.append("\nFailed User Journeys:")
        for journey in failed_journeys:
            summary.append(f"  ❌ {journey['name']}")
            summary.append(f"     Reason: {journey['outcome']}")
    
    # Recommendations
    summary.append("\nRecommendations:")
    if success:
        summary.append("  ✅ The application is ready for production deployment!")
    else:
        summary.append("  ❌ Fix the failed tests before deploying to production.")
        if failed_journeys:
            summary.append("  ❌ Critical user journeys are failing - high priority fixes needed!")
    
    return "\n".join(summary)


def main():
    """Main function."""
    args = parse_arguments()
    
    # Set up test environment
    env = setup_test_environment(args.staging_url)
    
    # Run integration tests
    success, report = run_integration_tests(args, env)
    
    # Verify user journeys
    journeys_success, failed_journeys = verify_user_journeys(report)
    
    # Generate and print summary
    summary = generate_summary(success and journeys_success, report, failed_journeys)
    print(summary)
    
    # Exit with appropriate status code
    return 0 if success and journeys_success else 1


if __name__ == "__main__":
    sys.exit(main())