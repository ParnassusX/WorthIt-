from fastapi import FastAPI, HTTPException
import os
import httpx
import asyncio
import logging
from api.errors import register_exception_handlers
from api.health import router as health_router
from api.ml_processor import analyze_reviews, extract_product_pros_cons, get_value_score

# Configure logging
logger = logging.getLogger(__name__)

app = FastAPI(title="WorthIt! API", version="1.0.0")

# Enable CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register error handlers
register_exception_handlers(app)

# Include routers
app.include_router(health_router)

# Import and include image analysis router
from api.image_analyzer import router as image_router
app.include_router(image_router, prefix="/api")

# Hugging Face API endpoints
SENTIMENT_API_URL = "https://api-inference.huggingface.co/models/nlptown/bert-base-multilingual-uncased-sentiment"
TEXT_GENERATION_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"

# Hugging Face API functions
async def analyze_sentiment(text):
    """Use Hugging Face API for sentiment analysis"""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        logger.warning("No Hugging Face token found. Using fallback sentiment analysis.")
        # Simple fallback sentiment analysis
        return {"label": "3 stars", "score": 0.5}
    
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {"inputs": text}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(SENTIMENT_API_URL, headers=headers, json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()[0]
    except Exception as e:
        logger.error(f"Sentiment analysis API error: {e}")
        return {"label": "3 stars", "score": 0.5}  # Fallback

async def generate_pros_cons(prompt):
    """Use Hugging Face API for text generation"""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        logger.warning("No Hugging Face token found. Using fallback pros/cons generation.")
        return {"generated_text": "Pros:\n- Quality product\n- Good value\n\nCons:\n- Could be improved\n- Limited features"}
    
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "inputs": prompt,
        "parameters": {"max_length": 500, "return_full_text": False}
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(TEXT_GENERATION_API_URL, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            return {"generated_text": response.json()[0]["generated_text"]}
    except Exception as e:
        logger.error(f"Text generation API error: {e}")
        return {"generated_text": "Pros:\n- Quality product\n- Good value\n\nCons:\n- Could be improved\n- Limited features"}  # Fallback

# Scraping function using Apify
async def scrape_product(url):
    apify_token = os.getenv("APIFY_TOKEN")
    if not apify_token:
        raise ValueError("Missing Apify token. Set APIFY_TOKEN environment variable.")
    
    async with httpx.AsyncClient() as client:
        # Start the scraping task
        response = await client.post(
            "https://api.apify.com/v2/acts/apify~web-scraper/runs",
            headers={"Authorization": f"Bearer {apify_token}"},
            json={
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
                """
            }
        )
        run_id = response.json()["id"]
        
        # Wait for results
        while True:
            await asyncio.sleep(2)
            status = await client.get(
                f"https://api.apify.com/v2/acts/apify~web-scraper/runs/{run_id}",
                headers={"Authorization": f"Bearer {apify_token}"}
            )
            if status.json()["status"] == "SUCCEEDED":
                break
        
        # Get results
        results = await client.get(
            f"https://api.apify.com/v2/acts/apify~web-scraper/runs/{run_id}/dataset/items",
            headers={"Authorization": f"Bearer {apify_token}"}
        )
        
        # Check if we got any results
        data = results.json()
        if not data or len(data) == 0:
            logger.error(f"No data returned from scraper for URL: {url}")
            raise Exception(f"Failed to extract product data from {url}")
            
        return data[0]

def parse_pros_cons(analysis_text: str):
    """Parse pros and cons from the generated analysis text."""
    pros = []
    cons = []
    current_list = None
    
    for line in analysis_text.split('\n'):
        line = line.strip().lower()
        if 'pros:' in line or 'advantages:' in line or 'benefits:' in line:
            current_list = pros
        elif 'cons:' in line or 'disadvantages:' in line or 'drawbacks:' in line:
            current_list = cons
        elif current_list is not None and line.startswith('-'):
            current_list.append(line[1:].strip())
    
    return {
        'pros': pros[:3] if pros else ['No clear advantages found'],
        'cons': cons[:3] if cons else ['No clear disadvantages found']
    }

@app.post("/analyze")
async def analyze_product(url: str):
    try:
        if not url or not (url.startswith('http://') or url.startswith('https://')):
            raise HTTPException(status_code=400, detail="Invalid URL provided")

        # Scrape product data
        try:
            product_data = await scrape_product(url)
        except ValueError as e:
            raise HTTPException(status_code=401, detail=str(e))
        except Exception as e:
            logger.error(f"Scraping error: {e}")
            raise HTTPException(status_code=503, detail="Unable to fetch product data")

        if not product_data.get('reviews'):
            logger.warning(f"No reviews found for product: {url}")

        # Prepare reviews data structure for ML processor
        reviews = []
        for review_text in product_data.get('reviews', []):
            reviews.append({"review": review_text})
            
        # Use ml_processor for sentiment analysis
        try:
            sentiment_data = await analyze_reviews(reviews)
            avg_sentiment = sentiment_data.get('average_sentiment', 3)
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            avg_sentiment = 3  # Fallback to neutral sentiment
            sentiment_data = {"average_sentiment": avg_sentiment}

        # Use ml_processor for pros/cons extraction
        try:
            # Prepare product data structure
            processed_product_data = {
                "title": product_data.get("title", "Unknown Product"),
                "description": product_data.get("description", ""),
                "features": [],  # Extract features if available in your scraping
                "price": product_data.get("price", "Price not available"),
                "url": url
            }
            
            pros, cons = await extract_product_pros_cons(reviews, processed_product_data)
            pros_cons = {
                'pros': pros,
                'cons': cons
            }
        except Exception as e:
            logger.error(f"Pros/cons analysis error: {e}")
            pros_cons = {
                'pros': ['Analysis unavailable'],
                'cons': ['Analysis unavailable']
            }

        # Use ml_processor for value score calculation
        try:
            value_score = await get_value_score(processed_product_data, sentiment_data)
        except Exception as e:
            logger.error(f"Value score calculation error: {e}")
            value_score = min(10, max(1, avg_sentiment * 2))  # Fallback calculation

        return {
            "title": product_data.get("title", "Unknown Product"),
            "price": product_data.get("price", "Price not available"),
            "value_score": value_score,
            "sentiment_score": avg_sentiment,
            "pros": pros_cons['pros'],
            "cons": pros_cons['cons'],
            "recommendation": "Worth it!" if value_score >= 7 else "Think twice!"
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {"status": "online", "service": "WorthIt! API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)