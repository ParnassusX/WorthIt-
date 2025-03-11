#!/usr/bin/env python
"""
Product Analysis Pipeline Verification Script

This script verifies the complete end-to-end product analysis pipeline by:
1. Testing the direct API call path
2. Testing the worker queue path
3. Verifying that results are properly returned to users
4. Checking all integration points between components

Use this script to verify that the entire pipeline is working correctly in production.
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
import httpx
import time

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import required components
from api.scraper import scrape_product
from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
from worker.queue import enqueue_task, get_task_by_id, initialize_queue
from worker.tasks import process_product_analysis_task
from bot.bot import format_analysis_response

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_direct_api_path():
    """Test the direct API call path for product analysis."""
    logger.info("\n===== Testing Direct API Path =====\n")
    
    # Test product URL
    test_url = "https://www.amazon.com/dp/B08N5KWB9H"
    logger.info(f"Testing product analysis for URL: {test_url}")
    
    try:
        # Step 1: Test product scraping
        logger.info("Step 1: Testing product scraping...")
        product_data = scrape_product(test_url)
        
        if not product_data:
            logger.error("❌ Failed to scrape product data")
            return False
            
        logger.info(f"✅ Successfully scraped product data")
        logger.info(f"   Title: {product_data.get('title')}")
        logger.info(f"   Price: {product_data.get('price')}")
        reviews = product_data.get('reviews', [])
        logger.info(f"   Found {len(reviews)} reviews")
        
        # Step 2: Test sentiment analysis
        if reviews:
            logger.info("\nStep 2: Testing sentiment analysis...")
            # Only use first 5 reviews for faster testing
            test_reviews = reviews[:5]
            sentiment = analyze_sentiment(test_reviews)
            logger.info(f"✅ Successfully analyzed sentiment: {sentiment}")
            
            # Step 3: Test pros/cons extraction
            logger.info("\nStep 3: Testing pros/cons extraction...")
            pros, cons = extract_product_pros_cons(test_reviews)
            logger.info(f"✅ Successfully extracted pros/cons")
            logger.info(f"   Pros: {pros}")
            logger.info(f"   Cons: {cons}")
            
            # Step 4: Test value score calculation
            logger.info("\nStep 4: Testing value score calculation...")
            price_str = product_data.get('price', '').replace('$', '').split(' ')[0]
            if price_str and price_str.replace('.', '').isdigit():
                price = float(price_str)
                value_score = get_value_score(sentiment, price)
                logger.info(f"✅ Successfully calculated value score: {value_score}")
                
                # Step 5: Test response formatting
                logger.info("\nStep 5: Testing response formatting...")
                analysis_result = {
                    "title": product_data.get('title'),
                    "price": product_data.get('price'),
                    "value_score": value_score,
                    "analysis": {
                        "pros": pros,
                        "cons": cons
                    }
                }
                
                formatted_response = format_analysis_response(analysis_result)
                logger.info(f"✅ Successfully formatted response")
                logger.info(f"Response preview: {formatted_response[:100]}...")
                
                return True
            else:
                logger.warning("⚠️ Could not calculate value score: invalid price format")
                return False
        else:
            logger.warning("⚠️ No reviews found for sentiment analysis")
            return False
    except Exception as e:
        logger.error(f"❌ Error in direct API path: {str(e)}")
        return False

async def test_worker_queue_path():
    """Test the worker queue path for product analysis."""
    logger.info("\n===== Testing Worker Queue Path =====\n")
    
    # Initialize queue
    try:
        await initialize_queue()
        logger.info("✅ Successfully initialized queue")
    except Exception as e:
        logger.error(f"❌ Failed to initialize queue: {str(e)}")
        return False
    
    # Test product URL
    test_url = "https://www.amazon.com/dp/B08N5KWB9H"
    logger.info(f"Testing product analysis for URL: {test_url}")
    
    try:
        # Step 1: Create and enqueue task
        logger.info("Step 1: Creating and enqueueing task...")
        task = {
            'type': 'product_analysis',
            'data': {
                'url': test_url,
                'chat_id': 123456789  # Test chat ID
            },
            'status': 'pending'
        }
        
        task_id = await enqueue_task(task)
        if not task_id:
            logger.error("❌ Failed to enqueue task")
            return False
            
        logger.info(f"✅ Successfully enqueued task with ID: {task_id}")
        
        # Step 2: Wait for task to be processed
        logger.info("\nStep 2: Waiting for task to be processed...")
        max_wait_time = 30  # seconds
        start_time = time.time()
        task_completed = False
        
        while time.time() - start_time < max_wait_time:
            # Check task status
            task_data = await get_task_by_id(task_id)
            if task_data and task_data.get('status') == 'completed':
                task_completed = True
                break
                
            # Wait before checking again
            await asyncio.sleep(1)
        
        if task_completed:
            logger.info(f"✅ Task completed successfully")
            logger.info(f"Task result: {json.dumps(task_data.get('result', {}), indent=2)}")
            return True
        else:
            logger.warning(f"⚠️ Task did not complete within {max_wait_time} seconds")
            return False
    except Exception as e:
        logger.error(f"❌ Error in worker queue path: {str(e)}")
        return False

async def test_api_endpoint():
    """Test the API endpoint for product analysis."""
    logger.info("\n===== Testing API Endpoint =====\n")
    
    # Get API host from environment
    api_host = os.getenv("API_HOST", "https://worthit-app.netlify.app/api")
    api_url = f"{api_host}/analyze/product"
    
    # Test product URL
    test_url = "https://www.amazon.com/dp/B08N5KWB9H"
    logger.info(f"Testing API endpoint: {api_url}")
    logger.info(f"Testing product URL: {test_url}")
    
    try:
        # Call the API endpoint
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                json={"url": test_url}
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ API endpoint returned successful response")
                logger.info(f"Response: {json.dumps(result, indent=2)}")
                return True
            else:
                logger.error(f"❌ API endpoint returned error: {response.status_code}")
                logger.error(f"Error details: {response.text}")
                return False
    except Exception as e:
        logger.error(f"❌ Error calling API endpoint: {str(e)}")
        return False

async def verify_pipeline():
    """Verify the complete product analysis pipeline."""
    logger.info("\n===== WorthIt! Product Analysis Pipeline Verification =====\n")
    
    # Load environment variables
    load_dotenv()
    
    # Test direct API path
    direct_api_success = await test_direct_api_path()
    
    # Test worker queue path
    worker_queue_success = await test_worker_queue_path()
    
    # Test API endpoint
    api_endpoint_success = await test_api_endpoint()
    
    # Print summary
    logger.info("\n===== Pipeline Verification Summary =====\n")
    logger.info(f"Direct API Path: {'✅ PASSED' if direct_api_success else '❌ FAILED'}")
    logger.info(f"Worker Queue Path: {'✅ PASSED' if worker_queue_success else '❌ FAILED'}")
    logger.info(f"API Endpoint: {'✅ PASSED' if api_endpoint_success else '❌ FAILED'}")
    
    # Overall result
    if direct_api_success and worker_queue_success and api_endpoint_success:
        logger.info("\n✅ PIPELINE VERIFICATION PASSED: All components are working correctly")
        return True
    else:
        logger.error("\n❌ PIPELINE VERIFICATION FAILED: Some components are not working correctly")
        return False

async def main():
    """Main entry point for the script."""
    success = await verify_pipeline()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())