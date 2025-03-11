@echo off
echo Activating WorthIt! virtual environment...

rem Check if PowerShell is available
where powershell >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Using PowerShell activation method
    powershell -ExecutionPolicy Bypass -Command "& {& '%~dp0venv\Scripts\Activate.ps1'}"
    if %ERRORLEVEL% NEQ 0 (
        echo PowerShell activation failed, trying batch activation
        call "%~dp0venv\Scripts\activate.bat"
    )
) else (
    echo PowerShell not found, using batch activation
    call "%~dp0venv\Scripts\activate.bat"
)

echo.
echo Virtual environment activated. You should now see (venv) in your prompt.
echo If you don't see (venv), try running: .\venv\Scripts\activate.bat
echo.

cmd /k