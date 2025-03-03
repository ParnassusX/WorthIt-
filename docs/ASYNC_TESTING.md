# Async Testing in WorthIt!

## Overview

This document provides guidance on how to write and run asynchronous tests in the WorthIt! project. Our testing framework is built on pytest with async support, allowing us to properly test FastAPI endpoints and other asynchronous components.

## Test Client Setup

We use two types of test clients for FastAPI testing:

### 1. AsyncClient

The `async_client` fixture in `conftest.py` provides an asynchronous HTTP client for testing API endpoints:

```python
@pytest.fixture
async def async_client(test_app):
    """Create an async test client for the FastAPI application."""
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        yield client
```

Use this client in tests marked with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_sentiment_analysis(async_client):
    # Test async endpoint
    response = await async_client.post("/api/analyze/sentiment", json={"text": "Great product!"})
    assert response.status_code == 200
```

### 2. TestClient

The `test_client` fixture provides a synchronous client wrapper for simpler tests:

```python
@pytest.fixture
def test_client(test_app):
    """Create a test client for the FastAPI application."""
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=test_app)
    return AsyncClient(transport=transport, base_url="http://test", follow_redirects=True)
```

## Mock Fixtures

The project includes several mock fixtures to isolate tests from external dependencies:

### Redis Mock

```python
@pytest.fixture
async def mock_redis():
    """Create a mock Redis client for testing."""
    mock_client = AsyncMock(spec=Redis)
    # Configure mock methods
    mock_client.get = AsyncMock(return_value=json.dumps({...}).encode())
    # ...
    yield mock_client
```

### Telegram Bot Mock

```python
@pytest.fixture
def mock_telegram_bot():
    """Create a mock Telegram bot for testing."""
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=True)
    return mock_bot
```

## Testing Patterns

### 1. API Endpoint Testing

Test FastAPI endpoints using the async client:

```python
@pytest.mark.asyncio
async def test_health_check(test_client):
    response = await test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

### 2. Mocking External Services

Use `patch` to mock external service calls:

```python
@pytest.mark.asyncio
async def test_scraper(async_client):
    with patch('api.scraper.scrape_product') as mock_scraper:
        mock_scraper.return_value = {...}
        response = await async_client.post("/api/scrape", json={"url": "https://example.com"})
        assert response.status_code == 200
```

### 3. Testing Asynchronous Workers

Test worker processes using AsyncMock:

```python
@pytest.mark.asyncio
async def test_worker_process(mock_redis, mock_telegram_bot):
    worker = TaskWorker(redis_client=mock_redis, bot=mock_telegram_bot)
    result = await worker.process_task({"id": "task-123", "type": "analysis"})
    assert result["status"] == "completed"
```

## Best Practices

1. **Use `@pytest.mark.asyncio`** for all async tests
2. **Properly mock external services** to avoid actual API calls during testing
3. **Use `AsyncMock`** for mocking async functions
4. **Clean up resources** in fixture teardown (using `yield` and finalization code)
5. **Isolate tests** to prevent state sharing between test cases

## Common Issues

### Event Loop Issues

If you encounter "Event loop is closed" errors, ensure you're using the event_loop fixture:

```python
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

### Redis Connection Issues

For Redis testing issues, check that:
1. The mock_redis fixture is properly configured
2. All Redis operations are properly mocked
3. Connection cleanup is handled correctly

## Running Tests

Run the async test suite with:

```bash
pytest tests/ -v
```

To run specific test files:

```bash
pytest tests/unit/test_api.py -v
```

## Conclusion

Following these async testing patterns will ensure reliable and maintainable tests for the WorthIt! project's asynchronous components.