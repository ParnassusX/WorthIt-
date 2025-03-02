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
    
    async def extract_product(self, url: str) -> Dict[str, Any]:
        """Extract product data from any supported e-commerce site using Apify Web Scraper"""
        try:
            # Run the Web Scraper actor with custom page function
            run_input = {
                "startUrls": [{"url": url}],
                "pageFunction": """
                async function pageFunction(context) {
                    const { $, request } = context;
                    
                    // Common selectors for major e-commerce sites
                    const selectors = {
                        amazon: {
                            title: '#productTitle, #title',
                            price: '.a-price .a-offscreen, #price_inside_buybox, #priceblock_ourprice',
                            description: '#feature-bullets, #productDescription, #productDetails',
                            reviews: '.review-text, .review-text-content, [data-hook="review-body"]'
                        },
                        ebay: {
                            title: '.x-item-title__mainTitle',
                            price: '.x-price-primary',
                            description: '.x-about-this-item',
                            reviews: '.ebay-review-section .review-item-content'
                        },
                        default: {
                            title: 'h1',
                            price: '[data-price], .price, .product-price',
                            description: '[data-description], .description, .product-description',
                            reviews: '.review, .product-review, .customer-review'
                        }
                    };
                    
                    // Determine site type from URL
                    let site = 'default';
                    if (request.url.includes('amazon')) site = 'amazon';
                    if (request.url.includes('ebay')) site = 'ebay';
                    
                    const selector = selectors[site];
                    
                    return {
                        title: $(selector.title).first().text().trim(),
                        price: $(selector.price).first().text().trim(),
                        description: $(selector.description).text().trim(),
                        reviews: $(selector.reviews).map((i, el) => $(el).text().trim()).get(),
                        url: request.url
                    };
                }
                """,
                "proxyConfiguration": {"useApifyProxy": True}
            }
            
            # Start the actor and wait for it to finish
            run = self.apify_client.actor("apify/web-scraper").call(run_input=run_input)
            
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
                "description": product_data.get("description", ""),
                "reviews": product_data.get("reviews", []),
                "url": url
            }
            
        except Exception as e:
            # Log the error and return a structured error response
            print(f"Error extracting product data: {str(e)}")
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
    # Now supports multiple e-commerce platforms
    return await scraper.extract_product(url)

# Function to get product reviews
async def get_product_reviews(url: str, max_reviews: int = 20) -> List[Dict[str, Any]]:
    """Get product reviews from a URL"""
    # Currently only supports Amazon
    if "amazon" in url.lower():
        return await scraper.extract_reviews(url, max_reviews)
    else:
        # For other sites, we extract reviews from the product data
        product_data = await scraper.extract_product(url)
        reviews = product_data.get("reviews", [])
        return [{"review": review, "rating": 0, "title": "", "date": "", "verified": False} for review in reviews]