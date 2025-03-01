from fastapi.testclient import TestClient
import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path to import the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.main import app
from api.errors import ScrapingError

# Create test client
client = TestClient(app)

# Test health check endpoint
def test_health_check():
    """Test the root endpoint for health check"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"
    assert response.json()["service"] == "WorthIt! API"

# Test product analysis with mocked functions
@pytest.mark.asyncio
async def test_product_analysis_success():
    """Test product analysis with mocked functions"""
    # Mock data
    mock_product_data = {
        "title": "Test Product",
        "price": "$99.99",
        "description": "A great test product with amazing features",
        "reviews": ["Great product", "Works well", "Good value"],
        "url": "https://amazon.com/test-product"
    }
    
    # Mock sentiment analysis result
    mock_sentiment_result = {"label": "4 stars", "score": 0.8}
    
    # Mock pros/cons generation result
    mock_pros_cons_result = {
        "generated_text": "Pros:\n- High quality\n- Good features\n- Great value\n\nCons:\n- Slightly expensive\n- Limited colors\n- Basic packaging"
    }
    
    # Create patches for the functions
    with patch('api.main.scrape_product', return_value=mock_product_data), \
         patch('api.main.analyze_sentiment', return_value=mock_sentiment_result), \
         patch('api.main.generate_pros_cons', return_value=mock_pros_cons_result):
        
        # Test the endpoint
        response = client.post("/analyze", params={"url": "https://amazon.com/test-product"})
        
        # Check response
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Product"
        assert data["price"] == "$99.99"
        assert isinstance(data["value_score"], (int, float))
        assert isinstance(data["sentiment_score"], (int, float))
        assert len(data["pros"]) > 0
        assert len(data["cons"]) > 0
        assert data["recommendation"] in ["Worth it!", "Think twice!"]

# Test product analysis with scraper error
@pytest.mark.asyncio
async def test_product_analysis_scraper_error():
    """Test product analysis with scraper error"""
    # Mock scraper to raise an exception
    with patch('api.main.scrape_product', side_effect=ValueError("Missing Apify token")):
        # Test the endpoint
        response = client.post("/analyze", params={"url": "https://amazon.com/test-product"})
        
        # Check response
        assert response.status_code == 401
        assert "detail" in response.json()

# Test URL validation
def test_url_validation():
    """Test URL validation"""
    # Test with invalid URL
    response = client.post("/analyze", params={"url": "not-a-valid-url"})
    assert response.status_code == 400
    
    # Test with empty URL
    response = client.post("/analyze", params={"url": ""})
    assert response.status_code == 400