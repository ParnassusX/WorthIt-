# WorthIt! Product Scraper
import os
import json
import logging
import time
import asyncio
from typing import Dict, Any, Optional, List
import httpx
from apify_client import ApifyClient
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Apify client
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
if not APIFY_TOKEN:
    logger.warning("APIFY_TOKEN environment variable not set. Scraping features will not work properly.")

apify_client = ApifyClient(APIFY_TOKEN)

class ProductScraper:
    """Class to handle product data extraction from e-commerce websites with enhanced error handling"""
    
    def __init__(self):
        self.apify_client = apify_client
        self.timeout = httpx.Timeout(60.0, connect=15.0)
        self.limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "avg_latency": 0,
            "last_error": None,
            "last_request_time": None
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, httpx.HTTPError, httpx.TimeoutException, asyncio.TimeoutError))
    )
    async def extract_product(self, url: str) -> Dict[str, Any]:
        """Extract product data from any supported e-commerce site using Apify Web Scraper"""
        try:
            start_time = time.time()
            self.metrics["requests"] += 1
            
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
            
            try:
                # Start the actor and wait for it to finish with timeout handling
                run = self.apify_client.actor("apify/web-scraper").call(run_input=run_input, timeout_secs=120)
                
                # Fetch the actor's output
                items = self.apify_client.dataset(run["defaultDatasetId"]).list_items().items
                
                if not items:
                    error_msg = "No product data found"
                    logger.error(f"{error_msg} for URL: {url}")
                    self.metrics["errors"] += 1
                    self.metrics["last_error"] = error_msg
                    raise ValueError(error_msg)
                
                # Extract the first item (should be only one for a single URL)
                product_data = items[0]
                
                # Update metrics on success
                duration = time.time() - start_time
                self.metrics["last_request_time"] = duration
                self.metrics["avg_latency"] = (
                    (self.metrics["avg_latency"] * (self.metrics["requests"] - 1) + duration) / 
                    self.metrics["requests"]
                )
                
                # Format the response
                return {
                    "title": product_data.get("title", "Unknown Product"),
                    "price": product_data.get("price", "Price not available"),
                    "description": product_data.get("description", ""),
                    "reviews": product_data.get("reviews", []),
                    "url": url
                }
                
            except asyncio.TimeoutError:
                error_msg = "Timeout while waiting for Apify actor to complete"
                logger.error(f"{error_msg} for URL: {url}")
                self.metrics["errors"] += 1
                self.metrics["last_error"] = error_msg
                raise
                
            except Exception as e:
                error_msg = f"Error during Apify API call: {str(e)}"
                logger.error(f"{error_msg} for URL: {url}")
                self.metrics["errors"] += 1
                self.metrics["last_error"] = str(e)
                raise
            
        except Exception as e:
            # Log the error and return a structured error response
            logger.error(f"Error extracting product data: {str(e)}")
            return {
                "error": True,
                "message": f"Failed to extract product data: {str(e)}",
                "url": url
            }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, httpx.HTTPError, httpx.TimeoutException, asyncio.TimeoutError))
    )
    async def extract_reviews(self, url: str, max_reviews: int = 20) -> List[Dict[str, Any]]:
        """Extract product reviews from Amazon using Apify with enhanced error handling"""
        try:
            start_time = time.time()
            self.metrics["requests"] += 1
            
            # Run the Amazon Review Scraper actor
            run_input = {
                "startUrls": [{"url": url}],
                "maxReviews": max_reviews,
                "includeDescription": True,
                "proxyConfiguration": {"useApifyProxy": True}
            }
            
            try:
                # Start the actor and wait for it to finish with timeout handling
                run = self.apify_client.actor("epctex/amazon-reviews-scraper").call(run_input=run_input, timeout_secs=120)
                
                # Fetch the actor's output
                items = self.apify_client.dataset(run["defaultDatasetId"]).list_items().items
                
                if not items:
                    logger.warning(f"No reviews found for URL: {url}")
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
                
                # Update metrics on success
                duration = time.time() - start_time
                self.metrics["last_request_time"] = duration
                self.metrics["avg_latency"] = (
                    (self.metrics["avg_latency"] * (self.metrics["requests"] - 1) + duration) / 
                    self.metrics["requests"]
                )
                
                return reviews
                
            except asyncio.TimeoutError:
                error_msg = "Timeout while waiting for Apify actor to complete"
                logger.error(f"{error_msg} for URL: {url}")
                self.metrics["errors"] += 1
                self.metrics["last_error"] = error_msg
                raise
                
            except Exception as e:
                error_msg = f"Error during Apify API call: {str(e)}"
                logger.error(f"{error_msg} for URL: {url}")
                self.metrics["errors"] += 1
                self.metrics["last_error"] = str(e)
                raise
            
        except Exception as e:
            # Log the error and return an empty list
            logger.error(f"Error extracting reviews: {str(e)}")
            self.metrics["errors"] += 1
            self.metrics["last_error"] = str(e)
            return []

# Create a singleton instance
scraper = ProductScraper()

# Function to get product data (convenience function)
async def get_product_data(url: str) -> Dict[str, Any]:
    """Get product data from a URL"""
    # Now supports multiple e-commerce platforms
    return await scraper.extract_product(url)

# Simple implementation of scrape_product for tests
def scrape_product(url: str) -> Dict[str, Any]:
    """Mock scraper function for tests.
    Returns a predefined product structure.
    """
    # Return a mock product based on the URL
    if "example.com" in url:
        return {
            "title": "Test Product",
            "price": 99.99,
            "reviews": ["Great product", "Worth the money"],
            "rating": 4.5
        }
    else:
        return {
            "title": "Unknown Product",
            "price": 0,
            "reviews": [],
            "rating": 0
        }

    async def search_products(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search for products across supported e-commerce platforms using Apify"""
        try:
            # Run the Product Search actor with custom page function
            run_input = {
                "search": query,
                "maxResults": max_results,
                "pageFunction": """
                async function pageFunction(context) {
                    const { $, request, log } = context;
                    
                    // Extract search results
                    const products = [];
                    
                    // Amazon-specific selectors
                    const amazonSelectors = {
                        container: '[data-component-type="s-search-result"]',
                        title: 'h2 a.a-link-normal',
                        price: '.a-price .a-offscreen',
                        url: 'h2 a.a-link-normal'
                    };
                    
                    // Extract data using selectors
                    $(amazonSelectors.container).each((i, el) => {
                        const $el = $(el);
                        const title = $el.find(amazonSelectors.title).text().trim();
                        const price = $el.find(amazonSelectors.price).first().text().trim();
                        const url = 'https://www.amazon.com' + $el.find(amazonSelectors.url).attr('href');
                        
                        if (title && url) {
                            products.push({
                                title,
                                price: price || 'Price not available',
                                url
                            });
                        }
                    });
                    
                    return products;
                }
                """,
                "startUrls": [{
                    "url": f"https://www.amazon.com/s?k={query}"
                }],
                "proxyConfiguration": {"useApifyProxy": true}
            }
            
            # Start the actor and wait for it to finish
            run = self.apify_client.actor("apify/web-scraper").call(run_input=run_input)
            
            # Fetch the actor's output
            items = self.apify_client.dataset(run["defaultDatasetId"]).list_items().items
            
            # Flatten and format the results
            results = []
            for item in items:
                if isinstance(item, list):
                    results.extend(item)
                else:
                    results.append(item)
            
            # Return the first max_results items
            return results[:max_results]
            
        except Exception as e:
            print(f"Error searching products: {str(e)}")
            return []

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