from fastapi import FastAPI
from supabase import create_client
from transformers import pipeline
import os
import httpx
import asyncio
from api.errors import register_exception_handlers

app = FastAPI()

# Register error handlers
register_exception_handlers(app)

# Initialize Supabase client
def get_supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("Missing Supabase credentials. Set SUPABASE_URL and SUPABASE_KEY environment variables.")
    return create_client(url, key)

# Initialize sentiment analyzer
def get_sentiment_analyzer():
    try:
        return pipeline(
            "text-classification", 
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            token=os.getenv("HF_TOKEN")
        )
    except Exception as e:
        print(f"Error loading sentiment model: {e}")
        return None

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
        
        sentiment_analyzer = get_sentiment_analyzer()
        if not sentiment_analyzer:
            return 0.0
        
        # Get average sentiment (1-5 scale)
        sentiments = []
        for review in reviews[:10]:  # Analyze up to 10 reviews
            try:
                result = sentiment_analyzer(review)
                # Extract the star rating from the label (e.g., "5 stars" -> 5)
                rating = int(result[0]["label"].split()[0])
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
        
        # Save to database
        try:
            supabase = get_supabase()
            supabase.table("products").insert(analysis).execute()
        except Exception as db_error:
            print(f"Database error: {db_error}")
        
        return analysis
    
    except Exception as e:
        return {"error": str(e)}

@app.get("/products")
async def get_products():
    try:
        supabase = get_supabase()
        response = supabase.table("products").select("*").execute()
        return response.data
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)