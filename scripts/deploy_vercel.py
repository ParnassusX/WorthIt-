import os
import requests
from dotenv import load_dotenv
import time

def wait_for_deployment(vercel_url: str, max_retries: int = 10, delay: int = 5) -> bool:
    """Wait for the Vercel deployment to be ready"""
    for i in range(max_retries):
        try:
            response = requests.get(f"https://{vercel_url}/health")
            if response.status_code == 200:
                return True
        except:
            pass
        print(f"Waiting for deployment... ({i + 1}/{max_retries})")
        time.sleep(delay)
    return False

def setup_webhook():
    """Setup Telegram webhook after deployment"""
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable is not set")
    
    vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
    
    # Wait for deployment to be ready
    print("Checking deployment status...")
    if not wait_for_deployment(vercel_url):
        raise Exception("Deployment not ready after maximum retries")
    
    # Setup webhook
    webhook_url = f"https://{vercel_url}/webhook"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    
    # Delete any existing webhook
    requests.post(f"https://api.telegram.org/bot{token}/deleteWebhook")
    
    # Set the new webhook with additional parameters
    response = requests.post(api_url, json={
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True
    })
    result = response.json()
    
    if response.status_code == 200 and result.get("ok"):
        print(f"✅ Webhook successfully set to: {webhook_url}")
        
        # Verify webhook info
        info_response = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo")
        info = info_response.json()
        if info.get("ok"):
            webhook_info = info["result"]
            print("\nWebhook Info:")
            print(f"URL: {webhook_info.get('url')}")
            print(f"Pending updates: {webhook_info.get('pending_update_count')}")
            if webhook_info.get('last_error_message'):
                print(f"⚠️ Last error: {webhook_info.get('last_error_message')}")
    else:
        raise Exception(f"Failed to set webhook: {result.get('description')}")

if __name__ == "__main__":
    try:
        setup_webhook()
    except Exception as e:
        print(f"❌ Error: {str(e)}")