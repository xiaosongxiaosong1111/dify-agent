$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-process.ps1')
$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$BackendPath = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'backend'))
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$DataPath = Join-Path $ProjectRoot 'data'
$PidPath = Join-Path $DataPath 'server.pid'
$StdoutPath = Join-Path $DataPath 'server.out.log'
$StderrPath = Join-Path $DataPath 'server.err.log'
$HealthUrl = 'http://127.0.0.1:8765/api/health'

function Get-ProcessRecord([int]$ProcessId) {
    try {
        return Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    } catch {
        try { return Get-WmiObject -Class Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop } catch { return $null }
    }
}

function Test-OwnedServer([int]$ProcessId) {
    $ProcessRecord = Get-ProcessRecord $ProcessId
    if (-not $ProcessRecord -or -not $ProcessRecord.CommandLine) { return $false }
    $CommandLine = [string]$ProcessRecord.CommandLine
    return (Test-SierraCommandLine $CommandLine $ProjectRoot)
}

function Test-PortAvailable {
    $Listener = $null
    try {
        $Listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Parse('127.0.0.1'), 8765)
        $Listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($Listener) { $Listener.Stop() }
    }
}

function Remove-OwnedProcess([int]$ProcessId) {
    if (Test-OwnedServer $ProcessId) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    Write-Error 'Project Python environment is missing. Run .\setup.ps1 first.'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'frontend\dist\index.html') -PathType Leaf)) {
    Write-Error 'Built frontend is missing. Run .\setup.ps1 first.'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $BackendPath 'app\main.py') -PathType Leaf)) {
    Write-Error 'Backend entry point is missing from this project.'
    exit 1
}
New-Item -ItemType Directory -Force -Path $DataPath | Out-Null

if (Test-Path -LiteralPath $PidPath -PathType Leaf) {
    $SavedPidText = (Get-Content -LiteralPath $PidPath -Raw).Trim()
    $SavedPid = 0
    if ([int]::TryParse($SavedPidText, [ref]$SavedPid) -and (Test-OwnedServer $SavedPid)) {
        try {
            $Health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3
            if ($Health.StatusCode -eq 200) {
                Write-Host 'Sierra is already running at http://127.0.0.1:8765/'
                exit 0
            }
        } catch { }
        Write-Error 'A Sierra process is already running but its health check failed. Review data/server.err.log before taking action.'
        exit 1
    }
    Remove-Item -LiteralPath $PidPath -Force
}

if (-not (Test-PortAvailable)) {
    Write-Error 'Port 8765 on 127.0.0.1 is already in use. Sierra did not start and no process was stopped. Check the other application or configure it to release the port.'
    exit 1
}

$RuntimeJson = & $PythonPath (Join-Path $ProjectRoot 'tools\prepare_runtime.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw 'Runtime snapshot preparation failed; no backend was started.' }
$Runtime = $RuntimeJson | ConvertFrom-Json
$BackendPath = [string]$Runtime.backend_path
$OriginalDataSetting = $env:FLOWCRAFT_DATA_DIR
$SharedDataPath = if ([string]::IsNullOrWhiteSpace($OriginalDataSetting)) { $DataPath } else { [System.IO.Path]::GetFullPath($OriginalDataSetting) }
$env:FLOWCRAFT_DATA_DIR = $SharedDataPath
$ArgumentList = "-m uvicorn app.main:app --app-dir `"$BackendPath`" --host 127.0.0.1 --port 8765"
try {
    $ServerProcess = Start-Process -FilePath $PythonPath -ArgumentList $ArgumentList -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
} catch {
    Write-Error "Could not start the local backend: $($_.Exception.Message)"
    exit 1
} finally {
    if ($null -eq $OriginalDataSetting) { Remove-Item Env:FLOWCRAFT_DATA_DIR -ErrorAction SilentlyContinue } else { $env:FLOWCRAFT_DATA_DIR = $OriginalDataSetting }
}

Start-Sleep -Milliseconds 500
if (-not (Test-OwnedServer $ServerProcess.Id)) {
    Write-Error 'Started process identity could not be verified against this project path; no PID file was written.'
    exit 1
}
Set-Content -LiteralPath $PidPath -Value ([string]$ServerProcess.Id) -Encoding ASCII

$Healthy = $false
for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
    if (-not (Test-OwnedServer $ServerProcess.Id)) { break }
    try {
        $Health = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        if ($Health.StatusCode -eq 200) { $Healthy = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}

if (-not $Healthy) {
    Remove-OwnedProcess $ServerProcess.Id
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    Write-Error 'Backend did not pass the health check. Review data/server.err.log and data/server.out.log. Any cleanup was limited to the process started by this script.'
    exit 1
}

Write-Host 'Sierra is running at http://127.0.0.1:8765/'
Write-Host 'Health check: http://127.0.0.1:8765/api/health'

Write-Host ('Runtime snapshot: ' + $Runtime.build_id)
