import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
from redis.asyncio import Redis
from bot.bot import WorthItBot
from worker.worker import TaskWorker

# Shared test data
SAMPLE_PRODUCT_DATA = {
    "title": "Test Product",
    "price": 99.99,
    "value_score": 0.75,
    "analysis": {
        "pros": ["Good quality", "Fast delivery"],
        "cons": ["Expensive"],
        "sentiment_score": 0.8
    }
}

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_update():
    """Create a mock Telegram update object with all necessary attributes."""
    update = MagicMock(spec=Update)
    message = MagicMock(spec=Message)
    chat = MagicMock(spec=Chat)
    user = MagicMock(spec=User)
    
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
    """Create a mock context for Telegram handlers with all necessary methods."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock(return_value=True)
    context.bot.reply_text = AsyncMock()
    return context

@pytest.fixture
async def mock_redis():
    """Create a comprehensive mock Redis client for testing with all required operations."""
    mock_client = AsyncMock(spec=Redis)
    
    # Configure basic Redis operations
    mock_client.get = AsyncMock(return_value=json.dumps(SAMPLE_PRODUCT_DATA).encode())
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
def mock_http_client():
    """Create a mock HTTP client for testing external API calls with proper async support."""
    mock_client = AsyncMock()
    mock_client.post.return_value = AsyncMock(
        status_code=200,
        json=AsyncMock(return_value={
            "task_id": "task-123",
            "status": "processing",
            "result": SAMPLE_PRODUCT_DATA
        })
    )
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client

@pytest.fixture
def mock_worker():
    """Create a mock worker with proper async task processing capabilities."""
    worker = TaskWorker()
    worker.process_task = AsyncMock(return_value={
        "status": "completed",
        "result": SAMPLE_PRODUCT_DATA
    })
    worker.notify_completion = AsyncMock(return_value=True)
    return worker

@pytest.fixture
def mock_bot():
    """Create a mock bot instance with all required async methods."""
    bot = WorthItBot('test_token')
    bot.send_message = AsyncMock(return_value=True)
    bot.reply_text = AsyncMock()
    return bot

@pytest.fixture
def sample_task():
    """Create a sample task with all required fields."""
    return {
        'id': 'task-123',
        'type': 'product_analysis',
        'data': {
            'url': 'https://example.com/product',
            'chat_id': 123456789
        }
    }