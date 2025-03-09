@echo off
echo ===================================
echo WorthIt! Git Add, Commit, Push Tool
echo ===================================

:: Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Virtual environment not found, continuing without activation...
)

:: Check if git is installed
git --version > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Git is not installed or not in PATH
    echo Please install Git from https://git-scm.com/downloads
    pause
    exit /b 1
)

:: Check if the directory is a git repository
if not exist .git (
    echo Error: This directory is not a git repository.
    echo Initialize a git repository first with: git init
    pause
    exit /b 1
)

:: Display current git status
echo.
echo Current git status:
git status

:: Ask for commit message
echo.
set /p COMMIT_MSG="Enter commit message (or press Enter for default message): "

:: Use default message if none provided
if "%COMMIT_MSG%"=="" set COMMIT_MSG="Update WorthIt! project files"

:: Add all changes
echo.
echo Adding all changes to git...
git add .

:: Commit changes
echo.
echo Committing changes with message: %COMMIT_MSG%
git commit -m "%COMMIT_MSG%"

:: Check if commit was successful
if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Commit failed. Please resolve any issues and try again.
    pause
    exit /b 1
)

:: Push to remote repository
echo.
echo Pushing changes to remote repository...
git push

:: Check if push was successful
if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Push failed. This could be due to:
    echo  - No remote repository configured
    echo  - No internet connection
    echo  - Authentication issues
    echo  - Merge conflicts
    echo.
    echo Try running: git push -u origin main
    echo Or configure your remote with: git remote add origin your-repo-url
    pause
    exit /b 1
)

echo.
echo ===================================
echo Success! Changes have been committed and pushed.
echo ===================================
echo.

pause