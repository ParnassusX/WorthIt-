# API Test Configuration for WorthIt!
import pytest
import os
import sys
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
from fastapi.testclient import TestClient

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.main import app

# Mock responses for external services
@pytest.fixture
def mock_apify_client():
    """Create a mock Apify client for testing."""
    mock_client = MagicMock()
    mock_actor = MagicMock()
    mock_dataset = MagicMock()
    
    # Configure the mock objects
    mock_actor.call.return_value = {"defaultDatasetId": "test-dataset-id"}
    mock_dataset.list_items.return_value.items = [{
        "title": "Test Product",
        "price": "$99.99",
        "description": "This is a test product description.",
        "reviews": ["Great product!", "Worth the money", "Fast shipping", "Good quality but expensive"],
        "url": "https://example.com/product"
    }]
    
    mock_client.actor.return_value = mock_actor
    mock_client.dataset.return_value = mock_dataset
    
    return mock_client

@pytest.fixture
def mock_huggingface_api():
    """Create a mock for Hugging Face API calls."""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = [
            # Sentiment analysis response
            [{"label": "4 stars", "score": 0.8}],
            # Text generation for pros/cons
            [{"generated_text": "Pros:\n- Good quality\n- Fast delivery\n\nCons:\n- Expensive"}]
        ]
        
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
        yield mock_client

@pytest.fixture
def mock_api_environment():
    """Set up environment variables for API testing."""
    original_env = {}
    test_env = {
        "APIFY_TOKEN": "test_apify_token",
        "HF_TOKEN": "test_huggingface_token",
        "TESTING": "true"
    }
    
    # Save original environment variables
    for key in test_env:
        if key in os.environ:
            original_env[key] = os.environ[key]
    
    # Set test environment variables
    for key, value in test_env.items():
        os.environ[key] = value
    
    yield
    
    # Restore original environment variables
    for key in test_env:
        if key in original_env:
            os.environ[key] = original_env[key]
        else:
            del os.environ[key]

# Patch the scraper and ML processor functions for testing
@pytest.fixture(autouse=True)
def patch_external_apis():
    """Patch all external API calls for testing."""
    with patch('api.scraper.scrape_product') as mock_scraper, \
         patch('api.ml_processor.extract_product_pros_cons') as mock_pros_cons, \
         patch('api.scraper.apify_client') as mock_apify, \
         patch('api.main.analyze_sentiment') as mock_sentiment:
        
        # Configure scraper mock
        mock_scraper.return_value = {
            "title": "Test Product",
            "price": 99.99,
            "currency": "USD",
            "description": "A test product",
            "reviews": [{
                "text": "Great product", 
                "rating": 4.5, 
                "date": "2023-01-01", 
                "verified": True
            }, {
                "text": "Good value", 
                "rating": 4.0, 
                "date": "2023-01-02", 
                "verified": False
            }],
            "rating": 4.5
        }
        
        # Configure ML processor mock - IMPORTANT: Return a tuple to match implementation
        mock_pros_cons.return_value = (
            ["Good quality", "Fast delivery"],
            ["Expensive"]
        )
        
        # Configure sentiment analysis mock
        mock_sentiment.return_value = {"label": "4 stars", "score": 0.8}
        
        # Configure Apify client mock
        mock_apify.return_value = mock_apify_client()
        
        yield mock_scraper, mock_pros_cons, mock_apify, mock_sentiment

# Test client fixtures
@pytest.fixture
def test_app():
    """Create a test instance of the FastAPI application."""
    return app

@pytest.fixture
def test_client(test_app):
    """Create a test client for the FastAPI application."""
    return TestClient(test_app)

@pytest.fixture
async def async_client(test_app):
    """Create an async test client for the FastAPI application."""
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        yield client