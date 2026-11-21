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
    Write-Error '项目 Python 环境缺失。请先运行 .\setup.ps1。'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'frontend\dist\index.html') -PathType Leaf)) {
    Write-Error '已构建的前端缺失。请先运行 .\setup.ps1。'
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $BackendPath 'app\main.py') -PathType Leaf)) {
    Write-Error '本项目缺少后端入口文件。'
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
                Write-Host 'Sierra 已在 http://127.0.0.1:8765/ 运行'
                exit 0
            }
        } catch { }
        Write-Error 'Sierra 进程已在运行，但健康检查失败。请在处理前查看 data/server.err.log。'
        exit 1
    }
    Remove-Item -LiteralPath $PidPath -Force
}

if (-not (Test-PortAvailable)) {
    Write-Error '127.0.0.1 上的 8765 端口已被占用。Sierra 未启动，也未停止任何进程。请检查占用该端口的其他应用，或将其配置为释放该端口。'
    exit 1
}

$RuntimeJson = & $PythonPath (Join-Path $ProjectRoot 'tools\prepare_runtime.py') --project-root $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw '运行快照准备失败；未启动后端。' }
$Runtime = $RuntimeJson | ConvertFrom-Json
$BackendPath = [string]$Runtime.backend_path
$OriginalDataSetting = $env:FLOWCRAFT_DATA_DIR
$SharedDataPath = if ([string]::IsNullOrWhiteSpace($OriginalDataSetting)) { $DataPath } else { [System.IO.Path]::GetFullPath($OriginalDataSetting) }
$env:FLOWCRAFT_DATA_DIR = $SharedDataPath
$ArgumentList = "-m uvicorn app.main:app --app-dir `"$BackendPath`" --host 127.0.0.1 --port 8765"
try {
    $ServerProcess = Start-Process -FilePath $PythonPath -ArgumentList $ArgumentList -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
} catch {
    Write-Error "无法启动本地后端：$($_.Exception.Message)"
    exit 1
} finally {
    if ($null -eq $OriginalDataSetting) { Remove-Item Env:FLOWCRAFT_DATA_DIR -ErrorAction SilentlyContinue } else { $env:FLOWCRAFT_DATA_DIR = $OriginalDataSetting }
}

Start-Sleep -Milliseconds 500
if (-not (Test-OwnedServer $ServerProcess.Id)) {
    Write-Error '无法根据本项目路径验证已启动进程的身份；未写入 PID 文件。'
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
    Write-Error '后端未通过健康检查。请查看 data/server.err.log 和 data/server.out.log。清理范围仅限本脚本启动的进程。'
    exit 1
}

Write-Host 'Sierra 正在 http://127.0.0.1:8765/ 运行'
Write-Host '健康检查：http://127.0.0.1:8765/api/health'

Write-Host ('运行快照：' + $Runtime.build_id)
