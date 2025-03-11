# WorthIt! Troubleshooting Guide

## Introduction
This guide provides solutions for common issues that may arise when deploying and running the WorthIt! application in production. It covers API connectivity, webhook configuration, Redis connection, payment processing, Netlify functions, and other critical components.

## API Connectivity Issues

### API Endpoint Not Responding

**Symptoms:**
- Timeout errors when calling API endpoints
- 502 or 504 errors from Netlify functions

**Solutions:**
1. Verify the API_HOST environment variable is correctly set in Netlify
2. Check Netlify function logs for errors
3. Ensure function timeout settings in netlify.toml are sufficient (at least 30 seconds)
4. Verify the function is not exceeding Netlify's memory limits

**Example netlify.toml configuration:**
```toml
[functions]
  directory = "netlify/functions"
  node_bundler = "esbuild"

[functions.analyze]
  timeout = 30
```

### CORS Issues

**Symptoms:**
- Browser console shows CORS errors
- API calls work in Postman but not from the web app

**Solutions:**
1. Ensure CORS headers are properly configured in API responses
2. Verify the API is allowing requests from your web app domain
3. Check for any proxy or middleware issues

## Webhook Configuration

### Telegram Webhook Not Receiving Messages

**Symptoms:**
- Bot doesn't respond to messages
- No errors in logs, but no activity either

**Solutions:**
1. Verify the WEBHOOK_URL environment variable is correctly set
2. Run the webhook registration script again:
   ```
   python scripts/activate_webhook.py
   ```
3. Check Telegram API response for webhook registration
4. Ensure the webhook URL is publicly accessible and has a valid SSL certificate

## Redis Connection Issues

### Redis Connection Failures

**Symptoms:**
- Error logs showing Redis connection failures
- Intermittent timeouts when accessing cached data

**Solutions:**
1. Verify the REDIS_URL environment variable is using the `rediss://` protocol (note the double 's')
2. Check if Redis connection string includes the correct password and host
3. Test Redis connectivity using the test script:
   ```
   python test_redis_connection.py
   ```
4. Implement connection pooling and retry logic as shown in the Redis wrapper

## Payment Processing Issues

### Payment Transactions Failing

**Symptoms:**
- Payment attempts result in errors
- Stripe dashboard shows failed transactions

**Solutions:**
1. Verify the STRIPE_API_KEY environment variable is correctly set
2. Check that the payment encryption keys are properly configured:
   - PAYMENT_ENCRYPTION_KEY
   - PAYMENT_KEY_SALT
3. Look for fraud detection false positives in the logs
4. Test the payment flow in Stripe test mode before using live keys

### Fraud Detection Too Strict

**Symptoms:**
- Legitimate transactions being blocked
- High rate of payment rejections

**Solutions:**
1. Adjust the risk threshold in the FraudDetector class
2. Review and update the fraud patterns in the fraud_detection.py file
3. Implement a manual review process for borderline cases

## Image Processing Issues

### Slow Image Processing

**Symptoms:**
- Product analysis taking too long
- High memory usage during image processing

**Solutions:**
1. Optimize the image processing pipeline using ImageProcessingOptimizer
2. Enable WebP conversion for smaller file sizes
3. Implement proper caching for processed images
4. Adjust the max_workers parameter based on your server's capabilities

## API Key Rotation Issues

### API Key Rotation Failures

**Symptoms:**
- Error logs during key rotation attempts
- External API calls failing after rotation

**Solutions:**
1. Verify the key rotation scheduler is properly configured
2. Check that external services support API key rotation
3. Ensure proper overlap period between old and new keys
4. Monitor the key rotation audit log for failures

## Integration Testing Issues

### Integration Tests Failing

**Symptoms:**
- CI/CD pipeline failing at integration test stage
- Inconsistent test results

**Solutions:**
1. Run tests with verbose output to identify specific failures:
   ```
   python scripts/run_integration_tests.py --verbose
   ```
2. Check if the staging environment is properly configured
3. Verify that all required environment variables are set for testing
4. Look for timing issues in asynchronous tests

## Load Testing Issues

### Performance Bottlenecks

**Symptoms:**
- High response times under load
- Timeouts during load testing

**Solutions:**
1. Run targeted load tests to identify bottlenecks:
   ```
   python tools/load_test_performance.py --concurrency 20 --requests 200
   ```
2. Optimize database queries and Redis usage
3. Implement caching for frequently accessed data
4. Consider scaling up Netlify functions or using dedicated servers for high-traffic components

## Monitoring and Alerting

### Missing Critical Alerts

**Symptoms:**
- Production issues not being detected promptly
- No visibility into system performance

**Solutions:**
1. Set up monitoring for API response times
2. Configure alerts for critical errors
3. Implement a dashboard for real-time monitoring
4. Set up log aggregation for easier troubleshooting

## Documentation Issues

### Outdated Documentation

**Symptoms:**
- Users reporting confusion about features
- Support requests for documented features

**Solutions:**
1. Update user documentation with production URLs
2. Add troubleshooting guides for common issues
3. Create an FAQ for end users
4. Maintain developer documentation with current deployment processes

## Contact Support

If you've tried the solutions above and are still experiencing issues, please contact our support team at:

- Email: support@worthit-app.com
- Telegram: @WorthItSupport

Please include detailed information about the issue, any error messages, and steps to reproduce the problem.