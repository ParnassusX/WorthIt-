import pytest
import asyncio
import os
import json
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes

# Import components from different parts of the system
from bot.bot import analyze_product_url, format_analysis_response
from api.scraper import scrape_product
from api.ml_processor import analyze_sentiment, extract_product_pros_cons, get_value_score
from worker.queue import enqueue_task, get_task_by_id
from worker.tasks import process_product_analysis_task

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
    message.text = "https://www.amazon.com/dp/B08N5KWB9H"
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
def mock_product_data():
    """Mock product data for testing."""
    return {
        "title": "Test Product",
        "price": "$99.99",
        "rating": 4.5,
        "reviews": [
            {"review": "Great product!", "rating": 5},
            {"review": "Worth the money", "rating": 4},
            {"review": "Fast shipping", "rating": 5},
            {"review": "Good quality but expensive", "rating": 3}
        ],
        "url": "https://example.com/product"
    }

@pytest.mark.asyncio
async def test_product_analysis_pipeline_integration(mock_update, mock_context, mock_product_data):
    """Test the complete product analysis pipeline from URL to user response."""
    # Mock the scraper to return test product data
    with patch('api.scraper.scrape_product', return_value=mock_product_data):
        # Mock sentiment analysis to return a test sentiment score
        with patch('api.ml_processor.analyze_sentiment', return_value=0.8):
            # Mock pros/cons extraction
            pros_cons = {
                "pros": ["Good quality", "Fast shipping"],
                "cons": ["Expensive"]
            }
            with patch('api.ml_processor.extract_product_pros_cons', return_value=(pros_cons["pros"], pros_cons["cons"])):
                # Mock value score calculation
                with patch('api.ml_processor.get_value_score', return_value=0.75):
                    # Test direct API call path
                    with patch('bot.bot.direct_api_call') as mock_direct_api:
                        # Configure the mock to simulate a successful API response
                        mock_api_response = {
                            "title": mock_product_data["title"],
                            "price": mock_product_data["price"],
                            "value_score": 0.75,
                            "analysis": {
                                "pros": pros_cons["pros"],
                                "cons": pros_cons["cons"]
                            }
                        }
                        mock_direct_api.return_value = mock_api_response
                        
                        # Call the analyze_product_url function
                        url = "https://www.amazon.com/dp/B08N5KWB9H"
                        result = await analyze_product_url(mock_update, url)
                        
                        # Verify that the message was sent to the user
                        mock_update.message.reply_text.assert_called()
                        
                        # Verify the result contains the expected data
                        assert result is not None
                        
                        # Test the worker queue path by mocking the queue
                        with patch('worker.queue.enqueue_task') as mock_enqueue:
                            # Reset the reply_text mock
                            mock_update.message.reply_text.reset_mock()
                            
                            # Set testing environment variable to false to use the queue
                            os.environ['TESTING'] = 'false'
                            
                            # Call the analyze_product_url function again
                            result = await analyze_product_url(mock_update, url)
                            
                            # Verify that enqueue_task was called
                            mock_enqueue.assert_called_once()
                            
                            # Verify that the initial message was sent
                            assert mock_update.message.reply_text.call_count > 0
                            
                            # Reset environment variable
                            os.environ['TESTING'] = 'true'

@pytest.mark.asyncio
async def test_worker_task_processing(mock_update, mock_product_data):
    """Test that the worker properly processes tasks and sends results back to users."""
    # Mock Redis client
    with patch('worker.queue.get_redis_client') as mock_redis_client:
        # Mock the bot instance
        with patch('worker.tasks.get_bot_instance') as mock_get_bot:
            bot_instance = MagicMock()
            bot_instance.send_message = AsyncMock()
            mock_get_bot.return_value = bot_instance
            
            # Mock scraper and ML processor
            with patch('api.scraper.scrape_product', return_value=mock_product_data):
                with patch('api.ml_processor.analyze_sentiment', return_value=0.8):
                    pros = ["Good quality", "Fast shipping"]
                    cons = ["Expensive"]
                    with patch('api.ml_processor.extract_product_pros_cons', return_value=(pros, cons)):
                        with patch('api.ml_processor.get_value_score', return_value=0.75):
                            # Create a task
                            task_data = {
                                'url': 'https://www.amazon.com/dp/B08N5KWB9H',
                                'chat_id': mock_update.effective_chat.id
                            }
                            
                            # Process the task
                            await process_product_analysis_task(task_data)
                            
                            # Verify that the bot sent a message with the analysis
                            bot_instance.send_message.assert_called_once()
                            
                            # Check that the message contains the analysis results
                            call_args = bot_instance.send_message.call_args[0]
                            message_text = call_args[1]
                            assert "Test Product" in message_text
                            assert "$99.99" in message_text
                            assert "Good quality" in message_text
                            assert "Expensive" in message_text

@pytest.mark.asyncio
async def test_format_analysis_response():
    """Test that the analysis response is properly formatted for the user."""
    # Create a sample analysis result
    analysis_result = {
        "title": "Test Product",
        "price": "$99.99",
        "value_score": 0.75,
        "analysis": {
            "pros": ["Good quality", "Fast shipping"],
            "cons": ["Expensive"]
        }
    }
    
    # Format the response
    formatted_response = format_analysis_response(analysis_result)
    
    # Verify the formatted response contains all the necessary information
    assert "Test Product" in formatted_response
    assert "$99.99" in formatted_response
    assert "75%" in formatted_response  # Value score as percentage
    assert "Good quality" in formatted_response
    assert "Fast shipping" in formatted_response
    assert "Expensive" in formatted_response

if __name__ == "__main__":
    pytest.main()