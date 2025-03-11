/**
 * Netlify serverless function for product analysis
 * 
 * PRODUCTION NOTES:
 * - This function handles product URL analysis requests
 * - It validates input, manages Redis connections, and delegates to Python for business logic
 * - Critical for product analysis reliability and performance monitoring
 */
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');
const MAX_PAYLOAD_SIZE = 1024 * 1024; // 1MB max payload size for security
const MAX_URL_LENGTH = 2048; // Standard maximum URL length

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
    function: 'analyze',
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

exports.handler = async function(event, context) {
  // Generate or use existing request ID for tracing through logs
  const requestId = context.awsRequestId || Math.random().toString(36).substring(2, 15);
  
  // Only allow POST requests for analysis
  if (event.httpMethod !== 'POST') {
    logEvent('warn', 'Method not allowed', { requestId, method: event.httpMethod });
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
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

  // Get the product URL from query parameters
  const url = event.queryStringParameters?.url;
  if (!url) {
    logEvent('warn', 'Missing product URL', { requestId });
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'Product URL is required' })
    };
  }
  
  // Validate URL format and length
  if (url.length > MAX_URL_LENGTH) {
    logEvent('warn', 'URL exceeds maximum length', { requestId, urlLength: url.length });
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'URL exceeds maximum allowed length' })
    };
  }
  
  try {
    // Validate URL format
    new URL(url);
  } catch (urlError) {
    logEvent('warn', 'Invalid URL format', { requestId, url: url.substring(0, 100) });
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'Invalid URL format' })
    };
  }

  try {
    logEvent('info', 'Processing product analysis request', { requestId, url: url.substring(0, 100) });
    
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

    // Execute the Python analysis script with proper path setup and error handling
    const result = await withRetry(() => executePythonScript(url), 3, 500);
    
    logEvent('info', 'Product analysis completed successfully', { requestId });
    return {
      statusCode: 200,
      body: JSON.stringify(result)
    };
  } catch (error) {
    // Structured error logging for production monitoring
    logEvent('error', 'Error analyzing product', { 
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
 * Execute Python script to process product analysis
 * 
 * PRODUCTION NOTES:
 * - Uses child_process for isolation and security
 * - Handles process output and errors properly
 * - Implements proper error propagation and logging
 * - Ensures clean process termination
 */
async function executePythonScript(productUrl) {
  return new Promise((resolve, reject) => {
    // Create a process to run the Python analysis handler
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
logger.info(f"Environment variables check: REDIS_URL exists: {bool(os.getenv('REDIS_URL'))}")

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

# Import the product analysis function
from api.main import analyze_product

async def analyze():
    try:
        # Validate URL before processing
        if not '${productUrl}':
            raise ValueError("Empty product URL provided")
            
        # Check for required API keys
        required_keys = ['APIFY_API_KEY', 'HUGGINGFACE_API_KEY']
        missing_keys = [key for key in required_keys if not os.getenv(key)]
        if missing_keys:
            raise EnvironmentError(f"Missing required API keys: {', '.join(missing_keys)}")
        
        # Analyze the product with timeout handling
        logger.info(f"Starting analysis for URL: {('${productUrl}')[:100]}...")
        result = await analyze_product('${productUrl}')
        logger.info("Analysis completed successfully")
        return result
    except Exception as e:
        logger.error(f"Error analyzing product: {str(e)}")
        return {"error": True, "message": str(e)}

# Run the async function
result = asyncio.run(analyze())
print(json.dumps(result))
      `
    ]);

    let outputData = '';
    let errorData = '';
    let outputLimitReached = false;

    // Capture stdout with buffer size limits for production safety
    pythonProcess.stdout.on('data', (data) => {
      // Limit buffer size to prevent memory issues in production
      if (outputData.length < 1024 * 1024) { // 1MB limit
        outputData += data.toString();
      } else if (!outputLimitReached) {
        outputLimitReached = true;
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
        if (result.error) {
          reject(new Error(result.message));
        } else {
          resolve(result);
        }
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