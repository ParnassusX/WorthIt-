<#
.Synopsis
Activate a Python virtual environment for the current PowerShell session.
.Description
Activates the Python virtual environment located in the directory specified by
the parameter or the environment variable $env:VIRTUAL_ENV.
.Parameter VenvDir
Path to the directory containing the virtual environment to activate.
#>

[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Position=0)]
    [string]$VenvDir = $null
)

if ($VenvDir -eq $null) {
    $VenvDir = $env:VIRTUAL_ENV
}

if ($VenvDir -eq $null) {
    Write-Host "VenvDir not set as a parameter or environment variable"
    return
}

# Get the path to the virtual environment
$Deactivate = $MyInvocation.MyCommand.Definition
$CommandName = $MyInvocation.MyCommand.Name

function global:deactivate ([switch]$NonDestructive) {
    if (Test-Path function:_OLD_VIRTUAL_PROMPT) {
        # Restore the original prompt
        copy-item function:_OLD_VIRTUAL_PROMPT function:prompt
        remove-item function:_OLD_VIRTUAL_PROMPT
    }

    if (Test-Path env:_OLD_VIRTUAL_PYTHONHOME) {
        # Restore the original PYTHONHOME
        copy-item env:_OLD_VIRTUAL_PYTHONHOME env:PYTHONHOME
        remove-item env:_OLD_VIRTUAL_PYTHONHOME
    }

    if (Test-Path env:_OLD_VIRTUAL_PATH) {
        # Restore the original PATH
        copy-item env:_OLD_VIRTUAL_PATH env:PATH
        remove-item env:_OLD_VIRTUAL_PATH
    }

    if (Test-Path env:VIRTUAL_ENV) {
        remove-item env:VIRTUAL_ENV
    }

    if (!$NonDestructive) {
        # Self destruct!
        remove-item function:deactivate
    }
}

function global:pydoc {
    python -m pydoc $args
}

# Preserve PYTHONHOME if set
if (Test-Path env:PYTHONHOME) {
    copy-item env:PYTHONHOME env:_OLD_VIRTUAL_PYTHONHOME
    remove-item env:PYTHONHOME
}

# Save the current PATH
copy-item env:PATH env:_OLD_VIRTUAL_PATH

# Append the virtual environment directory to the PATH
$env:PATH = "$VenvDir\Scripts;$env:PATH"
$env:VIRTUAL_ENV = $VenvDir

# Set the prompt to show that we're in a virtual environment
function global:_OLD_VIRTUAL_PROMPT {""}
copy-item function:prompt function:_OLD_VIRTUAL_PROMPT

function global:prompt {
    # Add a prefix to the current prompt, but don't discard it.
    Write-Host -NoNewline -ForegroundColor Green "(venv) "
    _OLD_VIRTUAL_PROMPT
}