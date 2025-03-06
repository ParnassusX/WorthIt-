# WorthIt! Bot

A Telegram bot that analyzes product links and tells you if they're worth buying based on reviews, price, and features.

## Setup Instructions

### Environment Variables

The bot requires several API keys to function properly. Create a `.env` file in the root directory with the following variables:

```
# Telegram Bot Token (from BotFather)
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Apify Token for Web Scraping
# Get this from https://apify.com/
APIFY_TOKEN=your_apify_token_here

# Hugging Face Token for AI Models
# Get this from https://huggingface.co/settings/tokens
HF_TOKEN=your_huggingface_token_here

# Optional: Vercel URL (set automatically in production)
# VERCEL_URL=your-app-name.vercel.app
```

### Common Issues

#### 401 Unauthorized Error

If you're seeing a 401 error when analyzing products, check that:

1. Your `APIFY_TOKEN` is correctly set in the `.env` file
2. Your `HF_TOKEN` is correctly set in the `.env` file
3. Both tokens are valid and have not expired

#### Event Loop Errors

If you encounter "Event loop is closed" errors, this has been fixed in the latest update. Make sure you're running the latest version of the code.

## Testing

### Running Tests

1. Install test dependencies: `pip install -r requirements.txt`
2. Create a `.env.test` file with mock tokens for testing
3. Run tests with pytest: `pytest tests/`

### Test Structure

The project uses pytest with async support:

- `tests/unit/` - Unit tests for API endpoints and components
- `tests/conftest.py` - Shared fixtures including async client setup

For more details, see the [Testing Structure](docs/TESTING_STRUCTURE.md) documentation.

## Deployment

### Local Development

1. Install dependencies: `pip install -r requirements.txt`
2. Set up your `.env` file as described above
3. Run the API: `uvicorn api.main:app --reload`
4. For testing the bot locally, use a tool like ngrok to expose your local server



## Features

- Product analysis based on reviews and features
- Value score calculation
- Pros and cons extraction
- Price comparison (coming soon)
- Sharing analysis with friends

## Supported Sites

Currently supports:
- Amazon
- eBay (partial support)

More sites coming soon!