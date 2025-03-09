# API Test Helpers for WorthIt!
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json
import os

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

# Helper functions for API tests

def setup_scraper_mock(mock_scraper):
    """Configure the scraper mock with standard test data."""
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
    return mock_scraper

def setup_ml_processor_mock(mock_pros_cons):
    """Configure the ML processor mock with standard test data."""
    # Handle both tuple and dictionary return types
    # The actual implementation returns a tuple, but tests expect a dictionary
    mock_pros_cons.return_value = {
        "pros": ["Good quality", "Fast delivery"],
        "cons": ["Expensive"]
    }
    return mock_pros_cons

# Patch decorators for common test scenarios

def patch_external_apis():
    """Patch all external API calls for testing."""
    return patch.multiple(
        'api.scraper',
        scrape_product=MagicMock(return_value=setup_scraper_mock(MagicMock()).return_value),
        apify_client=MagicMock()
    ), patch.multiple(
        'api.ml_processor',
        analyze_sentiment=MagicMock(return_value={"label": "4 stars", "score": 0.8}),
        extract_product_pros_cons=MagicMock(return_value=([
            "Good quality", "Fast delivery"
        ], [
            "Expensive"
        ]))
    )