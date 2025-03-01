from fastapi import FastAPI, HTTPException
import os
import httpx
import asyncio
from api.errors import register_exception_handlers
from textblob import TextBlob

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

# In-memory storage for products (temporary solution while Supabase is disabled)
products_db = []

# Simple sentiment analysis function
def analyze_sentiment(text):
    try:
        analysis = TextBlob(text)
        # Convert polarity (-1 to 1) to 1-5 scale
        sentiment_score = ((analysis.sentiment.polarity + 1) * 2) + 1
        return min(5, max(1, sentiment_score))
    except Exception as e:
        print(f"Error analyzing sentiment: {e}")
        return 3  # Neutral sentiment as fallback

# Scraping function using Apify
async def scrape_product(url):
    apify_token = os.getenv("APIFY_TOKEN")
    if not apify_token:
        raise ValueError("Missing Apify token. Set APIFY_TOKEN environment variable.")
    
    async with httpx.AsyncClient() as client:
        # Start the scraping task
        response = await client.post(
            "https://api.apify.com/v2/actor-tasks/your_task_id/runs",
            headers={"Authorization": f"Bearer {apify_token}"},
            json={"startUrls": [{"url": url}]}
        )
        run_data = response.json()
        run_id = run_data.get("data", {}).get("id")
        
        if not run_id:
            raise ValueError(f"Failed to start Apify task: {run_data}")
        
        # Wait for the task to complete
        while True:
            status_response = await client.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                headers={"Authorization": f"Bearer {apify_token}"}
            )
            status = status_response.json().get("data", {}).get("status")
            if status == "SUCCEEDED":
                break
            elif status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                raise ValueError(f"Apify task failed with status: {status}")
            await asyncio.sleep(2)
        
        # Get the results
        dataset_response = await client.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items",
            headers={"Authorization": f"Bearer {apify_token}"}
        )
        return dataset_response.json()

# Extract pros and cons from reviews
def extract_pros_cons(reviews):
    # Simple extraction based on keywords
    pros = []
    cons = []
    
    positive_keywords = ["ottimo", "eccellente", "buono", "perfetto", "consigliato"]
    negative_keywords = ["scarso", "pessimo", "difettoso", "problema", "delusione"]
    
    for review in reviews:
        review_lower = review.lower()
        
        # Check for positive aspects
        for keyword in positive_keywords:
            if keyword in review_lower:
                sentence = next((s for s in review.split(".") if keyword.lower() in s.lower()), "")
                if sentence and sentence not in pros:
                    pros.append(sentence.strip())
        
        # Check for negative aspects
        for keyword in negative_keywords:
            if keyword in review_lower:
                sentence = next((s for s in review.split(".") if keyword.lower() in s.lower()), "")
                if sentence and sentence not in cons:
                    cons.append(sentence.strip())
    
    return {"pros": pros[:3], "cons": cons[:3]}  # Return top 3 pros and cons

# Calculate value score
def analyze_value(data):
    try:
        # Extract prices
        prices = [float(p["price"].replace("€", "").replace(",", ".")) 
                 for p in data.get("prices", []) if "price" in p]
        
        if not prices:
            return 0.0
        
        avg_price = sum(prices) / len(prices)
        
        # Get sentiment scores
        reviews = data.get("reviews", [])
        if not reviews:
            return 0.0
        
        # Get average sentiment (1-5 scale)
        sentiments = []
        for review in reviews[:10]:  # Analyze up to 10 reviews
            try:
                rating = analyze_sentiment(review)
                sentiments.append(rating)
            except Exception:
                continue
        
        if not sentiments:
            return 0.0
        
        avg_sentiment = sum(sentiments) / len(sentiments)
        
        # Calculate value score (sentiment / normalized price)
        # Higher score = better value for money
        value_score = (avg_sentiment * 100) / (avg_price + 1)  # +1 to avoid division by zero
        
        # Normalize to 0-5 scale
        return min(5.0, max(0.0, value_score / 20))
    
    except Exception as e:
        print(f"Error analyzing value: {e}")
        return 0.0

# API endpoints
@app.get("/")
async def root():
    return {"message": "WorthIt! API is running"}

@app.post("/analyze")
async def analyze_product_endpoint(url: str):
    try:
        # Scrape product data
        product_data = await scrape_product(url)
        
        # Analyze the product
        value_score = analyze_value(product_data)
        pros_cons = extract_pros_cons(product_data.get("reviews", []))
        
        # Prepare analysis result
        analysis = {
            "url": url,
            "value_score": value_score,
            "pros_cons": pros_cons,
            "recommendation": "🟢 Ottimo" if value_score >= 4.0 else 
                           "🟡 Accettabile" if value_score >= 3.0 else 
                           "🔴 Scarso"
        }
        
        # Save to in-memory database (temporary solution)
        products_db.append(analysis)
        
        return analysis
    
    except Exception as e:
        return {"error": str(e)}

@app.get("/products")
async def get_products():
    try:
        # Return products from in-memory database (temporary solution)
        return products_db
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)