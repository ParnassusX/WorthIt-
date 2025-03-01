# WorthIt! Product Scraper
import os
import json
from typing import Dict, Any, Optional, List
import httpx
from apify_client import ApifyClient
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Apify client
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
apify_client = ApifyClient(APIFY_TOKEN)

class ProductScraper:
    """Class to handle product data extraction from e-commerce websites"""
    
    def __init__(self):
        self.apify_client = apify_client
    
    async def extract_amazon_product(self, url: str) -> Dict[str, Any]:
        """Extract product data from Amazon using Apify"""
        try:
            # Validate URL (basic check)
            if not url.startswith("https://www.amazon."):
                raise ValueError("URL is not a valid Amazon product URL")
            
            # Run the Amazon Product Scraper actor
            run_input = {
                "startUrls": [{"url": url}],
                "maxRequestRetries": 3,
                "maxConcurrency": 1,
                "extendOutputFunction": "",
                "proxyConfiguration": {"useApifyProxy": True}
            }
            
            # Start the actor and wait for it to finish
            run = self.apify_client.actor("apify/amazon-product-scraper").call(run_input=run_input)
            
            # Fetch the actor's output
            items = self.apify_client.dataset(run["defaultDatasetId"]).list_items().items
            
            if not items:
                raise ValueError("No product data found")
            
            # Extract the first item (should be only one for a single URL)
            product_data = items[0]
            
            # Format the response
            return {
                "title": product_data.get("title", "Unknown Product"),
                "price": product_data.get("price", "Price not available"),
                "currency": product_data.get("currency", "EUR"),  # Default to EUR
                "images": product_data.get("images", []),
                "description": product_data.get("description", ""),
                "rating": product_data.get("rating", 0),
                "review_count": product_data.get("reviewsCount", 0),
                "url": url,
                "features": product_data.get("features", []),
                "availability": product_data.get("availability", "Unknown")
            }
            
        except Exception as e:
            # Log the error and return a structured error response
            print(f"Error extracting Amazon product: {str(e)}")
            return {
                "error": True,
                "message": f"Failed to extract product data: {str(e)}",
                "url": url
            }
    
    async def extract_reviews(self, url: str, max_reviews: int = 20) -> List[Dict[str, Any]]:
        """Extract product reviews from Amazon using Apify"""
        try:
            # Run the Amazon Review Scraper actor
            run_input = {
                "startUrls": [{"url": url}],
                "maxReviews": max_reviews,
                "includeDescription": True,
                "proxyConfiguration": {"useApifyProxy": True}
            }
            
            # Start the actor and wait for it to finish
            run = self.apify_client.actor("epctex/amazon-reviews-scraper").call(run_input=run_input)
            
            # Fetch the actor's output
            items = self.apify_client.dataset(run["defaultDatasetId"]).list_items().items
            
            if not items:
                return []
            
            # Format the reviews
            reviews = []
            for item in items:
                reviews.append({
                    "rating": item.get("rating", 0),
                    "title": item.get("title", ""),
                    "review": item.get("review", ""),
                    "date": item.get("date", ""),
                    "verified": item.get("verifiedPurchase", False)
                })
            
            return reviews
            
        except Exception as e:
            # Log the error and return an empty list
            print(f"Error extracting reviews: {str(e)}")
            return []

# Create a singleton instance
scraper = ProductScraper()

# Function to get product data (convenience function)
async def get_product_data(url: str) -> Dict[str, Any]:
    """Get product data from a URL"""
    # Currently only supports Amazon
    if "amazon" in url.lower():
        return await scraper.extract_amazon_product(url)
    else:
        return {
            "error": True,
            "message": "Unsupported e-commerce platform",
            "url": url
        }

# Function to get product reviews
async def get_product_reviews(url: str, max_reviews: int = 20) -> List[Dict[str, Any]]:
    """Get product reviews from a URL"""
    # Currently only supports Amazon
    if "amazon" in url.lower():
        return await scraper.extract_reviews(url, max_reviews)
    else:
        return []