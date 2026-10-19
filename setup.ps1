$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$BackendRequirements = Join-Path $ProjectRoot 'backend\requirements.txt'
$BackendLock = Join-Path $ProjectRoot 'backend\requirements-lock.txt'
if (Test-Path -LiteralPath $BackendLock -PathType Leaf) { $BackendRequirements = $BackendLock }
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$FrontendPath = Join-Path $ProjectRoot 'frontend'

function Stop-WithMessage([string]$Message) {
    Write-Error $Message
    exit 1
}

function Get-PythonCommand {
    $Launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($Launcher) {
        & $Launcher.Source -3 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{ Path = $Launcher.Source; Prefix = @('-3') }
        }
    }
    $Python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if (-not $Python) { $Python = Get-Command 'python' -ErrorAction SilentlyContinue }
    if ($Python) {
        & $Python.Source --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{ Path = $Python.Source; Prefix = @() }
        }
    }
    return $null
}

function Assert-PythonVersion([string]$PythonPath, [string[]]$Prefix) {
    $VersionText = & $PythonPath @Prefix --version 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0 -or $VersionText -notmatch 'Python\s+(\d+)\.(\d+)') {
        Stop-WithMessage 'Could not read the Python version. Install Python 3.10 or newer and run setup.ps1 again.'
    }
    $Major = [int]$Matches[1]
    $Minor = [int]$Matches[2]
    if ($Major -lt 3 -or ($Major -eq 3 -and $Minor -lt 10)) {
        Stop-WithMessage "Python 3.10 or newer is required; found $($VersionText.Trim()). No global environment was changed."
    }
}

if (-not (Test-Path -LiteralPath $BackendRequirements -PathType Leaf)) {
    Stop-WithMessage "Missing backend requirements file: $BackendRequirements"
}

$PythonCommand = Get-PythonCommand
if (-not $PythonCommand) {
    Stop-WithMessage 'Python 3.10 or newer was not found. Install Python or the Python Launcher, then run setup.ps1 again.'
}
Assert-PythonVersion $PythonCommand.Path $PythonCommand.Prefix

$NodeCommand = Get-Command 'node.exe' -ErrorAction SilentlyContinue
if (-not $NodeCommand) { $NodeCommand = Get-Command 'node' -ErrorAction SilentlyContinue }
if (-not $NodeCommand) {
    Stop-WithMessage 'Node.js 20.19 or newer was not found. Install Node.js, reopen PowerShell, and run setup.ps1 again.'
}
$NodeVersionText = & $NodeCommand.Source --version 2>&1 | Out-String
if ($LASTEXITCODE -ne 0 -or $NodeVersionText -notmatch 'v(\d+)\.(\d+)\.(\d+)') {
    Stop-WithMessage 'Could not read the Node.js version. Install Node.js 20.19 or newer and run setup.ps1 again.'
}
$NodeMajor = [int]$Matches[1]
$NodeMinor = [int]$Matches[2]
if ($NodeMajor -lt 20 -or ($NodeMajor -eq 20 -and $NodeMinor -lt 19)) {
    Stop-WithMessage "Node.js 20.19 or newer is required; found $($NodeVersionText.Trim()). No global environment was changed."
}
$NpmCommand = Get-Command 'npm.cmd' -ErrorAction SilentlyContinue
if (-not $NpmCommand) { $NpmCommand = Get-Command 'npm' -ErrorAction SilentlyContinue }
if (-not $NpmCommand) { Stop-WithMessage 'npm was not found with Node.js. Reinstall Node.js including npm, then retry.' }

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Host 'Creating the project-local Python virtual environment...'
    $CreateVenvArguments = @()
    $CreateVenvArguments += $PythonCommand.Prefix
    $CreateVenvArguments += @('-m', 'venv', (Join-Path $ProjectRoot '.venv'))
    & $PythonCommand.Path @CreateVenvArguments
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Failed to create .venv. Check the Python installation and write access to the project directory.' }
}

Write-Host 'Installing backend requirements into .venv...'
& $VenvPython -m pip install -r $BackendRequirements
if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Backend dependency installation failed. Check network access and retry setup.ps1; global Python packages were not changed.' }

if (-not (Test-Path -LiteralPath (Join-Path $FrontendPath 'package-lock.json') -PathType Leaf)) {
    Stop-WithMessage 'Missing frontend/package-lock.json; cannot install reproducible frontend dependencies.'
}
Write-Host 'Installing frontend dependencies with npm ci...'
Push-Location $FrontendPath
try {
    & $NpmCommand.Source ci
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Frontend dependency installation failed. Check network access and retry setup.ps1.' }
    Write-Host 'Building frontend/dist...'
    & $NpmCommand.Source run build
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage 'Frontend build failed. Review the build output, correct the source issue, and retry setup.ps1.' }
} finally {
    Pop-Location
}

Write-Host 'Setup completed. Run .\start.ps1 or double-click start.cmd.'
