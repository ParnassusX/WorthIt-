@echo off
echo ===================================
echo WorthIt! Netlify Deployment Tool
echo ===================================

:: Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found, continuing without activation...
)

:: Check if netlify-cli is installed
npx --yes netlify --version > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Installing Netlify CLI...
    npm install -g netlify-cli
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to install Netlify CLI
        pause
        exit /b 1
    )
)

:: Run tests
echo.
echo Running tests...
pytest tests/
if %ERRORLEVEL% neq 0 (
    echo.
    echo Warning: Tests failed. Do you want to continue with deployment? (Y/N)
    set /p CONTINUE="Continue? "
    if /i "%CONTINUE%" neq "Y" (
        echo Deployment aborted.
        pause
        exit /b 1
    )
)

:: Build web app
echo.
echo Building web app...
cd web-app

:: Use memory-optimized npm install
echo Using memory-optimized npm install...
set NODE_OPTIONS=--max_old_space_size=2048
npm install --prefer-offline --no-audit --progress=false
npm run build
if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Web app build failed.
    cd ..
    pause
    exit /b 1
)
cd ..

:: Deploy to Netlify
echo.
echo Deploying to Netlify...
npx --yes netlify deploy --prod
if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Netlify deployment failed.
    echo Please check your Netlify configuration and authentication.
    pause
    exit /b 1
)

echo.
echo ===================================
echo Success! WorthIt! has been deployed to Netlify.
echo ===================================
echo.

pause