import pytest
from unittest.mock import MagicMock
from api import main
from bot import bot
from worker import worker

@pytest.fixture
def app_client():
    """Fixture for API test client"""
    app = main.app
    client = app.test_client()
    return client

@pytest.fixture
def mock_bot():
    """Fixture for mocked bot instance"""
    return bot.WorthItBot('test_token')

@pytest.fixture
def mock_worker():
    """Fixture for mocked worker instance"""
    return worker.TaskWorker()

@pytest.fixture
def mock_redis():
    """Fixture for mocked Redis client"""
    mock_redis_client = MagicMock()
    return mock_redis_client

@pytest.fixture
def mock_http_response():
    """Fixture for mocked HTTP response"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'ok': True}
    return mock_response

@pytest.fixture
def sample_task():
    """Fixture for a sample task"""
    return {
        'id': 'task-123',
        'type': 'product_analysis',
        'data': {
            'url': 'https://example.com/product',
            'user_id': 456
        }
    }

@pytest.fixture
def sample_message():
    """Fixture for a sample Telegram message"""
    return {
        'message_id': 123,
        'from': {'id': 456, 'first_name': 'Test User'},
        'chat': {'id': 789},
        'text': '/analyze https://example.com/product'
    }