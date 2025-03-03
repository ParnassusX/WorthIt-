# Test helper functions for WorthIt! API tests
from typing import Dict, List, Union, Any

# Simple implementation of analyze_sentiment for tests
def analyze_sentiment(text: str) -> Dict[str, Union[str, float]]:
    """Analyze the sentiment of a given text and return a label and score.
    This is a simplified version for tests.
    """
    # Simple sentiment analysis based on keywords
    positive_words = ['good', 'great', 'excellent', 'amazing', 'love', 'best', 'worth']
    negative_words = ['bad', 'poor', 'terrible', 'awful', 'hate', 'worst', 'expensive']
    
    text_lower = text.lower()
    
    # Count positive and negative words
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    # Calculate sentiment score
    total = positive_count + negative_count
    if total == 0:
        score = 0.5  # Neutral
    else:
        score = positive_count / total
    
    # Determine label based on score
    if score >= 0.8:
        label = "5 stars"
    elif score >= 0.6:
        label = "4 stars"
    elif score >= 0.4:
        label = "3 stars"
    elif score >= 0.2:
        label = "2 stars"
    else:
        label = "1 star"
    
    return {"label": label, "score": score}

# Simple implementation of extract_product_pros_cons for tests
def extract_product_pros_cons(reviews: List[str]) -> Dict[str, List[str]]:
    """Extract pros and cons from a list of product reviews.
    This is a simplified version for tests.
    """
    pros = []
    cons = []
    
    positive_phrases = ['good', 'great', 'excellent', 'amazing', 'love', 'best', 'worth', 'fast', 'quality']
    negative_phrases = ['bad', 'poor', 'terrible', 'awful', 'hate', 'worst', 'expensive', 'slow', 'short']
    
    for review in reviews:
        review_lower = review.lower()
        
        # Check for "but" to separate pros and cons
        if 'but' in review_lower:
            parts = review_lower.split('but')
            
            # Check first part for pros
            for phrase in positive_phrases:
                if phrase in parts[0]:
                    pros.append(review.split('but')[0].strip())
                    break
            
            # Check second part for cons
            for phrase in negative_phrases:
                if phrase in parts[1]:
                    cons.append(review.split('but')[1].strip())
                    break
        else:
            # If no "but", check overall sentiment
            sentiment = analyze_sentiment(review)
            if sentiment['score'] >= 0.6:
                pros.append(review)
            elif sentiment['score'] <= 0.4:
                cons.append(review)
    
    # If no pros or cons found, add defaults
    if not pros:
        pros = ["Good quality"]
    if not cons:
        cons = ["No significant cons found"]
    
    return {"pros": pros, "cons": cons}

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
            "price": 49.99,
            "reviews": ["No reviews available"],
            "rating": 3.0
        }