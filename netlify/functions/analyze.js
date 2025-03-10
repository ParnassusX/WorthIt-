// Netlify serverless function for product analysis
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

exports.handler = async function(event, context) {
  // Only allow POST requests
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  // Get the product URL from query parameters
  const url = event.queryStringParameters?.url;
  if (!url) {
    return {
      statusCode: 400,
      body: JSON.stringify({ error: 'Product URL is required' })
    };
  }

  try {
    // Set environment variables for Redis SSL
    process.env.REDIS_SSL = 'true';
    process.env.REDIS_VERIFY_SSL = 'true';

    // Convert Redis URL to use SSL if needed
    const redisUrl = process.env.REDIS_URL;
    if (redisUrl && redisUrl.includes('upstash') && !redisUrl.startsWith('rediss://')) {
      process.env.REDIS_URL = redisUrl.replace('redis://', 'rediss://');
      console.log(`Converted Redis URL to use SSL: ${process.env.REDIS_URL}`);
    }

    // Execute the Python analysis script with proper path setup
    const result = await executePythonScript(url);
    
    return {
      statusCode: 200,
      body: JSON.stringify(result)
    };
  } catch (error) {
    console.error('Error analyzing product:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ 
        error: 'Internal server error', 
        details: error.message 
      })
    };
  }
};

async function executePythonScript(productUrl) {
  return new Promise((resolve, reject) => {
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
logger.info(f"Environment variables check: API paths: {os.environ.get('PATH', 'Not set')}")


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
        # Analyze the product
        result = await analyze_product('${productUrl}')
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

    pythonProcess.stdout.on('data', (data) => {
      outputData += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorData += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        console.error(`Python process exited with code ${code}`);
        console.error(`Error: ${errorData}`);
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
        console.error('Failed to parse Python output:', outputData);
        reject(new Error('Failed to parse Python output'));
      }
    });
  });
}