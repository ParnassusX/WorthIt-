# WorthIt! Test Mode Guide

## Telegram Bot Testing

The Telegram bot is currently running in test mode using the configuration from `.env.test`. Here's how to interact with it:

1. **Find your test bot on Telegram**: 
   - Open Telegram and search for the bot username associated with your test token
   - If you haven't created a test bot yet, you can create one by talking to [@BotFather](https://t.me/botfather) on Telegram
   - Use the `/newbot` command to create a new bot and get a token
   - Update your `.env.test` file with this token

2. **Interact with your bot**:
   - Send the `/start` command to begin interaction
   - Try other commands like `/aiuto`, `/cerca`, `/analisi`, or `/popolari`
   - Send product URLs to test the analysis functionality

3. **Restart the bot**:
   - If you need to restart the bot, press Ctrl+C in the terminal where it's running
   - Run `python run_bot_local.py` again

## Web App Testing

The web app can be tested locally by starting the development server:

1. **Start the API server**:
   ```bash
   cd c:\Users\Ture\Desktop\random projects\WorthIt!
   uvicorn api.main:app --reload
   ```
   - Note: You may see Redis connection errors, but basic functionality should still work

2. **Start the web app development server**:
   ```bash
   cd c:\Users\Ture\Desktop\random projects\WorthIt!\web-app
   npm run dev
   ```

3. **Access the web app**:
   - Open your browser and navigate to the URL shown in the terminal (typically http://localhost:5173)
   - You can test the product scanning and analysis features

## Troubleshooting

### Redis Connection Errors
You may see Redis connection errors in the logs. These won't prevent basic testing but might limit some functionality:

```
Connection verification attempt failed: AbstractConnection.__init__() got an unexpected keyword argument 'ssl'
```

To fix this, you can:
- Install a local Redis server for testing
- Use Upstash Redis with the proper SSL configuration
- Update the Redis connection configuration in your code to handle SSL properly
- Or simply ignore these errors for basic testing

### Telegram Bot Token Issues
If you see an error about the Telegram token not being found:
1. Make sure your `.env.test` file contains a valid `TELEGRAM_TOKEN`
2. Ensure the token is for a bot you've created with @BotFather

### API Server Issues
If the API server fails to start:
1. Check that all required dependencies are installed
2. Verify that no other service is using port 8000
3. Look for specific error messages in the terminal output