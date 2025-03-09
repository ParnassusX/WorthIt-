# Enhanced Virtual Environment Setup Script for WorthIt!
# This script creates a complete virtual environment with all dependencies
# and ensures proper configuration for testing

# Stop on errors
$ErrorActionPreference = "Stop"

# Output formatting function
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    else {
        $input | Write-Output
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

# Create log directory if it doesn't exist
Write-ColorOutput Green "Creating log directory..."
if (-Not (Test-Path -Path .\logs)) {
    New-Item -ItemType Directory -Force -Path .\logs
    Write-ColorOutput Green "Log directory created successfully."
} else {
    Write-ColorOutput Yellow "Log directory already exists."
}

# Check Python installation
Write-ColorOutput Green "Checking Python installation..."
try {
    $pythonVersion = python --version
    Write-ColorOutput Green "Found $pythonVersion"
} catch {
    Write-ColorOutput Red "Python is not installed or not in PATH. Please install Python 3.8 or higher."
    exit 1
}

# Remove existing virtual environment if it exists
Write-ColorOutput Green "Checking for existing virtual environment..."
if (Test-Path -Path .\venv) {
    Write-ColorOutput Yellow "Existing virtual environment found. Removing..."
    Remove-Item -Recurse -Force .\venv
    Write-ColorOutput Green "Existing virtual environment removed."
}

# Create Python virtual environment
Write-ColorOutput Green "Creating new virtual environment..."
try {
    python -m venv venv
    Write-ColorOutput Green "Virtual environment created successfully."
} catch {
    Write-ColorOutput Red "Failed to create virtual environment: $_"
    exit 1
}

# Activate virtual environment
Write-ColorOutput Green "Activating virtual environment..."
try {
    .\venv\Scripts\Activate.ps1
    Write-ColorOutput Green "Virtual environment activated."
} catch {
    Write-ColorOutput Red "Failed to activate virtual environment: $_"
    exit 1
}

# Upgrade pip
Write-ColorOutput Green "Upgrading pip..."
try {
    python -m pip install --upgrade pip
    Write-ColorOutput Green "Pip upgraded successfully."
} catch {
    Write-ColorOutput Red "Failed to upgrade pip: $_"
    # Continue anyway
}

# Install requirements
Write-ColorOutput Green "Installing requirements..."
try {
    pip install -r requirements.txt
    Write-ColorOutput Green "Requirements installed successfully."
} catch {
    Write-ColorOutput Red "Failed to install requirements: $_"
    exit 1
}

# Install additional development dependencies
Write-ColorOutput Green "Installing additional development dependencies..."
try {
    pip install pytest-cov pytest-mock pytest-env
    Write-ColorOutput Green "Additional dependencies installed successfully."
} catch {
    Write-ColorOutput Red "Failed to install additional dependencies: $_"
    # Continue anyway
}

# Verify Redis module
Write-ColorOutput Green "Verifying Redis module..."
try {
    python -c "import redis; print(f'Redis version: {redis.__version__}')"
    Write-ColorOutput Green "Redis module verified."
} catch {
    Write-ColorOutput Red "Redis module verification failed: $_"
    # Continue anyway
}

# Run Redis wrapper test
Write-ColorOutput Green "Running Redis wrapper test..."
try {
    python test_redis_wrapper.py
    Write-ColorOutput Green "Redis wrapper test completed."
} catch {
    Write-ColorOutput Red "Redis wrapper test failed: $_"
    # Continue anyway
}

# Create .env file if it doesn't exist
Write-ColorOutput Green "Checking for .env file..."
if (-Not (Test-Path -Path .\.env)) {
    Write-ColorOutput Yellow ".env file not found. Creating from .env.example..."
    if (Test-Path -Path .\.env.example) {
        Copy-Item -Path .\.env.example -Destination .\.env
        Write-ColorOutput Green ".env file created from example."
    } else {
        Write-ColorOutput Red ".env.example not found. Please create a .env file manually."
    }
} else {
    Write-ColorOutput Green ".env file already exists."
}

Write-ColorOutput Green "\nVirtual environment setup complete! You can now run tests with:\n"
Write-ColorOutput Yellow "pytest tests/unit/"
Write-ColorOutput Yellow "pytest tests/integration/"
Write-ColorOutput Yellow "pytest -xvs tests/"

Write-ColorOutput Green "\nTo activate the virtual environment in a new terminal, run:\n"
Write-ColorOutput Yellow ".\venv\Scripts\Activate.ps1"