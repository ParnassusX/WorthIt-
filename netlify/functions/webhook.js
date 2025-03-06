// Netlify serverless function for handling Telegram webhook
const { spawn } = require('child_process');
const path = require('path');

exports.handler = async function(event, context) {
  // Only allow POST requests
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      body: JSON.stringify({ error: 'Method not allowed' })
    };
  }

  try {
    // Parse the incoming webhook data
    const body = JSON.parse(event.body);
    
    // Execute the Python webhook handler
    const result = await executePythonScript(body);
    
    return {
      statusCode: 200,
      body: JSON.stringify(result)
    };
  } catch (error) {
    console.error('Error processing webhook:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Internal server error', details: error.message })
    };
  }
};

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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.append('.')

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
        print(f"Error processing webhook: {str(e)}")
        return {"status": "error", "detail": str(e)}

# Run the async function
result = asyncio.run(handle_webhook())
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
        resolve(result);
      } catch (error) {
        console.error('Failed to parse Python output:', outputData);
        reject(new Error('Failed to parse Python output'));
      }
    });
  });
}