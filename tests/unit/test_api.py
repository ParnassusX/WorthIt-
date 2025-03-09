import pytest
import httpx
from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock
import json
from api.main import app

# Test health endpoint
@pytest.mark.asyncio
async def test_health_check(test_client):
    # Use the test_client fixture from conftest.py
    response = await test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

# Test ML processor
@pytest.mark.asyncio
async def test_sentiment_analysis(async_client):
    test_text = "This is a great product!"
    
    with patch('api.main.analyze_sentiment') as mock_sentiment:
        mock_sentiment.return_value = {"label": "5 stars", "score": 0.9}
        response = await async_client.post(
            "/api/analyze/sentiment",
            json={"text": test_text}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert "score" in result
        assert result["score"] > 0
@pytest.mark.asyncio
async def test_pros_cons_extraction(async_client):
    test_reviews = [
        "The product has good quality but is expensive"
    ]
    test_product_data = {
        "title": "Test Product",
        "price": 99.99,
        "currency": "USD",
        "description": "A test product",
        "reviews": [
            {"text": "The product has good quality but is expensive", 
             "rating": 4.0, 
             "date": "2023-01-01", 
             "verified": True}
        ]
    }
    
    # Mock both the validation middleware and the extract_product_pros_cons function
    with patch('api.ml_processor.extract_product_pros_cons') as mock_pros_cons, \
         patch('api.validation.validation_middleware', side_effect=lambda req, call_next: call_next(req)):
        mock_pros_cons.return_value = (
            ["Good quality"],
            ["Expensive"]
        )
        response = await async_client.post(
            "/api/analyze/pros-cons",
            json={
                "reviews": test_reviews,
                "product_data": test_product_data
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result, dict)
        assert "pros" in result
        assert "cons" in result

@pytest.mark.asyncio
async def test_scraper(async_client):
    test_url = "https://amazon.com/product"
    
    with patch('api.scraper.scrape_product') as mock_scraper, \
         patch('api.validation.ProductURL.validate_marketplace', return_value=True):
        mock_scraper.return_value = {
            "title": "Test Product",
            "price": 99.99,
            "currency": "USD",
            "description": "A test product",
            "reviews": [{"text": "Great product", "rating": 4.5, "date": "2023-01-01", "verified": True}, 
                      {"text": "Good value", "rating": 4.0, "date": "2023-01-02", "verified": False}]
        }
        response = await async_client.post(
            "/api/scrape",
            json={"url": test_url}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert "title" in result
        assert "price" in result

# Test product analysis endpoint
@pytest.mark.asyncio
async def test_analyze_product(async_client):
    test_url = "https://amazon.com/product"
    
    with patch('api.routes.scrape_product') as mock_scraper, \
         patch('api.routes.extract_product_pros_cons') as mock_pros_cons, \
         patch('api.validation.ProductURL.validate_marketplace', return_value=True):
        mock_scraper.return_value = {
            "title": "Test Product",
            "price": 99.99,
            "currency": "USD",
            "rating": 4.5,
            "reviews": [{"text": "Great product", "rating": 4.5, "date": "2023-01-01", "verified": True}],
            "description": "A test product"
        }
        # The extract_product_pros_cons function returns a tuple (pros, cons), not a dictionary
        mock_pros_cons.return_value = (["Good quality"], ["Expensive"])
        
        response = await async_client.post(
            "/api/analyze/product",
            json={"url": test_url}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert "title" in result
        assert "value_score" in result
        assert "analysis" in result