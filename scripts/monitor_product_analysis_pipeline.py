#!/usr/bin/env python
"""
Product Analysis Pipeline Monitoring Script

This script provides real-time monitoring of the product analysis pipeline by:
1. Tracking success rates of each component
2. Measuring response times at each stage
3. Detecting bottlenecks in the pipeline
4. Alerting on failures or performance degradation

Use this script to continuously monitor the health of the product analysis pipeline in production.
"""

import os
import sys
import json
import asyncio
import logging
import time
import datetime
from pathlib import Path
from dotenv import load_dotenv
import httpx
import statistics
from typing import Dict, List, Any, Optional

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import required components
from api.scraper import scrape_product
from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
from worker.queue import get_task_queue, get_task_by_id, initialize_queue
from worker.redis_manager import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/pipeline_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Metrics storage
metrics = {
    "api": {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "response_times": []
    },
    "scraper": {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "response_times": []
    },
    "sentiment": {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "response_times": []
    },
    "pros_cons": {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "response_times": []
    },
    "value_score": {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "response_times": []
    },
    "worker_queue": {
        "enqueued": 0,
        "processed": 0,
        "failed": 0,
        "processing_times": []
    },
    "end_to_end": {
        "calls": 0,
        "successes": 0,
        "failures": 0,
        "response_times": []
    }
}

async def monitor_api_endpoint(interval: int = 300):
    """Monitor the API endpoint for product analysis."""
    logger.info("Starting API endpoint monitoring")
    
    # Get API host from environment
    api_host = os.getenv("API_HOST", "https://worthit-app.netlify.app/api")
    api_url = f"{api_host}/analyze/product"
    
    # Test product URL - use a known stable product for consistent testing
    test_url = "https://www.amazon.com/dp/B08N5KWB9H"
    
    while True:
        try:
            start_time = time.time()
            metrics["api"]["calls"] += 1
            
            # Call the API endpoint
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    api_url,
                    json={"url": test_url}
                )
                
                end_time = time.time()
                response_time = end_time - start_time
                metrics["api"]["response_times"].append(response_time)
                
                if response.status_code == 200:
                    metrics["api"]["successes"] += 1
                    logger.info(f"API endpoint check successful. Response time: {response_time:.2f}s")
                else:
                    metrics["api"]["failures"] += 1
                    logger.error(f"API endpoint check failed with status code {response.status_code}")
                    logger.error(f"Error details: {response.text}")
        except Exception as e:
            metrics["api"]["failures"] += 1
            logger.error(f"Error monitoring API endpoint: {str(e)}")
        
        # Calculate success rate
        if metrics["api"]["calls"] > 0:
            success_rate = (metrics["api"]["successes"] / metrics["api"]["calls"]) * 100
            logger.info(f"API endpoint success rate: {success_rate:.2f}%")
        
        # Calculate average response time
        if metrics["api"]["response_times"]:
            avg_response_time = statistics.mean(metrics["api"]["response_times"][-10:])
            logger.info(f"API endpoint average response time (last 10 calls): {avg_response_time:.2f}s")
        
        # Wait for the next check
        await asyncio.sleep(interval)

async def monitor_worker_queue(interval: int = 60):
    """Monitor the worker queue for task processing."""
    logger.info("Starting worker queue monitoring")
    
    # Initialize queue
    try:
        await initialize_queue()
        logger.info("Successfully initialized queue for monitoring")
    except Exception as e:
        logger.error(f"Failed to initialize queue for monitoring: {str(e)}")
        return
    
    # Get Redis client
    redis = await get_redis_client()
    
    while True:
        try:
            # Get queue statistics
            pending_tasks = await redis.llen("worthit_tasks")
            processing_tasks = await redis.scard("worthit_processing")
            completed_tasks = await redis.scard("worthit_completed")
            failed_tasks = await redis.scard("worthit_failed")
            
            logger.info(f"Queue statistics: Pending={pending_tasks}, Processing={processing_tasks}, Completed={completed_tasks}, Failed={failed_tasks}")
            
            # Check processing times for recently completed tasks
            completed_task_ids = await redis.smembers("worthit_completed")
            if completed_task_ids:
                # Only check the 5 most recent tasks
                recent_task_ids = list(completed_task_ids)[-5:]
                for task_id in recent_task_ids:
                    task_data = await get_task_by_id(task_id)
                    if task_data and task_data.get("start_time") and task_data.get("end_time"):
                        processing_time = task_data["end_time"] - task_data["start_time"]
                        metrics["worker_queue"]["processing_times"].append(processing_time)
                        metrics["worker_queue"]["processed"] += 1
            
            # Calculate average processing time
            if metrics["worker_queue"]["processing_times"]:
                avg_processing_time = statistics.mean(metrics["worker_queue"]["processing_times"][-10:])
                logger.info(f"Average task processing time (last 10 tasks): {avg_processing_time:.2f}s")
            
            # Check for stuck tasks (in processing state for too long)
            processing_task_ids = await redis.smembers("worthit_processing")
            current_time = time.time()
            for task_id in processing_task_ids:
                task_data = await get_task_by_id(task_id)
                if task_data and task_data.get("start_time"):
                    processing_duration = current_time - task_data["start_time"]
                    if processing_duration > 300:  # 5 minutes
                        logger.warning(f"Task {task_id} has been processing for {processing_duration:.2f}s (>5 minutes)")
        except Exception as e:
            logger.error(f"Error monitoring worker queue: {str(e)}")
        
        # Wait for the next check
        await asyncio.sleep(interval)

async def monitor_component_health(interval: int = 180):
    """Monitor the health of individual components in the pipeline."""
    logger.info("Starting component health monitoring")
    
    # Test product URL
    test_url = "https://www.amazon.com/dp/B08N5KWB9H"
    
    while True:
        # Monitor scraper
        try:
            start_time = time.time()
            metrics["scraper"]["calls"] += 1
            
            product_data = scrape_product(test_url)
            
            end_time = time.time()
            response_time = end_time - start_time
            metrics["scraper"]["response_times"].append(response_time)
            
            if product_data:
                metrics["scraper"]["successes"] += 1
                logger.info(f"Scraper check successful. Response time: {response_time:.2f}s")
                
                # Monitor sentiment analysis
                if product_data.get("reviews"):
                    reviews = product_data.get("reviews", [])[:5]  # Use first 5 reviews
                    
                    try:
                        start_time = time.time()
                        metrics["sentiment"]["calls"] += 1
                        
                        sentiment = analyze_sentiment(reviews)
                        
                        end_time = time.time()
                        response_time = end_time - start_time
                        metrics["sentiment"]["response_times"].append(response_time)
                        
                        if sentiment is not None:
                            metrics["sentiment"]["successes"] += 1
                            logger.info(f"Sentiment analysis check successful. Response time: {response_time:.2f}s")
                            
                            # Monitor pros/cons extraction
                            try:
                                start_time = time.time()
                                metrics["pros_cons"]["calls"] += 1
                                
                                pros, cons = extract_product_pros_cons(reviews)
                                
                                end_time = time.time()
                                response_time = end_time - start_time
                                metrics["pros_cons"]["response_times"].append(response_time)
                                
                                if pros is not None and cons is not None:
                                    metrics["pros_cons"]["successes"] += 1
                                    logger.info(f"Pros/cons extraction check successful. Response time: {response_time:.2f}s")
                                else:
                                    metrics["pros_cons"]["failures"] += 1
                                    logger.error("Pros/cons extraction check failed: No pros/cons returned")
                            except Exception as e:
                                metrics["pros_cons"]["failures"] += 1
                                logger.error(f"Error in pros/cons extraction check: {str(e)}")
                            
                            # Monitor value score calculation
                            try:
                                start_time = time.time()
                                metrics["value_score"]["calls"] += 1
                                
                                price_str = product_data.get("price", "").replace("$", "").split(" ")[0]
                                if price_str and price_str.replace(".", "").isdigit():
                                    price = float(price_str)
                                    value_score = get_value_score(sentiment, price)
                                    
                                    end_time = time.time()
                                    response_time = end_time - start_time
                                    metrics["value_score"]["response_times"].append(response_time)
                                    
                                    if value_score is not None:
                                        metrics["value_score"]["successes"] += 1
                                        logger.info(f"Value score calculation check successful. Response time: {response_time:.2f}s")
                                    else:
                                        metrics["value_score"]["failures"] += 1
                                        logger.error("Value score calculation check failed: No value score returned")
                                else:
                                    metrics["value_score"]["failures"] += 1
                                    logger.error("Value score calculation check failed: Invalid price format")
                            except Exception as e:
                                metrics["value_score"]["failures"] += 1
                                logger.error(f"Error in value score calculation check: {str(e)}")
                        else:
                            metrics["sentiment"]["failures"] += 1
                            logger.error("Sentiment analysis check failed: No sentiment returned")
                    except Exception as e:
                        metrics["sentiment"]["failures"] += 1
                        logger.error(f"Error in sentiment analysis check: {str(e)}")
            else:
                metrics["scraper"]["failures"] += 1
                logger.error("Scraper check failed: No product data returned")
        except Exception as e:
            metrics["scraper"]["failures"] += 1
            logger.error(f"Error in scraper check: {str(e)}")
        
        # Generate component health report
        logger.info("\n===== Component Health Report =====")
        for component, data in metrics.items():
            if component != "worker_queue" and component != "end_to_end":
                if data["calls"] > 0:
                    success_rate = (data["successes"] / data["calls"]) * 100
                    logger.info(f"{component.upper()}: Success rate: {success_rate:.2f}% ({data['successes']}/{data['calls']})")
                    
                    if data["response_times"]:
                        avg_response_time = statistics.mean(data["response_times"][-10:])
                        logger.info(f"{component.upper()}: Average response time (last 10 calls): {avg_response_time:.2f}s")
        
        # Wait for the next check
        await asyncio.sleep(interval)

async def generate_daily_report():
    """Generate a daily report of pipeline performance."""
    logger.info("Starting daily report generation")
    
    while True:
        # Wait until midnight
        now = datetime.datetime.now()
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        seconds_until_midnight = (midnight - now).total_seconds()
        await asyncio.sleep(seconds_until_midnight)