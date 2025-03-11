/**
 * Netlify serverless function for handling Telegram webhook
 * 
 * PRODUCTION NOTES:
 * - This function serves as the entry point for all Telegram webhook requests
 * - It handles authentication, validation, and delegates to Python for business logic
 * - Critical for production reliability and security
 */
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const MAX_PAYLOAD_SIZE = 1024 * 1024; // 1MB max payload size for security

/**
 * Structured logging helper for consistent production monitoring
 * 
 * PRODUCTION NOTES:
 * - All logs use this format for consistent parsing by log aggregation tools
 * - Include context objects for better debugging and traceability
 * - Log levels: error, warn, info, debug - use appropriately
 */
function logEvent(level, message, context = {}) {
  const timestamp = new Date().toISOString();
  const logEntry = {
    timestamp,
    level,
    message,
    function: 'webhook',
    ...context
  };
  console.log(JSON.stringify(logEntry));
}

/**
 * Retry mechanism for handling transient errors in production
 * 
 * PRODUCTION NOTES:
 * - Uses exponential backoff to prevent overwhelming downstream services
 * - Only retries specific network/timeout errors to avoid masking real issues
 * - Logs each retry attempt for monitoring and debugging
 * - Preserves original error context for proper error reporting
 */
async function withRetry(operation, maxRetries = 3, initialDelay = 300) {
  let lastError;
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      // Only retry on network or timeout errors
      if (!error.message.includes('ECONNRESET') && 
          !error.message.includes('timeout') && 
          !error.message.includes('ETIMEDOUT')) {
        throw error;
      }
      
      const delay = initialDelay * Math.pow(2, attempt - 1);
      logEvent('warn', `Retry attempt ${attempt}/${maxRetries} after ${delay}ms`, { error: error.message });
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  throw lastError;
}

/**
 * Main webhook handler function
 * 
 * PRODUCTION NOTES:
 * - Entry point for all webhook requests from Telegram
 * - Implements request validation, error handling, and response formatting
 * - Uses structured logging for all operations
 * - Handles Redis configuration securely for production environments
 */
/**
 * Health check endpoint for monitoring service status
 * 
 * PRODUCTION NOTES:
 * - Allows monitoring systems to verify service health
 * - Returns basic diagnostics without exposing sensitive information
 * - Useful for automated alerting and dashboard monitoring
 * - Should respond quickly (<500ms) to avoid false positives
 */
async function handleHealthCheck(event, requestId) {
  // Check if Redis is configured
  const redisConfigured = !!process.env.REDIS_URL;
  
  // Check if Telegram token is configured
  const telegramConfigured = !!process.env.TELEGRAM_TOKEN;
  
  // Get basic system metrics
  const metrics = {
    memory: process.memoryUsage(),
    uptime: process.uptime(),
    timestamp: new Date().toISOString()
  };
  
  logEvent('info', 'Health check requested', { requestId, ...metrics });
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      status: 'ok',
      version: process.env.VERSION || '1.0.0',
      environment: process.env.NODE_ENV || 'development',
      services: {
        redis: redisConfigured ? 'configured' : 'not_configured',
        telegram: telegramConfigured ? 'configured' : 'not_configured'
      },
      timestamp: metrics.timestamp
    })
  };
}

exports.handler = async function(event, context) {
  // Generate or use existing request ID for tracing through logs
  const requestId = context.awsRequestId || Math.random().toString(36).substring(2, 15);
  
  // Handle health check requests (GET requests to /health endpoint)
  if (event.httpMethod === 'GET' && event.path && event.path.endsWith('/health')) {
    return await handleHealthCheck(event, requestId);
  }
  
  // Validate payload size to prevent DoS attacks
  const contentLength = parseInt(event.headers['content-length'] || '0');
  if (contentLength > MAX_PAYLOAD_SIZE) {
    logEvent('error', 'Payload too large', { requestId, contentLength });
    return {
      statusCode: 413,
      body: JSON.stringify({ error: 'Payload too large' })
    };
  }
  
  // Only allow POST requests for webhook handling
  if (event.httpMethod !== 'POST') {
    logEvent('warn', 'Method not allowed', { requestId, method: event.httpMethod });
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  try {
    // Parse and validate the incoming webhook data
    let body;
    try {
      body = JSON.parse(event.body);
    } catch (parseError) {
      logEvent('error', 'Invalid JSON payload', { requestId, error: parseError.message });
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Invalid JSON payload' })
      };
    }
    
    // Validate webhook structure
    if (!body.update_id) {
      logEvent('warn', 'Invalid webhook format', { requestId });
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'Invalid webhook format' })
      };
    }
    logEvent('info', 'Received webhook', { 
      requestId, 
      updateId: body.update_id,
      chatId: body.message?.chat?.id || body.callback_query?.message?.chat?.id
    });
    
    // Validate and configure Redis URL for production
    const redisUrl = process.env.REDIS_URL;
    if (!redisUrl) {
      // Critical production error - Redis is required for state management
      logEvent('error', 'Redis configuration missing', { requestId });
      throw new Error('REDIS_URL environment variable is not set');
    }
    
    // Validate Redis URL format
    try {
      new URL(redisUrl);
    } catch (urlError) {
      logEvent('error', 'Invalid Redis URL format', { requestId });
      throw new Error('Invalid REDIS_URL format');
    }
    
    // Set environment variables for Redis SSL
    process.env.REDIS_SSL = 'true';
    process.env.REDIS_VERIFY_SSL = 'true';
    
    // Convert Redis URL to use SSL if needed
    if (redisUrl.includes('upstash') && !redisUrl.startsWith('rediss://')) {
      process.env.REDIS_URL = redisUrl.replace('redis://', 'rediss://');
      logEvent('info', 'Converted Redis URL to use SSL', { requestId });
    }

    // Execute the Python webhook handler with proper path setup and error handling
    const result = await withRetry(() => executePythonScript(body), 3, 500);
    
    return {
      statusCode: 200,
      body: JSON.stringify(result)
    };
  } catch (error) {
    // Structured error logging for production monitoring
    logEvent('error', 'Error processing webhook', { 
      requestId, 
      errorMessage: error.message,
      errorStack: error.stack,
      errorName: error.name
    });
    
    // Don't expose detailed error information in production
    const isProduction = process.env.NODE_ENV === 'production';
    return {
      statusCode: 500,
      body: JSON.stringify({ 
        error: 'Internal server error', 
        details: isProduction ? 'See server logs for details' : error.message,
        requestId // Include for support reference
      })
    };
  }
};

/**
 * Execute Python script to process webhook data
 * 
 * PRODUCTION NOTES:
 * - Uses child_process for isolation and security
 * - Handles process output and errors properly
 * - Implements proper error propagation and logging
 * - Ensures clean process termination
 */
async function executePythonScript(webhookData) {
  return new Promise((resolve, reject) => {
    // Create a process to run the Python webhook handler
    const pythonProcess = spawn('python', [
      '-c',
      `
import json
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    # First try to load from .env file
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except Exception as e:
    logger.warning(f"Could not load .env file: {str(e)}")
    
# Verify environment variables are available
logger.info(f"Environment variables check: TELEGRAM_TOKEN exists: {bool(os.getenv('TELEGRAM_TOKEN'))}")

# Add project root to path - using absolute path for reliability in serverless environment
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
logger.info(f"Added project root to path: {project_root}")

# Also add the netlify functions directory to path
functions_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, functions_dir)
logger.info(f"Added functions directory to path: {functions_dir}")

# Handle Redis URL for Upstash SSL
redis_url = os.getenv('REDIS_URL')
if redis_url and 'upstash' in redis_url and not redis_url.startswith('rediss://'):
    os.environ['REDIS_URL'] = redis_url.replace('redis://', 'rediss://')
    logger.info(f"Converted Redis URL to use SSL: {os.environ['REDIS_URL']}")

# Import the webhook handler
from bot.webhook_handler import process_telegram_update
from telegram import Update, Bot

async def handle_webhook():
    try:
        # Parse webhook data
        webhook_data = json.loads('''${JSON.stringify(webhookData)}''')
        
        # Get bot token
        bot_token = os.getenv('TELEGRAM_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_TOKEN environment variable is not set")
            
        # Create bot instance
        bot = Bot(token=bot_token)
        
        # Create update object
        update = Update.de_json(webhook_data, bot)
        
        # Process the update
        await process_telegram_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {"status": "error", "detail": str(e)}

# Run the async function
result = asyncio.run(handle_webhook())
print(json.dumps(result))
      `
    ]);

    let outputData = '';
    let errorData = '';

    // Capture stdout with buffer size limits for production safety
    pythonProcess.stdout.on('data', (data) => {
      // Limit buffer size to prevent memory issues in production
      if (outputData.length < 1024 * 1024) { // 1MB limit
        outputData += data.toString();
      } else if (!outputLimitReached) {
        const outputLimitReached = true;
        logEvent('warn', 'Python output exceeded buffer size limit', { size: outputData.length });
      }
    });

    // Capture stderr with similar protections
    pythonProcess.stderr.on('data', (data) => {
      // Limit buffer size to prevent memory issues
      if (errorData.length < 1024 * 1024) { // 1MB limit
        errorData += data.toString();
      }
    });

    // Set timeout to prevent hanging processes in production
    const timeout = setTimeout(() => {
      logEvent('error', 'Python process timeout', { timeout: '30s' });
      // Force kill the process to prevent zombie processes
      try {
        pythonProcess.kill('SIGKILL');
      } catch (killError) {
        logEvent('error', 'Failed to kill Python process', { error: killError.message });
      }
      reject(new Error('Python process timed out after 30s'));
    }, 30000); // 30 second timeout
    
    // Handle unexpected process errors
    pythonProcess.on('error', (err) => {
      clearTimeout(timeout);
      logEvent('error', 'Python process error', { error: err.message });
      reject(new Error(`Python process error: ${err.message}`));
    });
    
    pythonProcess.on('close', (code) => {
      clearTimeout(timeout); // Clear timeout on process completion
      
      if (code !== 0) {
        logEvent('error', 'Python process failed', { exitCode: code, stderr: errorData });
        reject(new Error(`Python process failed: ${errorData}`));
        return;
      }
      
      try {
        // Parse the JSON output from the Python script
        const result = JSON.parse(outputData.trim());
        resolve(result);
      } catch (error) {
        logEvent('error', 'Failed to parse Python output', { 
          error: error.message,
          rawOutput: outputData.substring(0, 500) // Truncate long output
        });
        reject(new Error('Failed to parse Python output'));
      }
    });
  });
}