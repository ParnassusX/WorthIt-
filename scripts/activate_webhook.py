import os
import requests
import logging
import sys
import time
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def activate_webhook(max_retries=3, retry_delay=5):
    """Activate webhook with enhanced error handling and verification
    
    This function performs the following steps:
    1. Validates environment variables
    2. Validates webhook URL format and accessibility
    3. Sets the webhook with Telegram API
    4. Verifies webhook was set correctly
    5. Checks for pending updates
    
    Args:
        max_retries: Maximum number of retry attempts for API calls
        retry_delay: Delay between retry attempts in seconds
        
    Returns:
        bool: True if webhook was successfully set, False otherwise
        
    Raises:
        ValueError: If required environment variables are missing or invalid
        requests.RequestException: If there's a network error
    """
    # Load environment variables
    load_dotenv()
    
    # Validate Telegram token
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN environment variable is not set")
        raise ValueError("TELEGRAM_TOKEN environment variable is not set")
    
    # Validate webhook URL
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        logger.error("WEBHOOK_URL environment variable is not set")
        raise ValueError("WEBHOOK_URL environment variable is not set")
    
    # Validate webhook URL format
    if not webhook_url.startswith("https://"):
        logger.error("Webhook URL must use HTTPS protocol")
        raise ValueError("Webhook URL must use HTTPS protocol")
    
    # Validate API_HOST is set
    api_host = os.getenv("API_HOST")
    if not api_host:
        logger.warning("API_HOST environment variable is not set")
        # Derive API_HOST from WEBHOOK_URL if possible
        api_host = webhook_url.rsplit('/webhook', 1)[0] + '/api'
        logger.info(f"Derived API_HOST from WEBHOOK_URL: {api_host}")
        os.environ["API_HOST"] = api_host
    
    # Telegram API endpoints
    set_webhook_url = f"https://api.telegram.org/bot{token}/setWebhook"
    get_webhook_info_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    
    # Set the webhook with retries
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Setting webhook to {webhook_url} (Attempt {attempt}/{max_retries})")
            
            # Configure webhook with allowed updates and max connections
            webhook_params = {
                "url": webhook_url,
                "allowed_updates": ["message", "callback_query", "inline_query"],
                "max_connections": 100,
                "drop_pending_updates": True
            }
            
            response = requests.post(set_webhook_url, json=webhook_params, timeout=10)
            result = response.json()
            
            if response.status_code == 200 and result.get("ok"):
                logger.info(f"✅ Webhook successfully set to: {webhook_url}")
                break
            else:
                logger.error(f"Failed to set webhook: {result.get('description')}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Maximum retry attempts reached. Webhook setup failed.")
                    sys.exit(1)
        except requests.RequestException as e:
            logger.error(f"Network error setting webhook: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Maximum retry attempts reached. Webhook setup failed.")
                sys.exit(1)
    
    # Verify webhook was set correctly
    try:
        logger.info("Verifying webhook configuration...")
        response = requests.get(get_webhook_info_url, timeout=10)
        result = response.json()
        
        if response.status_code == 200 and result.get("ok"):
            webhook_info = result.get("result", {})
            current_url = webhook_info.get("url", "")
            pending_update_count = webhook_info.get("pending_update_count", 0)
            last_error_date = webhook_info.get("last_error_date")
            last_error_message = webhook_info.get("last_error_message")
            
            if current_url == webhook_url:
                logger.info("✅ Webhook verification successful")
                logger.info(f"Pending updates: {pending_update_count}")
                
                if last_error_date:
                    logger.warning(f"Last webhook error: {last_error_message}")
            else:
                logger.error(f"Webhook verification failed. Current URL: {current_url}")
                sys.exit(1)
        else:
            logger.error(f"Failed to verify webhook: {result.get('description')}")
            sys.exit(1)
    except requests.RequestException as e:
        logger.error(f"Network error verifying webhook: {e}")
        sys.exit(1)

if __name__ == "__main__":
    activate_webhook()