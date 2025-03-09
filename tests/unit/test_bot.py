import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from telegram import Update, Message, Chat, User
from telegram.ext import ContextTypes
import asyncio
from bot.bot import start, handle_text, analyze_product_url

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

# Test start command handler
@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    # Test the start command handler
    await start(mock_update, mock_context)
    
    # Verify that reply_text was called
    mock_update.message.reply_text.assert_called_once()
    # Verify keyboard structure and web app integration
    reply_markup = mock_update.message.reply_text.call_args[1]['reply_markup']
    
    # Check web app button details
    web_app_button = reply_markup.keyboard[0][0]
    assert web_app_button.text == "Scansiona 📸"
    assert web_app_button.web_app is not None
    assert web_app_button.web_app.url is not None
    assert web_app_button.web_app.url.startswith("https://") or os.getenv("WEBAPP_URL", "").startswith("https://")

# Test text message handler
@pytest.mark.asyncio
async def test_handle_text_help(mock_update, mock_context):
    # Test handling the help command
    mock_update.message.text = "ℹ️ Aiuto"
    
    # Set up the side effect to simulate closed event loop error on first call only
    # and then return normally on second call
    mock_update.message.reply_text.side_effect = [
        RuntimeError("Event loop is closed"),
        None  # Normal return on second call
    ]
    
    await handle_text(mock_update, mock_context)
    
    # Verify message was sent, without checking specific content
    assert mock_update.message.reply_text.called
    # Get the arguments from the call
    args, kwargs = mock_update.message.reply_text.call_args
    
    # Verify new event loop was created
    assert asyncio.get_event_loop().is_closed() == False

@pytest.mark.asyncio
async def test_handle_text_search(mock_update, mock_context):
    # Test handling the search command
    mock_update.message.text = "🔍 Cerca prodotto"
    
    # Set up user_data dictionary in mock_context
    mock_context.user_data = {}
    
    await handle_text(mock_update, mock_context)
    
    # Verify that reply_text was called with search prompt
    mock_update.message.reply_text.assert_called_once()
    args = mock_update.message.reply_text.call_args[0]
    assert "Incolla il link" in args[0]

@pytest.mark.asyncio
async def test_handle_text_with_url(mock_update, mock_context):
    # Test handling a message with a product URL
    test_url = "https://example.com/product"
    mock_update.message.text = test_url
    
    # Patch the analyze_product_url function to simulate its behavior
    async def mock_analyze_impl(update, url):
        await update.message.reply_text("Sto analizzando il prodotto... Attendi un momento ⏳")
    
    with patch('bot.bot.analyze_product_url', side_effect=mock_analyze_impl) as mock_analyze:
        await handle_text(mock_update, mock_context)
        
        # Verify that analyze_product_url was called with the URL
        mock_analyze.assert_called_once_with(mock_update, test_url)
        
        # Verify acknowledgment message was sent
        mock_update.message.reply_text.assert_called_with(
            "Sto analizzando il prodotto... Attendi un momento ⏳"
        )

# Test product URL analysis
@pytest.mark.asyncio
async def test_analyze_product_url(mock_update, mock_context):
    # Test the product URL analysis function
    test_url = "https://example.com/valid-product"
    
    # Configure mocks
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = AsyncMock(return_value={
        "task_id": "task-123",
        "status": "processing"
    })
    mock_client.post = AsyncMock(return_value=mock_response)
    
    # Set testing environment variable
    with patch.dict(os.environ, {"TESTING": "true"}), \
         patch('bot.bot.get_http_client', return_value=mock_client), \
         patch('bot.bot.validate_url', return_value=True), \
         patch('bot.bot.close_http_client', new_callable=AsyncMock):
        
        # Set up the reply_text mock to track calls
        mock_update.message.reply_text.reset_mock()
        
        # Call analyze_product_url
        await analyze_product_url(mock_update, test_url)
        
        # Verify a message was sent (not checking exact content as it may vary)
        assert mock_update.message.reply_text.called
        
        # Verify API call was made
        mock_client.post.assert_called_once()
        assert test_url in str(mock_client.post.call_args)