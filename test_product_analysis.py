#!/usr/bin/env python
"""
Product Analysis Pipeline Test Script for WorthIt!

This script tests the product analysis pipeline by scraping an Amazon product
and running sentiment analysis on its reviews to verify backend functionality.
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path for imports
sys.path.append(str(Path(__file__).parent))

# Import required components
from api.scraper import scrape_product
from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score

async def test_product_analysis():
    """Test the product analysis pipeline."""
    print("\n===== WorthIt! Product Analysis Pipeline Test =====\n")
    
    # Load environment variables
    load_dotenv()
    
    # Test product URL
    test_url = "https://www.amazon.com/dp/B08N5KWB9H"
    print(f"Testing product analysis for URL: {test_url}\n")
    
    # Step 1: Test product scraping
    print("Step 1: Testing product scraping...")
    try:
        product_data = scrape_product(test_url)
        if product_data:
            print(f"✅ Successfully scraped product data")
            print(f"   Title: {product_data.get('title')}")
            print(f"   Price: {product_data.get('price')}")
            reviews = product_data.get('reviews', [])
            print(f"   Found {len(reviews)} reviews")
        else:
            print("❌ Failed to scrape product data")
            return False
    except Exception as e:
        print(f"❌ Error during product scraping: {str(e)}")
        return False
    
    print()
    
    # Step 2: Test sentiment analysis
    if reviews:
        print("Step 2: Testing sentiment analysis...")
        try:
            # Only use first 5 reviews for faster testing
            test_reviews = reviews[:5]
            sentiment = analyze_sentiment(test_reviews)
            print(f"✅ Successfully analyzed sentiment: {sentiment}")
        except Exception as e:
            print(f"❌ Error during sentiment analysis: {str(e)}")
            return False
        
        print()
    
        # Step 3: Test pros/cons extraction
        print("Step 3: Testing pros/cons extraction...")
        try:
            pros_cons = extract_product_pros_cons(test_reviews)
            print(f"✅ Successfully extracted pros/cons")
            print(f"   Pros: {pros_cons.get('pros')}")
            print(f"   Cons: {pros_cons.get('cons')}")
        except Exception as e:
            print(f"❌ Error during pros/cons extraction: {str(e)}")
            return False
        
        print()
        
        # Step 4: Test value score calculation
        print("Step 4: Testing value score calculation...")
        try:
            price = product_data.get('price', '').replace('$', '').split(' ')[0]
            if price and price.replace('.', '').isdigit():
                price = float(price)
                value_score = get_value_score(sentiment, price)
                print(f"✅ Successfully calculated value score: {value_score}")
            else:
                print("⚠️ Could not calculate value score: invalid price format")
        except Exception as e:
            print(f"❌ Error during value score calculation: {str(e)}")
            return False
    
    print("\n===== Product Analysis Pipeline Test Complete =====\n")
    print("✅ All tests passed successfully!")
    return True

async def main():
    """Main entry point for the script."""
    success = await test_product_analysis()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())