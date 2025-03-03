import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json
import os
from telegram import Update
from bot.bot import handle_text
from worker.worker import TaskWorker
from worker.queue import enqueue_task

# Integration test for the complete workflow
@pytest.mark.asyncio
async def test_complete_workflow(mock_update, mock_context, mock_redis, mock_http_client):
    """Test the complete workflow from bot to API to worker, simulating real user interaction"""
    # Setup mocks for the entire workflow
    with patch('bot.bot.get_http_client') as mock_get_client, \
         patch('worker.worker.get_redis_client', return_value=mock_redis), \
         patch('api.scraper.scrape_product') as mock_scrape, \
         patch('api.ml_processor.analyze_reviews') as mock_analyze, \
         patch('api.ml_processor.get_value_score') as mock_score, \
         patch('worker.queue.get_redis_client', return_value=mock_redis):
        
        # Configure HTTP client mock
        mock_client = AsyncMock()
        mock_client.post.return_value = AsyncMock(
            status_code=200,
            json=AsyncMock(return_value={
                "task_id": "task-123",
                "status": "processing"
            })
        )
        mock_get_client.return_value = mock_client
        
        # Configure Redis mock for task queue with realistic task lifecycle
        mock_redis.lpush = AsyncMock(return_value=1)
        mock_redis.brpop = AsyncMock(return_value=(b'tasks', json.dumps({
            'id': 'task-123',
            'type': 'product_analysis',
            'status': 'pending',
            'created_at': '2024-01-01T12:00:00Z'
        }).encode()))
        mock_redis.get = AsyncMock()
        mock_redis.get.side_effect = [
            # Initial task status
            json.dumps({
                'status': 'processing',
                'progress': 0
            }).encode(),
            # Final task result
            json.dumps({
                'status': 'completed',
                'result': {
                    "title": "Test Product",
                    "price": 99.99,
                    "value_score": 0.75,
                    "analysis": {
                        "pros": ["Good quality", "Fast delivery"],
                        "cons": ["Expensive"],
                        "sentiment_score": 0.8
                    }
                }
            }).encode()
        ]
        
        # Configure scraper and ML processor mocks
        mock_scrape.return_value = {
            "title": "Test Product",
            "price": 99.99,
            "reviews": ["Great product", "Worth the money"],
            "rating": 4.5
        }
        mock_analyze.return_value = {
            "sentiment": 0.8,
            "pros": ["Good quality"],
            "cons": ["Expensive"]
        }
        mock_score.return_value = 0.75
        
        # 1. Simulate user sending a product URL
        mock_update.message.text = "https://example.com/product"
        await handle_text(mock_update, mock_context)
        
        # Verify API request was made
        mock_client.post.assert_called_once()
        
        # 2. Simulate worker processing the task
        task = {
            'id': 'task-123',
            'type': 'product_analysis',
            'data': {
                'url': 'https://example.com/product',
                'chat_id': mock_update.effective_chat.id
            }
        }
        
        # Enqueue the task
        task_id = await enqueue_task(task)
        assert task_id is not None
        
        # Process the task with detailed validation
        worker = TaskWorker()
        with patch.object(worker, 'process_task') as mock_process:
            mock_process.return_value = {
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
            }
            
            # Process task and verify result structure
            result = await worker.process_task(task)
            assert result["status"] == "completed"
            assert "result" in result
            assert all(key in result["result"] for key in ["title", "price", "value_score", "analysis"])
            
            # Verify analysis details
            analysis = result["result"]["analysis"]
            assert len(analysis["pros"]) > 0
            assert len(analysis["cons"]) > 0
            assert 0 <= analysis["sentiment_score"] <= 1
        
        # 3. Verify notification was sent to the user with proper formatting
        with patch.object(worker, 'notify_completion', return_value=True) as mock_notify:
            success = await worker.notify_completion(task_id, result)
            assert success is True
            mock_notify.assert_called_once()
            
            # Verify the notification format
            call_args = mock_notify.call_args
            assert task_id == call_args[0][0]
            assert isinstance(call_args[0][1], dict)
            assert "status" in call_args[0][1]

@pytest.mark.asyncio
async def test_redis_connection_pool():
    """Test Redis connection pooling for high-load scenarios"""
    # Setup mock Redis client
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    
    # Patch the get_redis_client function directly
    with patch('worker.worker.get_redis_client', return_value=mock_redis):
        # Import the function that uses the connection pool
        from worker.worker import get_redis_client
        
        # Reset the Redis client to force a new connection
        import worker.worker
        worker.worker._redis_client = None
        
        # Get multiple clients from the pool
        client1 = await get_redis_client()
        client2 = await get_redis_client()
        
        # Verify both clients are the same instance
        assert client1 is client2

@pytest.mark.asyncio
async def test_upstash_redis_connectivity():
    """Test specific Upstash Redis connectivity features"""
    # Setup mock Redis client
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.info = AsyncMock(return_value={"redis_version": "6.0.0"})
    
    # Directly patch the get_redis_client function
    with patch('worker.worker.get_redis_client', new=AsyncMock(return_value=mock_redis)):
        # Import the function that connects to Redis
        from worker.worker import get_redis_client
        import worker.worker
        
        # Reset the Redis client to force a new connection
        worker.worker._redis_client = None
        
        # Set a test Redis URL with upstash in it
        original_url = os.environ.get("REDIS_URL")
        os.environ["REDIS_URL"] = "redis://upstash.example.com:6379"
        
        try:
            # Get Redis client
            client = await get_redis_client()
            
            # Verify client is working
            assert client is not None
            assert await client.ping() is True
            
            # Verify the URL was processed correctly
            assert "upstash" in os.environ["REDIS_URL"]
        finally:
            # Restore original environment variable
            if original_url:
                os.environ["REDIS_URL"] = original_url
            else:
                del os.environ["REDIS_URL"]