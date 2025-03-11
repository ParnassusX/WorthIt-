#!/usr/bin/env python
"""
Load Testing Script for WorthIt! Security Features

This script performs load testing specifically on the security features of WorthIt! API
to ensure they can handle expected traffic and identify performance bottlenecks
before production deployment.
"""

import os
import sys
import time
import json
import asyncio
import argparse
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

import httpx
import aiohttp
import matplotlib.pyplot as plt
from rich.console import Console
from rich.progress import Progress, TaskID
from rich.table import Table

# Load environment variables
env_path = Path(__file__).parent.parent / ".env.test"
if env_path.exists():
    load_dotenv(env_path)
else:
    print("Warning: .env.test file not found, using system environment variables")

# Initialize console for rich output
console = Console()

# Default settings
DEFAULT_CONCURRENCY = 10
DEFAULT_REQUESTS = 100
DEFAULT_API_URL = os.getenv("API_HOST", "https://worthit-py.netlify.app/api")
TEST_PAYMENT_DATA = [
    {
        "card_number": "4111111111111111",
        "expiry": "12/25",
        "cvv": "123",
        "amount": 99.99,
        "currency": "USD",
        "customer_id": "test_user_123"
    },
    {
        "card_number": "5555555555554444",
        "expiry": "01/26",
        "cvv": "456",
        "amount": 149.99,
        "currency": "USD",
        "customer_id": "test_user_456"
    },
    {
        "card_number": "378282246310005",
        "expiry": "03/27",
        "cvv": "789",
        "amount": 199.99,
        "currency": "USD",
        "customer_id": "test_user_789"
    }
]


class SecurityLoadTester:
    """Load testing class for WorthIt! API security features."""
    
    def __init__(self, api_url: str, concurrency: int, total_requests: int):
        """Initialize the load tester.
        
        Args:
            api_url: Base URL of the API to test
            concurrency: Number of concurrent requests
            total_requests: Total number of requests to make
        """
        self.api_url = api_url.rstrip('/')
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.results = {
            "payment_encryption": [],
            "fraud_detection": [],
            "key_rotation": []
        }
        self.errors = {
            "payment_encryption": [],
            "fraud_detection": [],
            "key_rotation": []
        }
        self.start_time = None
        self.end_time = None
    
    async def run_test(self) -> Dict[str, Any]:
        """Run the load test.
        
        Returns:
            Dictionary with test results
        """
        self.start_time = time.time()
        
        with Progress() as progress:
            payment_task = progress.add_task("[cyan]Testing payment encryption...", total=self.total_requests)
            fraud_task = progress.add_task("[yellow]Testing fraud detection...", total=self.total_requests)
            key_task = progress.add_task("[green]Testing key rotation...", total=self.total_requests)
            
            # Create a semaphore to limit concurrency
            semaphore = asyncio.Semaphore(self.concurrency)
            
            # Create tasks for payment encryption tests
            payment_tasks = []
            for i in range(self.total_requests):
                # Select test payment data (round-robin)
                test_data = TEST_PAYMENT_DATA[i % len(TEST_PAYMENT_DATA)]
                payment_tasks.append(self._test_payment_encryption(semaphore, test_data, progress, payment_task))
            
            # Create tasks for fraud detection tests
            fraud_tasks = []
            for i in range(self.total_requests):
                # Select test payment data (round-robin)
                test_data = TEST_PAYMENT_DATA[i % len(TEST_PAYMENT_DATA)]
                # Modify amount to test fraud detection
                if i % 10 == 0:  # Every 10th request is high-risk
                    test_data = test_data.copy()
                    test_data["amount"] = 5000  # High amount to trigger fraud detection
                fraud_tasks.append(self._test_fraud_detection(semaphore, test_data, progress, fraud_task))
            
            # Create tasks for key rotation tests
            key_tasks = []
            for i in range(self.total_requests):
                key_tasks.append(self._test_key_rotation(semaphore, progress, key_task))
            
            # Run all tasks concurrently
            await asyncio.gather(
                *payment_tasks,
                *fraud_tasks,
                *key_tasks
            )
        
        self.end_time = time.time()
        
        # Calculate statistics
        stats = self._calculate_statistics()
        
        return stats
    
    async def _test_payment_encryption(self, semaphore: asyncio.Semaphore, payment_data: Dict[str, Any],
                                     progress: Progress, task: TaskID) -> None:
        """Test payment encryption endpoint.
        
        Args:
            semaphore: Semaphore to limit concurrency
            payment_data: Test payment data
            progress: Progress bar
            task: Task ID for progress tracking
        """
        async with semaphore:
            start_time = time.time()
            url = f"{self.api_url}/payment/process"
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        json={"payment_data": payment_data},
                        timeout=10.0
                    )
                    
                    elapsed = time.time() - start_time
                    status_code = response.status_code
                    
                    self.results["payment_encryption"].append({
                        "elapsed": elapsed,
                        "status_code": status_code,
                        "success": 200 <= status_code < 300
                    })
            except Exception as e:
                elapsed = time.time() - start_time
                self.errors["payment_encryption"].append({
                    "elapsed": elapsed,
                    "error": str(e)
                })
            
            progress.update(task, advance=1)
    
    async def _test_fraud_detection(self, semaphore: asyncio.Semaphore, payment_data: Dict[str, Any],
                                 progress: Progress, task: TaskID) -> None:
        """Test fraud detection endpoint.
        
        Args:
            semaphore: Semaphore to limit concurrency
            payment_data: Test payment data
            progress: Progress bar
            task: Task ID for progress tracking
        """
        async with semaphore:
            start_time = time.time()
            url = f"{self.api_url}/payment/check-fraud"
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        url,
                        json=payment_data,
                        timeout=10.0
                    )
                    
                    elapsed = time.time() - start_time
                    status_code = response.status_code
                    
                    self.results["fraud_detection"].append({
                        "elapsed": elapsed,
                        "status_code": status_code,
                        "success": status_code in [200, 403]  # 403 is expected for high-risk transactions
                    })
            except Exception as e:
                elapsed = time.time() - start_time
                self.errors["fraud_detection"].append({
                    "elapsed": elapsed,
                    "error": str(e)
                })
            
            progress.update(task, advance=1)
    
    async def _test_key_rotation(self, semaphore: asyncio.Semaphore, progress: Progress, task: TaskID) -> None:
        """Test key rotation endpoint.
        
        Args:
            semaphore: Semaphore to limit concurrency
            progress: Progress bar
            task: Task ID for progress tracking
        """
        async with semaphore:
            start_time = time.time()
            url = f"{self.api_url}/admin/key-status"
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        url,
                        timeout=10.0
                    )
                    
                    elapsed = time.time() - start_time
                    status_code = response.status_code
                    
                    self.results["key_rotation"].append({
                        "elapsed": elapsed,
                        "status_code": status_code,
                        "success": 200 <= status_code < 300
                    })
            except Exception as e:
                elapsed = time.time() - start_time
                self.errors["key_rotation"].append({
                    "elapsed": elapsed,
                    "error": str(e)
                })
            
            progress.update(task, advance=1)
    
    def _calculate_statistics(self) -> Dict[str, Any]:
        """Calculate statistics from test results.
        
        Returns:
            Dictionary with statistics
        """
        stats = {}
        total_duration = self.end_time - self.start_time
        
        for feature, results in self.results.items():
            if not results:
                continue
                
            # Calculate response time statistics
            response_times = [r["elapsed"] for r in results]
            success_count = sum(1 for r in results if r["success"])
            
            feature_stats = {
                "requests": len(results),
                "success_rate": success_count / len(results) if results else 0,
                "errors": len(self.errors[feature]),
                "avg_response_time": statistics.mean(response_times) if response_times else 0,
                "min_response_time": min(response_times) if response_times else 0,
                "max_response_time": max(response_times) if response_times else 0,
                "p95_response_time": statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else None,
                "requests_per_second": len(results) / total_duration if total_duration > 0 else 0
            }
            
            # Add median if we have enough data points
            if len(response_times) >= 2:
                feature_stats["median_response_time"] = statistics.median(response_times)
            
            stats[feature] = feature_stats
        
        # Overall statistics
        total_requests = sum(len(results) for results in self.results.values())
        total_success = sum(sum(1 for r in results if r["success"]) for results in self.results.values())
        total_errors = sum(len(errors) for errors in self.errors.values())
        
        stats["overall"] = {
            "total_requests": total_requests,
            "total_success": total_success,
            "total_errors": total_errors,
            "success_rate": total_success / total_requests if total_requests > 0 else 0,
            "total_duration": total_duration,
            "requests_per_second": total_requests / total_duration if total_duration > 0 else 0
        }
        
        return stats
    
    def generate_report(self, stats: Dict[str, Any]) -> None:
        """Generate a report from test statistics.
        
        Args:
            stats: Dictionary with statistics
        """
        console.print("\n[bold green]Security Load Test Report[/bold green]")
        console.print(f"Total duration: {stats['overall']['total_duration']:.2f} seconds")
        console.print(f"Total requests: {stats['overall']['total_requests']}")
        console.print(f"Success rate: {stats['overall']['success_rate']*100:.2f}%")
        console.print(f"Requests per second: {stats['overall']['requests_per_second']:.2f}")
        
        # Create a table for feature-specific stats
        table = Table(title="Feature Performance")
        table.add_column("Feature")
        table.add_column("Requests")
        table.add_column("Success Rate")
        table.add_column("Avg Response Time (s)")
        table.add_column("P95 Response Time (s)")
        table.add_column("Requests/sec")
        
        for feature, feature_stats in stats.items():
            if feature == "overall":
                continue
                
            table.add_row(
                feature,
                str(feature_stats["requests"]),
                f"{feature_stats['success_rate']*100:.2f}%",
                f"{feature_stats['avg_response_time']:.4f}",
                f"{feature_stats['p95_response_time']:.4f}" if feature_stats['p95_response_time'] else "N/A",
                f"{feature_stats['requests_per_second']:.2f}"
            )
        
        console.print(table)
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"security_load_test_results_{timestamp}.json"
        with open(filename, "w") as f:
            json.dump(stats, f, indent=2)
        
        console.print(f"\nDetailed results saved to {filename}")


async def main():
    """Main function to run the load test."""
    parser = argparse.ArgumentParser(description="Load test WorthIt! API security features")
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API URL to test (default: {DEFAULT_API_URL})"
    )
    parser.add_argument(
        "-c", "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Number of concurrent requests (default: {DEFAULT_CONCURRENCY})"
    )
    parser.add_argument(
        "-n", "--requests",
        type=int,
        default=DEFAULT_REQUESTS,
        help=f"Total number of requests to make (default: {DEFAULT_REQUESTS})"
    )
    
    args = parser.parse_args()
    
    # Create and run the load tester
    load_tester = SecurityLoadTester(
        api_url=args.api_url,
        concurrency=args.concurrency,
        total_requests=args.requests
    )
    
    console.print(f"[bold]Starting security load test with {args.concurrency} concurrent users and {args.requests} total requests[/bold]")
    console.print(f"API URL: {args.api_url}")
    
    # Run the test
    stats = await load_tester.run_test()
    
    # Generate report
    load_tester.generate_report(stats)


if __name__ == "__main__":
    asyncio.run(main())