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
    test_reviews = ["The product has good quality but is expensive"]
    test_product_data = {
        "title": "Test Product",
        "price": 99.99,
        "description": "A test product",
        "reviews": test_reviews
    }
    
    with patch('api.ml_processor.extract_product_pros_cons') as mock_pros_cons:
        mock_pros_cons.return_value = {
            "pros": ["Good quality"],
            "cons": ["Expensive"]
        }
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
    test_url = "https://example.com/product"
    
    with patch('api.scraper.scrape_product') as mock_scraper:
        mock_scraper.return_value = {
            "title": "Test Product",
            "price": 99.99,
            "description": "A test product",
            "reviews": ["Great product", "Good value"]
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
    test_url = "https://example.com/product"
    
    with patch('api.routes.scrape_product') as mock_scraper, \
         patch('api.routes.extract_product_pros_cons') as mock_pros_cons:
        mock_scraper.return_value = {
            "title": "Test Product",
            "price": 99.99,
            "rating": 4.5,
            "reviews": ["Great product"],
            "description": "A test product"
        }
        mock_pros_cons.return_value = {
            "pros": ["Good quality"],
            "cons": ["Expensive"]
        }
        
        response = await async_client.post(
            "/api/analyze/product",
            json={"url": test_url}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert "title" in result
        assert "value_score" in result
        assert "analysis" in result