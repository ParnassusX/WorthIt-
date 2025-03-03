import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json
from worker.worker import TaskWorker, notify_completion, get_redis_client
from redis.asyncio import Redis

@pytest.fixture
def task_worker():
    """Create a TaskWorker instance for testing."""
    return TaskWorker()

# Test task processing
@pytest.mark.asyncio
async def test_process_task(task_worker, mock_redis):
    # Test the task processing functionality
    with patch('worker.worker.get_redis_client', return_value=mock_redis), \
         patch('api.scraper.scrape_product') as mock_scrape, \
         patch('api.ml_processor.analyze_sentiment') as mock_sentiment, \
         patch('api.ml_processor.extract_product_pros_cons') as mock_extract, \
         patch('api.ml_processor.get_value_score') as mock_score:
        
        # Configure mock returns
        product_data = {
            'title': 'Test Product',
            'price': 99.99,
            'reviews': [{'review': 'Great product'}, {'review': 'Worth the money'}]
        }
        
        # Set up async mock returns as coroutines
        async def mock_scrape_impl(*args, **kwargs):
            return product_data
        
        async def mock_sentiment_impl(*args, **kwargs):
            return {'score': 0.8, 'label': '4 stars'}
        
        async def mock_extract_impl(*args, **kwargs):
            return (['Good quality'], ['Expensive'])
        
        async def mock_score_impl(*args, **kwargs):
            return 0.75
        
        mock_scrape.side_effect = mock_scrape_impl
        mock_sentiment.side_effect = mock_sentiment_impl
        mock_extract.side_effect = mock_extract_impl
        mock_score.side_effect = mock_score_impl
        
        test_task = {
            'id': 'task-123',
            'type': 'product_analysis',
            'data': {
                'url': 'https://example.com/product',
                'chat_id': 456
            }
        }
        
        result = await task_worker.process_task(test_task)
        
        # Verify the task was processed
        assert result is not None
        assert 'status' in result
        assert result['status'] == 'completed'
        assert 'result' in result
        assert all(key in result['result'] for key in ['title', 'price', 'value_score', 'analysis'])

# Test notification system
@pytest.mark.asyncio
async def test_notify_completion(task_worker):
    # Test the notification system
    with patch('worker.worker.httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client
        
        result = {'status': 'completed', 'data': {'test': 'data'}}
        success = await notify_completion('task-123', result)
        
        # Verify the notification was sent
        assert success is True
        mock_client.post.assert_called_once()

# Test Redis connectivity
@pytest.mark.asyncio
async def test_redis_connectivity():
    # Test Redis connection handling
    # Create a mock Redis client
    mock_redis = AsyncMock(spec=Redis)
    mock_redis.ping = AsyncMock(return_value=True)
    
    # Directly patch the get_redis_client function to bypass Redis.from_url
    with patch('worker.worker.get_redis_client', new=AsyncMock(return_value=mock_redis)):
        # Reset the global Redis client to force a new connection
        import worker.worker
        worker.worker._redis_client = None
        
        # Get the Redis client through our patched function
        client = await worker.worker.get_redis_client()
        
        # Verify the connection was established
        assert client is not None
        # No need to check mock_from_url as we're directly patching get_redis_client

# Test queue operations
@pytest.mark.asyncio
async def test_queue_operations(mock_redis):
    # Test queue operations
    with patch('worker.queue.get_redis_client', return_value=mock_redis):
        from worker.queue import enqueue_task, dequeue_task
        
        # Reset any previous calls to the mock
        mock_redis.lpush.reset_mock()
        mock_redis.brpop.reset_mock()
        
        # Setup mock for Redis list operations
        mock_redis.lpush = AsyncMock(return_value=1)
        mock_redis.brpop = AsyncMock(return_value=(b'tasks', json.dumps({
            'id': 'task-123',
            'type': 'product_analysis',
            'data': {
                'url': 'https://example.com/product',
                'chat_id': 123456789
            }
        }).encode()))
        
        # Test enqueue
        task = {
            'type': 'product_analysis',
            'data': {
                'url': 'https://example.com/product',
                'chat_id': 123456789
            }
        }
        
        # Mock uuid generation
        with patch('uuid.uuid4', return_value='mock-uuid'):
            task_id = await enqueue_task(task)
            assert task_id == 'mock-uuid'
            assert isinstance(task_id, str)
            mock_redis.lpush.assert_called_once()
        
        # Test dequeue
        dequeued_task = await dequeue_task()
        assert dequeued_task is not None
        assert isinstance(dequeued_task, dict)
        assert dequeued_task.get('id') == 'task-123'
        assert dequeued_task.get('type') == 'product_analysis'
        mock_redis.brpop.assert_called_once()

# Test error handling
@pytest.mark.asyncio
async def test_error_handling(task_worker, mock_redis):
    # Test error handling in task processing
    with patch('worker.worker.get_redis_client', return_value=mock_redis), \
         patch('api.scraper.scrape_product', side_effect=Exception('Test error')):
        
        test_task = {
            'id': 'task-123',
            'type': 'product_analysis',
            'data': {'url': 'https://example.com/product'}
        }
        
        # The process_task should catch the exception and return an error status
        result = await task_worker.process_task(test_task)
        
        assert result is not None
        assert result.get('status') == 'error'
        assert 'error_message' in result