#!/usr/bin/env python
"""
Product Analysis Integration Verification Script

This script verifies that all components of the product analysis pipeline are properly integrated
and communicating with each other. It tests the complete flow from user input to final response,
ensuring that data is correctly passed between components and that the user receives the expected output.

Use this script to verify the integration of the product analysis pipeline in production.
"""

import os
import sys
import json
import asyncio
import logging
import time
from pathlib import Path
from dotenv import load_dotenv
import httpx
from typing import Dict, Any, Optional

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent.parent))

# Import required components
from api.scraper import scrape_product
from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
from worker.queue import enqueue_task, get_task_by_id, initialize_queue
from worker.tasks import process_product_analysis_task
from bot.bot import format_analysis_response, get_bot_instance

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def verify_bot_to_api_integration():
    """Verify integration between the bot and API components."""
    logger.info("\n===== Verifying Bot to API Integration =====\n")
    
    # Get API host from environment
    api_host = os.getenv("API_HOST", "https://worthit-app.netlify.app/api")
    
    try:
        # Create a mock update to simulate user input
        from unittest.mock import AsyncMock, MagicMock
        from telegram import Update, Message, Chat, User
        
        # Create mock objects
        update = MagicMock(spec=Update)
        message = MagicMock(spec=Message)
        chat = MagicMock(spec=Chat)
        user = MagicMock(spec=User)
        
        # Configure the mock objects
        chat.id = 123456789
        user.id = 987654321
        user.first_name = "Test User"
        message.chat = chat
        message.from_user = user
        message.text = "https://www.amazon.com/dp/B08N5KWB9H"
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_chat = chat
        update.effective_user = user
        
        # Import the analyze_product_url function
        from bot.bot import analyze_product_url
        
        # Set testing environment variable to true to use direct API call
        os.environ['TESTING'] = 'true'
        
        # Call the analyze_product_url function
        logger.info("Calling analyze_product_url function with test URL...")
        result = await analyze_product_url(update, message.text)
        
        # Check if the function returned a result
        if result:
            logger.info("✅ Bot to API integration successful")
            logger.info(f"Result: {json.dumps(result, indent=2) if isinstance(result, dict) else result}")
            
            # Verify that the message was sent to the user
            if message.reply_text.called:
                logger.info("✅ Bot successfully sent response to user")
                return True
            else:
                logger.warning("⚠️ Bot did not send response to user")
                return False
        else:
            logger.error("❌ Bot to API integration failed: No result returned")
            return False
    except Exception as e:
        logger.error(f"❌ Error verifying Bot to API integration: {str(e)}")
        return False
    finally:
        # Reset testing environment variable
        os.environ['TESTING'] = 'false'

async def verify_api_to_worker_integration():
    """Verify integration between the API and worker components."""
    logger.info("\n===== Verifying API to Worker Integration =====\n")
    
    try:
        # Initialize queue
        await initialize_queue()
        logger.info("✅ Successfully initialized queue")
        
        # Create a test task
        test_url = "https://www.amazon.com/dp/B08N5KWB9H"
        task = {
            'type': 'product_analysis',
            'data': {
                'url': test_url,
                'chat_id': 123456789  # Test chat ID
            },
            'status': 'pending'
        }
        
        # Enqueue the task
        logger.info("Enqueueing test task...")
        task_id = await enqueue_task(task)
        
        if not task_id:
            logger.error("❌ API to Worker integration failed: Could not enqueue task")
            return False
            
        logger.info(f"✅ Successfully enqueued task with ID: {task_id}")
        
        # Wait for the task to be processed
        logger.info("Waiting for task to be processed...")
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
            logger.info(f"✅ API to Worker integration successful: Task completed")
            logger.info(f"Task result: {json.dumps(task_data.get('result', {}), indent=2)}")
            return True
        else:
            logger.warning(f"⚠️ API to Worker integration incomplete: Task did not complete within {max_wait_time} seconds")
            return False
    except Exception as e:
        logger.error(f"❌ Error verifying API to Worker integration: {str(e)}")
        return False

async def verify_worker_to_bot_integration():
    """Verify integration between the worker and bot components."""
    logger.info("\n===== Verifying Worker to Bot Integration =====\n")
    
    try:
        # Mock the bot instance
        from unittest.mock import AsyncMock, MagicMock
        bot_instance = MagicMock()
        bot_instance.send_message = AsyncMock()
        
        # Mock the get_bot_instance function
        with MagicMock() as mock_get_bot:
            mock_get_bot.return_value = bot_instance
            
            # Create a test task data
            task_data = {
                'url': 'https://www.amazon.com/dp/B08N5KWB9H',
                'chat_id': 123456789  # Test chat ID
            }
            
            # Process the task
            logger.info("Processing test task...")
            await process_product_analysis_task(task_data)
            
            # Verify that the bot sent a message with the analysis
            if bot_instance.send_message.called:
                logger.info("✅ Worker to Bot integration successful: Bot sent message to user")
                return True
            else:
                logger.error("❌ Worker to Bot integration failed: Bot did not send message to user")
                return False
    except Exception as e:
        logger.error(f"❌ Error verifying Worker to Bot integration: {str(e)}")
        return False

async def verify_end_to_end_integration():
    """Verify end-to-end integration of the product analysis pipeline."""
    logger.info("\n===== Verifying End-to-End Integration =====\n")
    
    try:
        # Create a mock update to simulate user input
        from unittest.mock import AsyncMock, MagicMock
        from telegram import Update, Message, Chat, User
        
        # Create mock objects
        update = MagicMock(spec=Update)
        message = MagicMock(spec=Message)
        chat = MagicMock(spec=Chat)
        user = MagicMock(spec=User)
        
        # Configure the mock objects
        chat.id = 123456789
        user.id = 987654321
        user.first_name = "Test User"
        message.chat = chat
        message.from_user = user
        message.text = "https://www.amazon.com/dp/B08N5KWB9H"
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_chat = chat
        update.effective_user = user
        
        # Import the analyze_product_url function
        from bot.bot import analyze_product_url
        
        # Set testing environment variable to false to use worker queue
        os.environ['TESTING'] = 'false'
        
        # Call the analyze_product_url function
        logger.info("Calling analyze_product_url function with test URL...")
        result = await analyze_product_url(update, message.text)
        
        # Check if the function returned a result
        if result and isinstance(result, dict) and result.get('status') == 'processing':
            logger.info("✅ Task successfully enqueued for processing")
            
            # Wait for the task to be processed
            logger.info("Waiting for task to be processed...")
            max_wait_time = 30  # seconds
            start_time = time.time()
            
            # Check if the message was sent to the user
            while time.time() - start_time < max_wait_time:
                if message.reply_text.call_count >= 2:  # Initial acknowledgment + result
                    logger.info("✅ End-to-End integration successful: User received analysis result")
                    return True
                    
                # Wait before checking again
                await asyncio.sleep(1)
            
            logger.warning(f"⚠️ End-to-End integration incomplete: User did not receive analysis result within {max_wait_time} seconds")
            return False
        else:
            logger.error("❌ End-to-End integration failed: Task was not enqueued for processing")
            return False
    except Exception as e:
        logger.error(f"❌ Error verifying End-to-End integration: {str(e)}")
        return False
    finally:
        # Reset testing environment variable
        os.environ['TESTING'] = 'true'

async def verify_integration():
    """Verify the integration of all components in the product analysis pipeline."""
    logger.info("\n===== WorthIt! Product Analysis Integration Verification =====\n")
    
    # Load environment variables
    load_dotenv()
    
    # Verify Bot to API integration
    bot_to_api = await verify_bot_to_api_integration()
    
    # Verify API to Worker integration
    api_to_worker = await verify_api_to_worker_integration()
    
    # Verify Worker to Bot integration
    worker_to_bot = await verify_worker_to_bot_integration()
    
    # Verify End-to-End integration
    end_to_end = await verify_end_to_end_integration()
    
    # Print summary
    logger.info("\n===== Integration Verification Summary =====\n")
    logger.info(f"Bot to API Integration: {'✅ PASSED' if bot_to_api else '❌ FAILED'}")
    logger.info(f"API to Worker Integration: {'✅ PASSED' if api_to_worker else '❌ FAILED'}")
    logger.info(f"Worker to Bot Integration: {'✅ PASSED' if worker_to_bot else '❌ FAILED'}")
    logger.info(f"End-to-End Integration: {'✅ PASSED' if end_to_end else '❌ FAILED'}")
    
    # Overall result
    if bot_to_api and api_to_worker and worker_to_bot and end_to_end:
        logger.info("\n✅ INTEGRATION VERIFICATION PASSED: All components are properly integrated")
        return True
    else:
        logger.error("\n❌ INTEGRATION VERIFICATION FAILED: Some components are not properly integrated")
        return False

async def main():
    """Main entry point for the script."""
    success = await verify_integration()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())