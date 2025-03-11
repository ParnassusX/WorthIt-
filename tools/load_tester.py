#!/usr/bin/env python
"""
Load Testing Script for WorthIt!

This script performs load testing on the WorthIt! API to ensure it can handle
expected traffic and identify performance bottlenecks before production deployment.
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
TEST_PRODUCT_URLS = [
    "https://www.amazon.com/dp/B08N5M7S6K",
    "https://www.amazon.com/dp/B08FC6MR62",
    "https://www.amazon.com/dp/B09V3KXJPB",
    "https://www.ebay.com/itm/123456789012",
    "https://www.ebay.com/itm/234567890123"
]


class LoadTester:
    """Load testing class for WorthIt! API."""
    
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
        self.results = []
        self.errors = []
        self.start_time = None
        self.end_time = None
    
    async def run_test(self) -> Dict[str, Any]:
        """Run the load test.
        
        Returns:
            Dictionary with test results
        """
        self.start_time = time.time()
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Running load test...", total=self.total_requests)
            
            # Create a semaphore to limit concurrency
            semaphore = asyncio.Semaphore(self.concurrency)
            
            # Create tasks
            tasks = []
            for i in range(self.total_requests):
                # Select a test URL (round-robin)
                test_url = TEST_PRODUCT_URLS[i % len(TEST_PRODUCT_URLS)]
                
                # Create and add the task
                tasks.append(self._make_request(semaphore, test_url, progress, task))
            
            # Run all tasks concurrently
            await asyncio.gather(*tasks)
        
        self.end_time = time.time()
        
        # Calculate statistics
        stats = self._calculate_statistics()
        
        return stats
    
    async def _make_request(self, semaphore: asyncio.Semaphore, product_url: str, 
                           progress: Progress, task_id: TaskID) -> None:
        """Make a single API request.
        
        Args:
            semaphore: Semaphore to limit concurrency
            product_url: URL of the product to analyze
            progress: Progress bar
            task_id: Task ID for progress tracking
        """
        async with semaphore:
            start_time = time.time()
            error = None
            status_code = None
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_url}/analyze?url={product_url}",
                        timeout=30  # 30 second timeout
                    ) as response:
                        status_code = response.status
                        if response.status == 200:
                            await response.json()
                        else:
                            error = f"HTTP {response.status}: {await response.text()}"
            except asyncio.TimeoutError:
                error = "Request timed out"
                status_code = 408
            except Exception as e:
                error = str(e)
                status_code = 500
            
            end_time = time.time()
            response_time = end_time - start_time
            
            # Record result
            result = {
                "response_time": response_time,
                "status_code": status_code,
                "error": error,
                "timestamp": datetime.now().isoformat(),
                "url": product_url
            }
            
            self.results.append(result)
            if error:
                self.errors.append(result)
            
            # Update progress
            progress.update(task_id, advance=1)
    
    def _calculate_statistics(self) -> Dict[str, Any]:
        """Calculate statistics from test results.
        
        Returns:
            Dictionary with statistics
        """
        if not self.results:
            return {"error": "No results collected"}
        
        # Extract response times
        response_times = [r["response_time"] for r in self.results]
        
        # Count status codes
        status_codes = {}
        for r in self.results:
            code = r["status_code"]
            if code in status_codes:
                status_codes[code] += 1
            else:
                status_codes[code] = 1
        
        # Calculate statistics
        stats = {
            "total_requests": len(self.results),
            "successful_requests": len([r for r in self.results if r["status_code"] == 200]),
            "failed_requests": len([r for r in self.results if r["status_code"] != 200]),
            "error_rate": len([r for r in self.results if r["status_code"] != 200]) / len(self.results),
            "total_time": self.end_time - self.start_time,
            "requests_per_second": len(self.results) / (self.end_time - self.start_time),
            "min_response_time": min(response_times),
            "max_response_time": max(response_times),
            "avg_response_time": statistics.mean(response_times),
            "median_response_time": statistics.median(response_times),
            "p90_response_time": sorted(response_times)[int(len(response_times) * 0.9)],
            "p95_response_time": sorted(response_times)[int(len(response_times) * 0.95)],
            "p99_response_time": sorted(response_times)[int(len(response_times) * 0.99)],
            "status_codes": status_codes,
            "concurrency": self.concurrency,
            "errors": self.errors[:10]  # Include first 10 errors
        }
        
        return stats
    
    def generate_report(self, stats: Dict[str, Any], output_file: Optional[str] = None) -> None:
        """Generate a report from test statistics.
        
        Args:
            stats: Dictionary with test statistics
            output_file: Optional file to save the report to
        """
        # Print summary table
        table = Table(title="Load Test Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Requests", str(stats["total_requests"]))
        table.add_row("Successful Requests", str(stats["successful_requests"]))
        table.add_row("Failed Requests", str(stats["failed_requests"]))
        table.add_row("Error Rate", f"{stats['error_rate']:.2%}")
        table.add_row("Total Time", f"{stats['total_time']:.2f} seconds")
        table.add_row("Requests Per Second", f"{stats['requests_per_second']:.2f}")
        table.add_row("Min Response Time", f"{stats['min_response_time']:.2f} seconds")
        table.add_row("Max Response Time", f"{stats['max_response_time']:.2f} seconds")
        table.add_row("Average Response Time", f"{stats['avg_response_time']:.2f} seconds")
        table.add_row("Median Response Time", f"{stats['median_response_time']:.2f} seconds")
        table.add_row("90th Percentile", f"{stats['p90_response_time']:.2f} seconds")
        table.add_row("95th Percentile", f"{stats['p95_response_time']:.2f} seconds")
        table.add_row("99th Percentile", f"{stats['p99_response_time']:.2f} seconds")
        
        console.print(table)
        
        # Print status code distribution
        status_table = Table(title="Status Code Distribution")
        status_table.add_column("Status Code", style="cyan")
        status_table.add_column("Count", style="green")
        status_table.add_column("Percentage", style="green")
        
        for code, count in stats["status_codes"].items():
            percentage = count / stats["total_requests"] * 100
            status_table.add_row(str(code), str(count), f"{percentage:.2f}%")
        
        console.print(status_table)
        
        # Print errors if any
        if stats["errors"]:
            console.print("\n[bold red]Sample Errors:[/bold red]")
            for i, error in enumerate(stats["errors"]):
                console.print(f"[red]{i+1}. {error['error']} (URL: {error['url']})[/red]")
        
        # Generate plots
        self._generate_plots(stats)
        
        # Save report to file if requested
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(stats, f, indent=2)
            console.print(f"\n[green]Report saved to {output_file}[/green]")
    
    def _generate_plots(self, stats: Dict[str, Any]) -> None:
        """Generate plots from test statistics.
        
        Args:
            stats: Dictionary with test statistics
        """
        try:
            # Response time histogram
            response_times = [r["response_time"] for r in self.results]
            
            plt.figure(figsize=(10, 6))
            plt.hist(response_times, bins=20, alpha=0.7, color='blue')
            plt.axvline(stats["avg_response_time"], color='red', linestyle='dashed', linewidth=1, label=f'Mean: {stats["avg_response_time"]:.2f}s')
            plt.axvline(stats["median_response_time"], color='green', linestyle='dashed', linewidth=1, label=f'Median: {stats["median_response_time"]:.2f}s')
            plt.axvline(stats["p95_response_time"], color='orange', linestyle='dashed', linewidth=1, label=f'95th: {stats["p95_response_time"]:.2f}s')
            plt.title('Response Time Distribution')
            plt.xlabel('Response Time (seconds)')
            plt.ylabel('Count')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig('response_time_histogram.png')
            
            # Status code pie chart
            labels = [f"HTTP {code}" for code in stats["status_codes"].keys()]
            sizes = list(stats["status_codes"].values())
            
            plt.figure(figsize=(8, 8))
            plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
            plt.axis('equal')
            plt.title('Status Code Distribution')
            plt.savefig('status_code_distribution.png')
            
            console.print("\n[green]Plots generated: response_time_histogram.png, status_code_distribution.png[/green]")
        except Exception as e:
            console.print(f"\n[red]Error generating plots: {str(e)}[/red]")


async def main():
    """Main function to run the load tester."""
    parser = argparse.ArgumentParser(description="Load Testing Tool for WorthIt! API")
    parser.add_argument("-c", "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Number of concurrent requests (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("-n", "--requests", type=int, default=DEFAULT_REQUESTS,
                        help=f"Total number of requests (default: {DEFAULT_REQUESTS})")
    parser.add_argument("-u", "--url", type=str, default=DEFAULT_API_URL,
                        help=f"API URL (default: {DEFAULT_API_URL})")
    parser.add_argument("-o", "--output", type=str, help="Output file for JSON report")
    args = parser.parse_args()
    
    console.print(f"[bold cyan]WorthIt! Load Tester[/bold cyan]")
    console.print(f"API URL: {args.url}")
    console.print(f"Concurrency: {args.concurrency}")
    console.print(f"Total Requests: {args.requests}\n")
    
    # Create and run load tester
    tester = LoadTester(args.url, args.concurrency, args.requests)
    stats = await tester.run_test()
    
    # Generate report
    tester.generate_report(stats, args.output)


if __name__ == "__main__":
    asyncio.run(main())