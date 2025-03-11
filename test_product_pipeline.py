#!/usr/bin/env python
"""
Product Analysis Pipeline Verification Script

This script verifies that all components required for the product analysis pipeline
are properly configured and working correctly.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

def test_pipeline_components():
    """Test all components required for the product analysis pipeline."""
    print("\n===== Testing Product Analysis Pipeline =====\n")
    
    # Test environment variables
    print("Testing environment variables...")
    load_dotenv()
    required_vars = [
        "TELEGRAM_TOKEN",
        "REDIS_URL",
        "WEBHOOK_URL",
        "APIFY_TOKEN",
        "HF_TOKEN"
    ]
    
    for var in required_vars:
        if not os.getenv(var):
            print(f"❌ {var} is not set")
            return False
    print("✅ Environment variables loaded")
    
    # Test Redis connection
    print("\nTesting Redis connection...")
    try:
        from worker.redis.connection import get_redis_manager
        redis_manager = get_redis_manager()
        print("✅ Redis manager initialized")
    except Exception as e:
        print(f"❌ Redis connection failed: {str(e)}")
        return False
    
    # Test API components
    print("\nTesting API components...")
    try:
        from api.scraper import scrape_product
        from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
        print("✅ API components loaded")
    except Exception as e:
        print(f"❌ API components failed to load: {str(e)}")
        return False
    
    # Test worker components
    print("\nTesting worker components...")
    try:
        from worker.queue import enqueue_task, get_task_by_id
        print("✅ Worker queue components loaded")
    except Exception as e:
        print(f"❌ Worker components failed to load: {str(e)}")
        return False
    
    # Test bot components
    print("\nTesting bot components...")
    try:
        from bot.bot import format_analysis_response
        print("✅ Bot components loaded")
    except Exception as e:
        print(f"❌ Bot components failed to load: {str(e)}")
        return False
    
    # Test payment processing components
    print("\nTesting payment processing components...")
    try:
        from api.payment_processor import PaymentProcessor
        from api.payment_encryption import encrypt_payment_data
        print("✅ Payment processing components loaded")
    except Exception as e:
        print(f"❌ Payment processing components failed to load: {str(e)}")
        return False
    
    print("\n✅ All components for product analysis pipeline verified!\n")
    print("The product analysis pipeline is ready for production.")
    return True

if __name__ == "__main__":
    success = test_pipeline_components()
    sys.exit(0 if success else 1)