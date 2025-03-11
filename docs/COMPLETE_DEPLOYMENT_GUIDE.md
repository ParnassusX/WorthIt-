# WorthIt! Complete Deployment Guide

This guide provides a comprehensive approach to deploying the WorthIt! application to Netlify, ensuring all components are properly configured and functioning.

## Pre-Deployment Checklist

### Environment Variables

Ensure all required environment variables are set in your Netlify dashboard:

- `TELEGRAM_TOKEN` - Your Telegram bot token
- `REDIS_URL` - Upstash Redis URL (must use `rediss://` protocol)
- `WEBHOOK_URL` - Full URL to your webhook endpoint
- `APIFY_TOKEN` - Token for web scraping
- `HF_TOKEN` - Hugging Face token for AI models
- `SUPABASE_URL` and `SUPABASE_KEY` - If using Supabase
- `RENDER_API_KEY` - If using Render services

### Code Preparation

1. **Test locally first**
   ```
   netlify dev
   ```

2. **Verify Redis connection**
   ```
   python test_redis_connection.py --verbose
   ```

3. **Run all tests**
   ```
   pytest tests/
   ```

4. **Check netlify.toml configuration**
   - Ensure `included_files` directive includes all necessary Python files
   - Verify memory and timeout settings for functions
   - Check redirects for function endpoints

## Deployment Process

### 1. Deploy to Netlify

Use the deployment script:
```
./deploy_to_netlify.bat
```

Or deploy manually:
```
npx netlify deploy --prod --memory=2048
```

### 2. Verify Webhook Registration

After deployment, register the webhook with Telegram:
```
python scripts/activate_webhook.py
```

### 3. Run Post-Deployment Verification

Run the verification script to ensure everything is working:
```
python scripts/post_deploy_checks.py --verbose
```

This script checks:
- Environment variables
- Webhook registration
- Redis connection
- Function endpoints
- Web app accessibility

## Troubleshooting Common Issues

### 404 Errors with Netlify Functions

**Symptoms:**
- 404 errors when accessing `/.netlify/functions/webhook` or `/.netlify/functions/analyze`
- Error messages in browser console: `Failed to load resource: the server responded with a status of 404 ()`
- Telegram bot not responding to messages

**Solutions:**

1. **Check environment variables**
   - Verify all required environment variables are set in Netlify dashboard
   - Check for typos in variable names

2. **Verify function deployment**
   - Check Netlify dashboard > Functions to see if functions are deployed
   - Look at function logs for errors

3. **Check netlify.toml configuration**
   - Ensure `included_files` directive includes all necessary Python files
   - Verify redirects are properly configured

4. **Inspect Python dependencies**
   - Ensure all required dependencies are listed in `requirements-netlify.txt`
   - Check for compatibility issues between dependencies

### Redis Connection Issues

**Symptoms:**
- Error messages about Redis connection failures
- Bot responds slowly or not at all

**Solutions:**

1. **Check Redis URL format**
   - Ensure URL uses `rediss://` protocol for Upstash
   - Verify credentials in the URL are correct

2. **Test Redis connection**
   ```
   python test_redis_connection.py --verbose
   ```

3. **Check Upstash dashboard**
   - Verify the database is active
   - Check connection limits and usage

### Webhook Registration Issues

**Symptoms:**
- Bot doesn't respond to messages
- No errors in function logs

**Solutions:**

1. **Check webhook registration**
   ```
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo
   ```

2. **Re-register webhook**
   ```
   python scripts/activate_webhook.py
   ```

3. **Verify webhook URL**
   - Ensure it points to your Netlify deployment
   - Check for typos or incorrect formatting

## Monitoring and Maintenance

### Regular Checks

1. **Monitor function logs**
   - Netlify dashboard > Functions > Select function > View logs
   - Look for errors or warnings

2. **Check Redis connection**
   - Run connection test weekly
   - Monitor memory usage and performance

3. **Test bot functionality**
   - Regularly send test messages to the bot
   - Verify all commands work as expected

### Performance Optimization

1. **Optimize Redis usage**
   - Use appropriate TTL for cached items
   - Implement batch operations where possible

2. **Monitor function performance**
   - Check execution times in Netlify logs
   - Optimize slow functions

3. **Implement circuit breakers**
   - Add retry logic for external API calls
   - Implement fallbacks for critical services

## Security Considerations

1. **Protect API keys**
   - Never commit API keys to the repository
   - Use environment variables for all sensitive information

2. **Implement rate limiting**
   - Protect against abuse and DoS attacks
   - Monitor for unusual traffic patterns

3. **Regular security audits**
   - Review dependencies for vulnerabilities
   - Update packages regularly

## Conclusion

Following this comprehensive deployment guide will ensure your WorthIt! application is properly deployed, configured, and maintained. Regular monitoring and maintenance will help identify and resolve issues before they impact users.