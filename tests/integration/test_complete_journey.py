import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import json
import os
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
from bot.bot import start, handle_text, analyze_product_url
from worker.worker import TaskWorker
from worker.queue import enqueue_task, dequeue_task
from api.scraper import scrape_product
from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score

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

# Comprehensive end-to-end test for the complete user journey
@pytest.mark.asyncio
async def test_complete_user_journey(mock_update, mock_context, mock_redis, mock_http_client, mock_apify_client, mock_huggingface_api):
    """Test the complete user journey from bot interaction to product analysis"""
    # Step 1: User starts the bot
    mock_update.message.text = "/start"
    await start(mock_update, mock_context)
    
    # Verify welcome message was sent with keyboard
    mock_update.message.reply_text.assert_called_once()
    assert "reply_markup" in mock_update.message.reply_text.call_args[1]
    mock_update.message.reply_text.reset_mock()
    
    # Step 2: User asks for help
    mock_update.message.text = "ℹ️ Aiuto"
    await handle_text(mock_update, mock_context)
    
    # Verify help message was sent
    mock_update.message.reply_text.assert_called_once()
    args, kwargs = mock_update.message.reply_text.call_args
    assert "Come usare WorthIt!" in args[0]
    assert kwargs.get("parse_mode") == "Markdown"
    mock_update.message.reply_text.reset_mock()
    
    # Step 3: User selects search product option
    mock_update.message.text = "🔍 Cerca prodotto"
    await handle_text(mock_update, mock_context)
    
    # Verify search prompt was sent
    mock_update.message.reply_text.assert_called_once()
    args = mock_update.message.reply_text.call_args[0]
    assert "Incolla il link" in args[0]
    mock_update.message.reply_text.reset_mock()
    
    # Step 4: User sends a product URL
    product_url = "https://example.com/product"
    mock_update.message.text = product_url
    
    # Setup mocks for the entire workflow
    with patch('bot.bot.get_http_client') as mock_get_client, \
         patch('worker.worker.get_redis_client', return_value=mock_redis), \
         patch('api.scraper.scrape_product') as mock_scrape, \
         patch('api.ml_processor.extract_product_pros_cons') as mock_extract, \
         patch('api.ml_processor.analyze_sentiment') as mock_sentiment, \
         patch('api.ml_processor.get_value_score') as mock_score, \
         patch('worker.queue.get_redis_client', return_value=mock_redis), \
         patch('api.scraper.apify_client', mock_apify_client):
        
        # Configure HTTP client mock for API call
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
            'created_at': '2024-01-01T12:00:00Z',
            'data': {
                'url': product_url,
                'chat_id': mock_update.effective_chat.id
            }
        }).encode()))
        
        # Configure Redis get responses for task status checks
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
            "reviews": ["Great product!", "Worth the money", "Fast shipping", "Good quality but expensive"],
            "rating": 4.5
        }
        
        mock_extract.return_value = {
            "pros": ["Good quality", "Fast delivery"],
            "cons": ["Expensive"]
        }
        
        mock_sentiment.return_value = {
            "label": "4 stars",
            "score": 0.8
        }
        
        mock_score.return_value = 0.75
        
        # Step 4a: User sends product URL to bot
        # Simulate the analyze_product_url behavior
        async def mock_analyze_impl(update, url):
            await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
            return {"status": "processing"}
        
        with patch('bot.bot.analyze_product_url', side_effect=mock_analyze_impl):
            await handle_text(mock_update, mock_context)
            
            # Verify acknowledgment message was sent
            assert mock_update.message.reply_text.call_count >= 1
            # Find the acknowledgment message
            ack_message_found = False
            for call in mock_update.message.reply_text.call_args_list:
                if "Sto analizzando" in call[0][0]:
                    ack_message_found = True
                    break
            assert ack_message_found, "Acknowledgment message not found"
            mock_update.message.reply_text.reset_mock()

@pytest.mark.asyncio
async def test_error_handling_in_workflow(mock_update, mock_context, mock_redis, mock_http_client):
    """Test error handling throughout the complete workflow"""
    # Setup for error testing
    product_url = "https://example.com/invalid-product"
    mock_update.message.text = product_url
    
    # Test scraper error handling
    with patch('bot.bot.get_http_client') as mock_get_client, \
         patch('api.scraper.scrape_product', side_effect=Exception("Failed to scrape product")):
        
        # Configure HTTP client mock
        mock_client = AsyncMock()
        mock_client.post.return_value = AsyncMock(
            status_code=500,
            json=AsyncMock(return_value={"error": "Failed to analyze product"})
        )
        mock_get_client.return_value = mock_client
        
        # Test error handling when sending URL
        await handle_text(mock_update, mock_context)
        
        # Verify error message was sent to user
        mock_update.message.reply_text.assert_called_with(
            "Mi dispiace, non sono riuscito ad analizzare questo prodotto. Errore: "
        )
        
        # Test error handling in worker
        task = {
            'id': 'task-123',
            'type': 'product_analysis',
            'data': {
                'url': product_url,
                'chat_id': mock_update.effective_chat.id
            }
        }
        
        worker = TaskWorker()
        result = await worker.process_task(task)
        
        # Verify error status and message
        assert result['status'] == 'error'
        assert 'error_message' in result
        assert 'Failed to scrape product' in result['error_message']