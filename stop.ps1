$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime-process.ps1')
$ProjectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$BackendPath = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot 'backend'))
$PidPath = Join-Path $ProjectRoot 'data\server.pid'

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

if (-not (Test-Path -LiteralPath $PidPath -PathType Leaf)) {
    Write-Host '未找到 Sierra PID 文件；未停止任何进程。'
    exit 0
}

$SavedPidText = (Get-Content -LiteralPath $PidPath -Raw).Trim()
$SavedPid = 0
if (-not [int]::TryParse($SavedPidText, [ref]$SavedPid) -or $SavedPid -lt 1) {
    Remove-Item -LiteralPath $PidPath -Force
    Write-Host '已移除无效的 Sierra PID 文件；未停止任何进程。'
    exit 0
}

if (-not (Test-OwnedServer $SavedPid)) {
    Remove-Item -LiteralPath $PidPath -Force
    Write-Host '保存的 PID 与本项目命令行不匹配；未停止任何进程。'
    exit 0
}

Stop-Process -Id $SavedPid -Force
Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
Write-Host 'Sierra 后端已停止。'
