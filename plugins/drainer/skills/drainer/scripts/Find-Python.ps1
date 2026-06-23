# Find-Python.ps1 - Shared helper to locate python.exe or pythonw.exe with full path.
#
# Returns the full path to the requested Python executable, using py launcher or PATH.
# Exits with error 1 if not found.
#
# Usage:
#   $pythonw = & (Join-Path $scriptDir 'Find-Python.ps1') -Executable 'pythonw'
#   $python = & (Join-Path $scriptDir 'Find-Python.ps1') -Executable 'python'

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('python', 'pythonw')]
    [string]$Executable
)

$exeName = "$Executable.exe"
$pythonPath = $null

# Try py launcher first - most reliable way to find the default Python installation
$pyLauncher = (Get-Command py.exe -ErrorAction SilentlyContinue)
if ($pyLauncher) {
    $pythonDir = & py.exe -c "import sys; print(sys.executable)" 2>$null | Split-Path -Parent
    $candidate = Join-Path $pythonDir $exeName
    if (Test-Path $candidate) {
        $pythonPath = $candidate
    }
}

# Fall back to PATH
if (-not $pythonPath) {
    $pythonPath = (Get-Command $exeName -ErrorAction SilentlyContinue).Source
}

# Fail with clear error if not found
if (-not $pythonPath) {
    Write-Error "Cannot find $exeName. Install Python or ensure it's in PATH."
    exit 1
}

# Return the full path
Write-Output $pythonPath
