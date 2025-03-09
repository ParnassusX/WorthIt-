# WorthIt! Bot 🛒💰

A Telegram bot that analyzes product links and tells you if they're worth buying based on reviews, price, and features.

![WorthIt! Bot](https://img.shields.io/badge/WorthIt!-Bot-blue)
![Netlify](https://img.shields.io/badge/Netlify-Deployed-success)
![Redis](https://img.shields.io/badge/Upstash-Redis-red)

## 🌟 Features

- **Product Analysis**: Get detailed insights on products from reviews and features
- **Value Score**: Understand if a product is worth its price with our proprietary scoring system
- **Pros & Cons**: Automatically extracted from reviews and product descriptions
- **Price Comparison**: Compare with similar products (coming soon)
- **Sharing**: Share analysis results with friends
- **Web App Integration**: Scan products with your camera

## 🚀 Supported Sites

Currently supports:
- Amazon
- eBay (partial support)

More sites coming soon!

## 🛠️ Setup Instructions

### Environment Variables

The bot requires several API keys to function properly. Create a `.env` file in the root directory with the following variables:

```env
# Telegram Bot Token (from BotFather)
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Supabase Configuration
SUPABASE_URL=your_supabase_url_here
SUPABASE_KEY=your_supabase_key_here

# Apify Token for Web Scraping
# Get this from https://apify.com/ (free tier includes $5 monthly credit)
APIFY_TOKEN=your_apify_token_here

# Hugging Face Token for AI Models
# Get this from https://huggingface.co/settings/tokens
HF_TOKEN=your_huggingface_token_here

# Redis URL for caching and task queue
# For local development: redis://localhost:6379
# For production: Use Upstash Redis URL with rediss:// protocol
REDIS_URL=your_redis_url_here

# Webhook URL (set automatically in production)
WEBHOOK_URL=https://your-app.netlify.app/webhook
API_HOST=https://your-app.netlify.app/api
```

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up your `.env` file as described above

3. Run the API:
   ```bash
   uvicorn api.main:app --reload
   ```

4. For testing the bot locally:
   ```bash
   python run_bot_local.py
   ```

5. For local webhook testing, use a tool like ngrok to expose your local server

### Redis Setup

WorthIt! uses Redis for caching and task queue management. For production, we recommend using Upstash Redis:

1. Follow the [Upstash Setup Guide](docs/UPSTASH_SETUP.md)
2. Make sure to use the `rediss://` protocol for SSL connections

## 🧪 Testing

### Running Tests

1. Install test dependencies: `pip install -r requirements.txt`
2. Create a `.env.test` file with mock tokens for testing
3. Run tests with pytest: `pytest tests/`

### Test Structure

The project uses pytest with async support:

- `tests/unit/` - Unit tests for API endpoints and components
- `tests/integration/` - End-to-end tests for complete workflows
- `tests/conftest.py` - Shared fixtures including async client setup

For more details, see the [Testing Structure](docs/TESTING_STRUCTURE.md) documentation.

## 📚 Documentation

- [API Reference](docs/API_REFERENCE.md) - API endpoints and usage
- [Architecture](docs/ARCHITECTURE.md) - System architecture overview
- [Setup Guide](docs/SETUP_GUIDE.md) - Detailed setup instructions
- [Redis Troubleshooting](docs/REDIS_TROUBLESHOOTING.md) - Solving Redis connectivity issues
- [Upstash Setup](docs/UPSTASH_SETUP.md) - Setting up Upstash Redis

## 🚢 Deployment

WorthIt! uses a modern hybrid architecture:

1. **Webhook Handler**: Deployed on Netlify Serverless Functions for fast, scalable webhook processing
2. **Worker Service**: Hosted on Render Web Services for reliable background processing
3. **Database**: Supabase for structured data storage and real-time features
4. **Cache & Queue**: Upstash Redis for serverless-compatible caching and task queues
5. **Web App**: React-based frontend hosted on Netlify

Follow our comprehensive [Deployment Checklist](DEPLOYMENT_CHECKLIST.md) for a complete setup guide.

### Deployment Flow

1. Set up all required services (Netlify, Render, Supabase, Upstash)
2. Configure environment variables in each platform
3. Deploy webhook handler to Netlify
4. Deploy worker service to Render
5. Verify all connections and monitoring

For detailed instructions, see our [Architecture Guide](docs/ARCHITECTURE.md).

## 🔍 Common Issues

### 401 Unauthorized Error

If you're seeing a 401 error when analyzing products, check that:

1. Your `APIFY_TOKEN` is correctly set in the `.env` file
2. Your `HF_TOKEN` is correctly set in the `.env` file
3. Both tokens are valid and have not expired

### Redis Connection Issues

If you encounter Redis connection errors:

1. Check your Redis URL format (should use `rediss://` for Upstash)
2. Verify network connectivity
3. See [Redis Troubleshooting](docs/REDIS_TROUBLESHOOTING.md) for more solutions

## 📝 License

MIT