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

# Test product analysis with mocked scraper
@pytest.mark.asyncio
async def test_product_analysis_success():
    """Test product analysis with mocked scraper"""
    # Mock data
    mock_product_data = {
        "title": "Test Product",
        "price": 99.99,
        "reviews": ["Great product", "Works well", "Good value"],
        "images": ["image1.jpg"]
    }
    
    # Mock sentiment results
    mock_sentiment_results = [
        [{"label": "5 stars", "score": 0.9}],
        [{"label": "4 stars", "score": 0.8}],
        [{"label": "5 stars", "score": 0.7}]
    ]
    
    # Mock pros and cons
    mock_pros_cons = {
        "pros": ["Good quality", "Fast delivery", "Great value"],
        "cons": ["Slightly expensive", "Could be better", "Some issues"]
    }
    
    # Create patches for the functions
    with patch('api.main.scrape_product', return_value=mock_product_data), \
         patch('api.main.analyze_sentiment', return_value=mock_sentiment_results), \
         patch('api.main.extract_pros_cons', return_value=mock_pros_cons), \
         patch('api.main.supabase.table'):
        
        # Test the endpoint
        response = client.post("/analyze", json={"url": "https://amazon.it/dp/B08J5F3G18"})
        
        # Check response
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Product"
        assert data["price"] == 99.99
        assert len(data["pros"]) == 3
        assert len(data["cons"]) == 3

# Test product analysis with scraper error
@pytest.mark.asyncio
async def test_product_analysis_scraper_error():
    """Test product analysis with scraper error"""
    # Mock scraper to raise an exception
    with patch('api.main.scrape_product', side_effect=ScrapingError()):
        # Test the endpoint
        response = client.post("/analyze", json={"url": "https://amazon.it/dp/B08J5F3G18"})
        
        # Check response
        assert response.status_code == 503
        assert "error" in response.json()

# Test URL validation
def test_url_validation():
    """Test URL validation"""
    # Test with invalid URL
    response = client.post("/analyze", json={"url": "https://invalid-site.com/product"})
    assert response.status_code == 400
    
    # Test with empty URL
    response = client.post("/analyze", json={"url": ""})
    assert response.status_code == 400