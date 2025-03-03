import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
import json
from api.main import app

# Test health endpoint
def test_health_check(test_client):
    with TestClient(app) as client:
        response = client.get('/health')
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "healthy"}

# Test ML processor
@pytest.mark.asyncio
async def test_sentiment_analysis(test_client):
    # Test the sentiment analysis endpoint
    with patch('api.ml_processor.analyze_sentiment') as mock_analyze:
        mock_analyze.return_value = {"label": "4 stars", "score": 0.8}
        with patch('api.ml_processor.analyze_sentiment') as mock_analyze:
            mock_analyze.return_value = {"label": "4 stars", "score": 0.8}
            
            response = test_client.post(
                "/api/analyze/sentiment",
                json={"text": "This product is amazing!"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        assert "label" in response.json()
        assert "score" in response.json()
        mock_analyze.assert_called_once_with("This product is amazing!")

@pytest.mark.asyncio
async def test_pros_cons_extraction(test_client):
    # Test the pros/cons extraction endpoint
    with patch('api.ml_processor.extract_product_pros_cons') as mock_extract:
        with patch('api.ml_processor.extract_product_pros_cons') as mock_extract:
            mock_extract.return_value = {
                "pros": ["Good quality", "Fast delivery"],
                "cons": ["Expensive", "Short battery life"]
            }
            
            test_reviews = ["Good quality but expensive", "Fast delivery but short battery life"]
            response = test_client.post(
                "/api/analyze/pros-cons",
                json={"reviews": test_reviews}
            )
        
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert "pros" in result
        assert "cons" in result
        mock_extract.assert_called_once_with(test_reviews)

@pytest.mark.asyncio
async def test_scraper(test_client):
    # Test the scraper endpoint
    with patch('api.scraper.scrape_product') as mock_scrape:
        with patch('api.scraper.scrape_product') as mock_scrape:
            mock_product_data = {
                "title": "Test Product",
                "price": 99.99,
                "reviews": ["Great product", "Worth the money"],
                "rating": 4.5
            }
            mock_scrape.return_value = mock_product_data
            
            test_url = "https://example.com/product"
            response = test_client.post(
                "/api/scrape",
                json={"url": test_url}
            )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == mock_product_data
        mock_scrape.assert_called_once_with(test_url)

# Test product analysis endpoint
@pytest.mark.asyncio
async def test_analyze_product(test_client):
    # Test the complete product analysis flow
    with patch('api.scraper.scrape_product') as mock_scrape,\
         patch('api.ml_processor.extract_product_pros_cons') as mock_extract,\
         patch('api.ml_processor.get_value_score', return_value=0.75):
        with patch('api.scraper.scrape_product') as mock_scrape, \
             patch('api.ml_processor.extract_product_pros_cons') as mock_extract, \
             patch('api.ml_processor.get_value_score', return_value=0.75):
            
            # Setup mock returns
            mock_scrape.return_value = {
                "title": "Test Product",
                "price": 99.99,
                "reviews": ["Great product", "Worth the money"],
                "rating": 4.5
            }
            mock_extract.return_value = {
                "pros": ["Good quality", "Fast delivery"],
                "cons": ["Expensive"]
            }
            
            response = test_client.post(
                "/api/analyze/product",
                json={"url": "https://example.com/product"}
            )
        
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert "title" in result
        assert "price" in result
        assert "value_score" in result
        assert "analysis" in result
        # The value score is calculated in the route handler
        assert isinstance(result["value_score"], float)