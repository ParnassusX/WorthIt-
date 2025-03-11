# WorthIt! Developer Guide

## Introduction
This guide provides comprehensive information for developers working on the WorthIt! application. It covers deployment processes, API documentation, troubleshooting, and best practices.

## Deployment Process

### Prerequisites
- Access to Netlify account
- Access to Upstash Redis account
- Telegram Bot API token
- Hugging Face API token
- Apify API token

### Deployment Steps

#### 1. Environment Configuration
Ensure all environment variables are properly set in Netlify:

```
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_bot_token
WEBHOOK_URL=https://worthit-app.netlify.app/webhook

# API Tokens
APIFY_TOKEN=your_apify_token
HF_TOKEN=your_huggingface_token

# Redis Configuration
REDIS_URL=rediss://default:your_password@your-database.upstash.io:6379

# API Configuration
API_HOST=https://worthit-app.netlify.app/api

# Payment Processing
STRIPE_API_KEY=your_stripe_key
PAYMENT_ENCRYPTION_KEY=your_encryption_key
PAYMENT_KEY_SALT=your_key_salt
```

#### 2. Netlify Deployment

1. Push code to GitHub repository
2. Connect repository to Netlify
3. Configure build settings:
   - Build command: `npm run build`
   - Publish directory: `web-app/dist`
   - Functions directory: `netlify/functions`

4. Deploy the application:
```bash
git push origin main  # Netlify will automatically deploy on push
```

Or manually deploy using Netlify CLI:
```bash
npx netlify deploy --prod
```

#### 3. Post-Deployment Verification

Run the post-deployment verification script:
```bash
python scripts/verify_deployment.py
```

This script checks:
- API endpoints accessibility
- Webhook registration with Telegram
- Redis connection
- Function deployment status

### Continuous Integration/Deployment

The project uses GitHub Actions for CI/CD:

1. Tests run on every pull request
2. Deployment to staging on merge to develop branch
3. Deployment to production on merge to main branch

Workflow file: `.github/workflows/deploy.yml`

## API Architecture

### Core Components

1. **API Layer** (`api/main.py`)
   - FastAPI application handling HTTP requests
   - Route definitions and middleware configuration

2. **Bot Layer** (`bot/bot.py`)
   - Telegram bot implementation
   - Webhook handler for processing updates

3. **Worker Layer** (`worker/worker.py`)
   - Background task processing
   - Redis queue management

4. **Netlify Functions** (`netlify/functions/`)
   - Serverless function endpoints
   - Webhook handler for Telegram

### Data Flow

1. User submits URL via Telegram or Web App
2. Request is processed by API or webhook handler
3. Task is enqueued in Redis
4. Worker processes the task asynchronously
5. Results are stored in Redis cache
6. User is notified of completion

## Troubleshooting Guide

### Common Deployment Issues

#### Webhook Registration Failure

**Problem**: Telegram webhook registration fails

**Solution**:
- Verify TELEGRAM_TOKEN is correct
- Ensure WEBHOOK_URL is publicly accessible
- Check Netlify function logs for errors
- Run the webhook activation script:
  ```bash
  python scripts/activate_webhook.py
  ```

#### Redis Connection Issues

**Problem**: Application fails to connect to Redis

**Solution**:
- Verify REDIS_URL is correct and includes `rediss://` protocol
- Check network connectivity to Upstash
- Verify Redis credentials
- Run the Redis diagnostics tool:
  ```bash
  python tools/redis_diagnostics.py
  ```

#### Function Deployment Failures

**Problem**: Netlify functions fail to deploy

**Solution**:
- Check function logs in Netlify dashboard
- Verify dependencies in `requirements-netlify.txt`
- Check function size (max 50MB)
- Increase function timeout if needed in `netlify.toml`

### Performance Issues

#### Slow API Response Times

**Problem**: API endpoints respond slowly

**Solution**:
- Check Redis connection performance
- Optimize database queries
- Implement caching for frequently accessed data
- Run load testing to identify bottlenecks:
  ```bash
  python tools/load_tester.py -c 10 -n 100
  ```

#### Memory Leaks

**Problem**: Functions consume excessive memory

**Solution**:
- Check for unclosed connections
- Optimize image processing pipeline
- Implement proper garbage collection
- Monitor memory usage with performance monitor

## Security Best Practices

### API Security

1. **Input Validation**
   - All user inputs must be validated
   - Use `api/input_validator.py` for consistent validation

2. **Rate Limiting**
   - Implement rate limiting for all public endpoints
   - Configure limits based on subscription tier

3. **Authentication**
   - Use secure token-based authentication
   - Implement proper session management

### Payment Security

1. **Encryption**
   - All payment data must be encrypted
   - Use `api/payment_encryption.py` for encryption/decryption

2. **Fraud Detection**
   - Implement fraud detection for all transactions
   - Use `api/fraud_detection.py` for risk assessment

3. **PCI Compliance**
   - Never store raw credit card data
   - Use tokenization for payment processing
   - Implement key rotation mechanism

## Testing

### Running Tests

#### Unit Tests
```bash
pytest tests/unit/
```

#### Integration Tests
```bash
pytest tests/integration/
```

#### Load Testing
```bash
python tools/load_tester.py --concurrency 20 --requests 200
```

### Test Environment

The test environment uses:
- `.env.test` for environment variables
- Mock Redis for testing Redis functionality
- Mock HTTP client for testing API calls

## Monitoring and Alerting

### Monitoring Setup

1. **API Response Times**
   - Monitored via `api/response_time_monitor.py`
   - Alerts triggered for responses > 2 seconds

2. **Error Rates**
   - Monitored via application logs
   - Alerts triggered for error rates > 5%

3. **Redis Health**
   - Monitored via `worker/redis/monitoring.py`
   - Alerts triggered for connection failures

### Dashboard

Access the monitoring dashboard at:
```
https://worthit-app.netlify.app/admin/dashboard
```

Credentials are provided separately to the development team.

## API Reference

See the complete API reference in `docs/API_REFERENCE.md`

## Contributing

### Development Workflow

1. Create a feature branch from `develop`
2. Implement changes with tests
3. Submit pull request to `develop`
4. After review and CI passes, merge to `develop`
5. Periodically, `develop` is merged to `main` for production release

### Coding Standards

- Follow PEP 8 for Python code
- Use type hints for all function parameters and return values
- Write docstrings for all functions and classes
- Maintain test coverage above 80%

## Support

For developer support, contact:
- Email: dev-support@worthit-app.com
- Slack: #worthit-dev channel