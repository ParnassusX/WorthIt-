from fastapi import FastAPI, HTTPException
import os
import httpx
import asyncio
import logging
from api.errors import register_exception_handlers
from transformers import pipeline

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

# Initialize Hugging Face pipelines
try:
    sentiment_analyzer = pipeline(
        "text-classification",
        model="nlptown/bert-base-multilingual-uncased-sentiment",
        token=os.getenv("HF_TOKEN")
    )

    pros_cons_analyzer = pipeline(
        "text-generation",
        model="mistralai/Mistral-7B-Instruct-v0.2",
        token=os.getenv("HF_TOKEN")
    )
except Exception as e:
    logger.error(f"Failed to initialize Hugging Face pipelines: {e}")
    raise RuntimeError("AI analysis services unavailable")

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
                            title: '#productTitle',
                            price: '.a-price .a-offscreen',
                            description: '#feature-bullets, #productDescription',
                            reviews: '.review-text'
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
        return results.json()[0]

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

        # Analyze reviews sentiment
        try:
            sentiments = []
            for review in product_data.get('reviews', []):
                result = sentiment_analyzer(review)[0]
                score = int(result['label'].split('stars')[0])
                sentiments.append(score)

            avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 3
        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            avg_sentiment = 3  # Fallback to neutral sentiment

        # Generate pros/cons analysis
        try:
            analysis_prompt = f"""Analyze this product description and provide a structured list of pros and cons. Format your response as follows:

Pros:
- [advantage 1]
- [advantage 2]
- [advantage 3]

Cons:
- [disadvantage 1]
- [disadvantage 2]
- [disadvantage 3]

Product description:
{product_data['description']}"""

            analysis_result = pros_cons_analyzer(analysis_prompt, max_length=500, num_return_sequences=1)[0]
            pros_cons = parse_pros_cons(analysis_result['generated_text'])
        except Exception as e:
            logger.error(f"Pros/cons analysis error: {e}")
            pros_cons = {
                'pros': ['Analysis unavailable'],
                'cons': ['Analysis unavailable']
            }

        # Calculate value score (1-10)
        value_score = min(10, max(1, avg_sentiment * 2))  # Ensure score is between 1-10

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)