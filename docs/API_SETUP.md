# API Keys Setup Guide for WorthIt!

## Required Services

To run WorthIt!, you need to register for the following services and obtain their API keys:

### 1. Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow the prompts to create your bot
4. Copy the provided API token

### 2. Apify Token (for Web Scraping)
1. Go to [Apify](https://apify.com/)
2. Sign up for a free account
3. Navigate to Account Settings > Integrations
4. Copy your API token

### 3. Hugging Face Token (for ML Features)
1. Create an account at [Hugging Face](https://huggingface.co/)
2. Go to Settings > Access Tokens
3. Create a new token with read access
4. Copy the generated token

## Configuration

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` and add your tokens:
```env
TELEGRAM_TOKEN=your_telegram_bot_token
APIFY_TOKEN=your_apify_token
HF_TOKEN=your_huggingface_token
```

## Verifying Setup

1. Run the health check endpoint:
```bash
curl http://localhost:8000/health
```

2. Test the bot:
- Send a message to your bot
- Try the product analysis feature

## Usage Limits

### Free Tier Limits
- Apify: $5 monthly credit
- Hugging Face: Rate limits vary by model
- Telegram: No specific limits for bot API

### Scaling Considerations
- Monitor API usage
- Set up usage alerts
- Consider upgrading to paid tiers for production use