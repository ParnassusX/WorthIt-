import os
import requests
from dotenv import load_dotenv

def activate_webhook():
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_TOKEN environment variable is not set")
    
    vercel_url = os.getenv("VERCEL_URL", "worth-it-bot-git-main-parnassusxs-projects.vercel.app")
    webhook_url = f"https://{vercel_url}/webhook"
    
    # Telegram API endpoint for setting webhook
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    
    # Set the webhook
    response = requests.post(api_url, json={"url": webhook_url})
    result = response.json()
    
    if response.status_code == 200 and result.get("ok"):
        print(f"✅ Webhook successfully set to: {webhook_url}")
    else:
        print(f"❌ Failed to set webhook: {result.get('description')}")

if __name__ == "__main__":
    activate_webhook()