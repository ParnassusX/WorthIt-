@echo off
echo Starting WorthIt! Telegram Bot...
echo.

:: Activate the virtual environment
call venv\Scripts\activate.bat

:: Run the bot
python run_bot_local.py

:: Keep the window open if there's an error
pause