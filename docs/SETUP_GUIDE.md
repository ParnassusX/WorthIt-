# WorthIt! Setup Guide

## Prerequisites
- Python 3.8 or higher
- Node.js 14 or higher (for web app)
- A Telegram Bot Token
- APIFY Token for web scraping
- Hugging Face Token for ML features
- Redis Cloud account for background task processing

## Environment Setup
1. Clone the repository
2. Copy `.env.example` to `.env`
3. Configure the following environment variables:

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_bot_token
WEBHOOK_URL=your_webhook_url

# API Tokens
APIFY_TOKEN=your_apify_token
HF_TOKEN=your_huggingface_token

# Redis Cloud Configuration
REDIS_URL=redis://default:A13fhd8gzadebwqq9cqaxkhrx7cxlhehhfjdct3ep62mgjqpfi2@redis-18843.c1.us-east1-2.gce.cloud.redislabs.com:18843

# Render.com API Configuration
RENDER_API_KEY=rnd_oW3VZXHpUJPzn6KLrzmgw9BJvyTt

# Deployment
VERCEL_URL=your_vercel_url
API_HOST=https://your_api_host
```

## Installation
1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install web app dependencies:
```bash
cd web-app
npm install
```

## Configuration

### Telegram Bot Setup
1. Create a new bot with @BotFather
2. Get your bot token
3. Set the webhook URL:
```bash
python scripts/activate_webhook.py
```

### Redis Cloud Setup
1. The Redis Cloud connection is already configured with the provided URL in your .env file
2. To start the background worker for processing tasks:
```bash
python -m worker.worker
```
3. The worker will connect to Redis Cloud and process tasks asynchronously

### Vercel Deployment
1. Install Vercel CLI:
```bash
npm i -g vercel
```

2. Deploy to Vercel:
```bash
python scripts/deploy_vercel.py
```

## Running Locally
1. Start the API server:
```bash
uvicorn api.main:app --reload
```

2. Start the web app (development mode):
```bash
cd web-app
npm run dev
```

## Troubleshooting

### Common Issues

1. **Event Loop Errors**
- Symptom: "Event loop is closed" errors
- Solution: These are expected in serverless environments and are handled gracefully

2. **API Authentication Errors**
- Check that APIFY_TOKEN and HF_TOKEN are correctly set
- Verify token permissions and quotas

3. **Webhook Issues**
- Ensure WEBHOOK_URL is correct and accessible
- Check Telegram bot token permissions

### Health Checks
- Use the `/health` endpoint to verify API status
- Monitor error rates and response times

## Development Guidelines
1. Follow the project's code style
2. Add tests for new features
3. Update documentation when making changes
4. Use meaningful commit messages

## Support
For support or to report issues, please open a GitHub issue in the repository.