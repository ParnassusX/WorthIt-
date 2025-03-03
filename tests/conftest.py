import pytest
import asyncio
import os
import httpx
import json
from fastapi.testclient import TestClient
from httpx import AsyncClient
from redis.asyncio import Redis
from unittest.mock import AsyncMock, patch, MagicMock
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
from api.main import app
from bot.bot import WorthItBot
from worker.worker import TaskWorker

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_update():
    """Create a mock Telegram update object."""
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    chat = MagicMock(spec=Chat)
    user = MagicMock(spec=User)
    
    # Configure the mock objects
    chat.id = 123456789
    user.id = 987654321
    user.first_name = "Test User"
    message.chat = chat
    message.from_user = user
    message.text = "/start"
    message.reply_text = AsyncMock()
    update.message = message
    update.effective_chat = chat
    update.effective_user = user
    
    return update

@pytest.fixture
def mock_context():
    """Create a mock context for Telegram handlers."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock(return_value=True)
    return context

@pytest.fixture
def test_app():
    """Create a test instance of the FastAPI application."""
    return app

@pytest.fixture
def test_client(test_app):
    """Create a test client for the FastAPI application."""
    # Use httpx AsyncClient with ASGITransport
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=test_app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)

@pytest.fixture
async def async_client(test_app):
    """Create an async test client for the FastAPI application."""
    # Create a new AsyncClient with proper configuration using ASGITransport
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        yield client

@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    mock_client = AsyncMock(spec=Redis)
    # Configure basic Redis operations
    mock_client.get = AsyncMock(return_value=json.dumps({
        "status": "completed",
        "result": {
            "title": "Test Product",
            "price": 99.99,
            "value_score": 0.75,
            "analysis": {
                "pros": ["Good quality", "Fast delivery"],
                "cons": ["Expensive"],
                "sentiment_score": 0.8
            }
        }
    }).encode())
    mock_client.set = AsyncMock(return_value=True)
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.info = AsyncMock(return_value={"redis_version": "6.0.0"})
    
    # Configure queue operations
    mock_client.lpush = AsyncMock(return_value=1)
    mock_client.brpop = AsyncMock(return_value=(b'tasks', json.dumps({
        'id': 'task-123',
        'type': 'product_analysis',
        'data': {
            'url': 'https://example.com/product',
            'chat_id': 123456789
        }
    }).encode()))
    
    # Configure Redis connection and context manager
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    # Add close method as AsyncMock
    mock_client.close = AsyncMock()
    
    # Mock the from_url class method
    Redis.from_url = AsyncMock(return_value=mock_client)
    
    yield mock_client
    # No need for cleanup in finally block as we've mocked the close method

@pytest.fixture
def mock_telegram_bot():
    """Create a mock Telegram bot for testing."""
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=True)
    mock_bot.reply_text = AsyncMock()
    return mock_bot

@pytest.fixture
def mock_worker():
    """Create a mock worker for testing."""
    worker = TaskWorker()
    worker.process_task = AsyncMock(return_value={"status": "completed"})
    worker.notify_completion = AsyncMock(return_value=True)
    return worker

@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client for testing external API calls."""
    mock_client = AsyncMock()
    mock_client.post.return_value = AsyncMock(
        status_code=200,
        json=AsyncMock(return_value={"result": "success"})
    )
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client