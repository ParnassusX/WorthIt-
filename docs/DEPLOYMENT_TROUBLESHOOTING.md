# WorthIt! Deployment Troubleshooting Guide

## Common Issues and Solutions

### 404 Errors with Netlify Functions

**Symptoms:**
- 404 errors when accessing `/.netlify/functions/webhook` or `/.netlify/functions/analyze`
- Error messages in browser console: `Failed to load resource: the server responded with a status of 404 ()`
- Telegram bot not responding to messages

**Causes:**
1. Environment variables not properly loaded in serverless functions
2. Python dependencies not properly included in function deployment
3. Incorrect path configuration in web app API calls
4. Missing files in Netlify function deployment

**Solutions:**

1. **Improve environment variable handling in serverless functions:**
   - Add better error handling for environment variable loading
   - Add logging to verify environment variables are available
   - Ensure all required environment variables are set in Netlify dashboard

2. **Update netlify.toml configuration:**
   - Ensure `included_files` directive includes all necessary Python files
   - Specify memory and timeout settings for functions
   - Configure proper redirects for function endpoints

3. **Fix API endpoint paths in web app:**
   - Use absolute paths with `window.location.origin` for API endpoints
   - Add logging to verify correct API URLs are being used

4. **Verify Python dependencies:**
   - Ensure all required dependencies are listed in `requirements-netlify.txt`
   - Check for compatibility issues between dependencies

## Deployment Checklist

Before deploying to Netlify, ensure:

1. All environment variables are set in Netlify dashboard:
   - `TELEGRAM_TOKEN`
   - `REDIS_URL` (with `rediss://` protocol for Upstash)
   - `WEBHOOK_URL`
   - Other required API keys

2. Test functions locally using Netlify CLI:
   ```
   netlify dev
   ```

3. Verify webhook registration with Telegram:
   ```
   python scripts/activate_webhook.py
   ```

4. Check for any Python dependency conflicts

## Monitoring and Debugging

1. **Check Netlify function logs:**
   - Go to Netlify dashboard > Functions > Select function > View logs
   - Look for Python errors or missing dependencies

2. **Test API endpoints directly:**
   - Use tools like Postman or curl to test function endpoints
   - Verify correct response formats

3. **Monitor Redis connection:**
   - Use `test_redis_connection.py` to verify Redis connectivity
   - Check for SSL/TLS issues with Upstash

## Common Error Messages and Solutions

### "TELEGRAM_TOKEN environment variable is not set"

- Verify token is set in Netlify environment variables
- Check for typos in variable name
- Ensure token is valid and active

### "Failed to parse Python output"

- Check for syntax errors in Python code
- Verify all dependencies are installed
- Look for JSON formatting issues in Python output

### "Python process failed"

- Check for missing Python dependencies
- Verify Python version compatibility
- Look for file path issues in Python imports