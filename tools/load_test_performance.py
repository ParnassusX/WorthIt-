#!/usr/bin/env python
"""
Performance Load Testing Script for WorthIt!

This script performs load testing with a focus on performance bottlenecks
and optimization opportunities in the WorthIt! API to ensure it can handle
expected production traffic levels.
"""

import os
import sys
import time
import json
import asyncio
import argparse
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

import httpx
import aiohttp
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console
from rich.progress import Progress, TaskID
from rich.table import Table
from rich.panel import Panel

# Load environment variables
env_path = Path(__file__).parent.parent / ".env.test"
if env_path.exists():
    load_dotenv(env_path)
else:
    print("Warning: .env.test file not found, using system environment variables")

# Initialize console for rich output
console = Console()

# Default settings
DEFAULT_CONCURRENCY = 20
DEFAULT_REQUESTS = 200
DEFAULT_RAMP_UP = 5  # seconds
DEFAULT_API_URL = os.getenv("API_HOST", "https://worthit-app.netlify.app/api")
TEST_PRODUCT_URLS = [
    "https://www.amazon.com/dp/B08N5M7S6K",
    "https://www.amazon.com/dp/B08FC6MR62",
    "https://www.amazon.com/dp/B09V3KXJPB",
    "https://www.ebay.com/itm/123456789012",
    "https://www.ebay.com/itm/234567890123"
]

# Test endpoints
TEST_ENDPOINTS = [
    {"name": "product_analysis", "path": "/analyze", "method": "POST"},
    {"name": "health_check", "path": "/health", "method": "GET"},
    {"name": "image_processing", "path": "/process-image", "method": "POST"},
    {"name": "payment_processing", "path": "/payment/process", "method": "POST"}
]


class PerformanceLoadTester:
    """Performance-focused load testing class for WorthIt! API."""
    
    def __init__(self, api_url: str, concurrency: int, total_requests: int, ramp_up: int = DEFAULT_RAMP_UP):
        """Initialize the performance load tester.
        
        Args:
            api_url: Base URL of the API to test
            concurrency: Number of concurrent requests
            total_requests: Total number of requests to make
            ramp_up: Ramp-up time in seconds (gradually increase load)
        """
        self.api_url = api_url.rstrip('/')
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.ramp_up = ramp_up
        self.results = {endpoint["name"]: [] for endpoint in TEST_ENDPOINTS}
        self.errors = {endpoint["name"]: [] for endpoint in TEST_ENDPOINTS}
        self.start_time = None
        self.end_time = None
        self.performance_metrics = {}
        self.bottlenecks = []
        
        # Performance thresholds (in seconds)
        self.thresholds = {
            "product_analysis": {"p95": 3.0, "p99": 5.0},
            "health_check": {"p95": 0.5, "p99": 1.0},
            "image_processing": {"p95": 2.0, "p99": 4.0},
            "payment_processing": {"p95": 1.5, "p99": 3.0}
        }
    
    async def run_test(self) -> Dict[str, Any]:
        """Run the performance load test.
        
        Returns:
            Dictionary with test results and performance analysis
        """
        self.start_time = time.time()
        
        with Progress() as progress:
            # Create tasks for each endpoint
            tasks = {}
            for endpoint in TEST_ENDPOINTS:
                tasks[endpoint["name"]] = progress.add_task(
                    f"[cyan]Testing {endpoint['name']}...", 
                    total=self.total_requests
                )
            
            # Create a semaphore to limit concurrency
            semaphore = asyncio.Semaphore(self.concurrency)
            
            # Create test tasks
            all_tasks = []
            for endpoint in TEST_ENDPOINTS:
                endpoint_tasks = []
                
                # Calculate requests per endpoint (distribute evenly)
                requests_per_endpoint = self.total_requests // len(TEST_ENDPOINTS)
                
                for i in range(requests_per_endpoint):
                    # Select a test URL (round-robin) for endpoints that need it
                    test_url = TEST_PRODUCT_URLS[i % len(TEST_PRODUCT_URLS)]
                    
                    # Add delay for ramp-up if enabled
                    delay = 0
                    if self.ramp_up > 0:
                        delay = (i / requests_per_endpoint) * self.ramp_up
                    
                    # Create and add the task
                    endpoint_tasks.append(self._make_request(
                        semaphore, 
                        endpoint, 
                        test_url, 
                        progress, 
                        tasks[endpoint["name"]],
                        delay
                    ))
                
                all_tasks.extend(endpoint_tasks)
            
            # Run all tasks concurrently
            await asyncio.gather(*all_tasks)
        
        self.end_time = time.time()
        
        # Calculate statistics and identify bottlenecks
        self._analyze_performance()
        
        # Generate performance report
        return {
            "test_summary": {
                "total_requests": self.total_requests,
                "concurrency": self.concurrency,
                "duration": self.end_time - self.start_time,
                "requests_per_second": self.total_requests / (self.end_time - self.start_time),
                "timestamp": datetime.now().isoformat()
            },
            "endpoint_metrics": self.performance_metrics,
            "bottlenecks": self.bottlenecks,
            "optimization_recommendations": self._generate_recommendations(),
            "errors": {k: len(v) for k, v in self.errors.items()}
        }
    
    async def _make_request(self, semaphore: asyncio.Semaphore, endpoint: Dict[str, str], 
                         test_url: str, progress: Progress, task_id: TaskID, delay: float = 0) -> None:
        """Make a single API request for performance testing.
        
        Args:
            semaphore: Semaphore to limit concurrency
            endpoint: Endpoint configuration
            test_url: Product URL to analyze (for endpoints that need it)
            progress: Progress bar
            task_id: Task ID for progress tracking
            delay: Optional delay for ramp-up
        """
        # Apply delay if needed for ramp-up
        if delay > 0:
            await asyncio.sleep(delay)
        
        async with semaphore:
            start_time = time.time()
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Prepare request based on endpoint method
                    if endpoint["method"] == "GET":
                        response = await client.get(
                            f"{self.api_url}{endpoint['path']}",
                            headers={"Content-Type": "application/json"}
                        )
                    elif endpoint["method"] == "POST":
                        # Prepare payload based on endpoint
                        if endpoint["name"] == "product_analysis":
                            payload = {"url": test_url}
                        elif endpoint["name"] == "image_processing":
                            # Dummy image processing request
                            payload = {"url": test_url, "operations": ["resize", "optimize"]}
                        elif endpoint["name"] == "payment_processing":
                            # Dummy payment processing request
                            payload = {
                                "amount": 99.99,
                                "currency": "USD",
                                "payment_method_id": f"pm_{int(time.time())}",
                                "customer_id": f"cust_{int(time.time())}"
                            }
                        else:
                            payload = {}
                        
                        response = await client.post(
                            f"{self.api_url}{endpoint['path']}",
                            json=payload,
                            headers={"Content-Type": "application/json"}
                        )
                    else:
                        raise ValueError(f"Unsupported method: {endpoint['method']}")
                    
                    end_time = time.time()
                    duration = end_time - start_time
                    
                    # Record detailed metrics
                    result = {
                        "status_code": response.status_code,
                        "duration": duration,
                        "success": 200 <= response.status_code < 300,
                        "response_size": len(response.content),
                        "timestamp": time.time()
                    }
                    
                    # Add to results
                    self.results[endpoint["name"]].append(result)
                    
            except Exception as e:
                end_time = time.time()
                duration = end_time - start_time
                
                # Record error
                error = {
                    "error": str(e),
                    "duration": duration,
                    "timestamp": time.time()
                }
                
                self.errors[endpoint["name"]].append(error)
                
                # Also add to results as failed request
                self.results[endpoint["name"]].append({
                    "status_code": 0,
                    "duration": duration,
                    "success": False,
                    "error": str(e),
                    "timestamp": time.time()
                })
            
            finally:
                progress.update(task_id, advance=1)
    
    def _analyze_performance(self) -> None:
        """Analyze performance metrics and identify bottlenecks."""
        for endpoint_name, results in self.results.items():
            if not results:
                continue
                
            # Extract response times
            response_times = [r["duration"] for r in results]
            success_times = [r["duration"] for r in results if r["success"]]
            
            # Calculate success rate
            success_count = sum(1 for r in results if r["success"])
            success_rate = (success_count / len(results)) * 100 if results else 0
            
            # Calculate percentiles
            if response_times:
                p50 = statistics.median(response_times)
                p95 = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max(response_times)
                p99 = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else max(response_times)
            else:
                p50 = p95 = p99 = 0
            
            # Calculate throughput
            if self.start_time and self.end_time:
                throughput = len(results) / (self.end_time - self.start_time)
            else:
                throughput = 0
            
            # Store metrics
            self.performance_metrics[endpoint_name] = {
                "total_requests": len(results),
                "successful_requests": success_count,
                "success_rate": success_rate,
                "response_time": {
                    "min": min(response_times) if response_times else 0,
                    "max": max(response_times) if response_times else 0,
                    "mean": statistics.mean(response_times) if response_times else 0,
                    "median": p50,
                    "p95": p95,
                    "p99": p99
                },
                "throughput": throughput,
                "errors": len(self.errors[endpoint_name])
            }
            
            # Check for bottlenecks
            threshold = self.thresholds.get(endpoint_name, {"p95": 2.0, "p99": 4.0})
            
            if p95 > threshold["p95"]:
                self.bottlenecks.append({
                    "endpoint": endpoint_name,
                    "metric": "p95",
                    "value": p95,
                    "threshold": threshold["p95"],
                    "severity": "medium" if p95 < threshold["p99"] else "high"
                })
                
            if p99 > threshold["p99"]:
                self.bottlenecks.append({
                    "endpoint": endpoint_name,
                    "metric": "p99",
                    "value": p99,
                    "threshold": threshold["p99"],
                    "severity": "high"
                })
                
            # Check for high error rate
            if success_rate < 95:
                self.bottlenecks.append({
                    "endpoint": endpoint_name,
                    "metric": "success_rate",
                    "value": success_rate,
                    "threshold": 95,
                    "severity": "high" if success_rate < 90 else "medium"
                })
    
    def _generate_recommendations(self) -> List[Dict[str, str]]:
        """Generate optimization recommendations based on performance analysis.
        
        Returns:
            List of recommendation dictionaries
        """
        recommendations = []
        
        # Check for specific bottlenecks and generate recommendations
        for bottleneck in self.bottlenecks:
            endpoint = bottleneck["endpoint"]
            metric = bottleneck["metric"]
            severity = bottleneck["severity"]
            
            if endpoint == "analyze_product":
                recommendations.append({
                    "endpoint": endpoint,
                    "recommendation": "Consider implementing caching for product analysis results",
                    "impact": "high"
                })