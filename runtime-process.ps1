function Test-SierraCommandLine([string]$CommandLine, [string]$RootPath) {
    if (-not $CommandLine -or $CommandLine -notmatch '(?i)-m\s+uvicorn\s+app\.main:app(?:\s|$)') { return $false }
    if ($CommandLine -notmatch '(?i)--host\s+127\.0\.0\.1(?:\s|$)' -or $CommandLine -notmatch '(?i)--port\s+8765(?:\s|$)') { return $false }
    $AppDirMatch = [regex]::Match($CommandLine, '(?i)--app-dir\s+(?:"([^"]+)"|(\S+))')
    if (-not $AppDirMatch.Success) { return $false }
    try {
        $SelectedPath = if ($AppDirMatch.Groups[1].Success) { $AppDirMatch.Groups[1].Value } else { $AppDirMatch.Groups[2].Value }
        $ResolvedBackend = [System.IO.Path]::GetFullPath($SelectedPath).TrimEnd('\')
        $ResolvedRoot = [System.IO.Path]::GetFullPath($RootPath).TrimEnd('\')
        if ($ResolvedBackend.Equals((Join-Path $ResolvedRoot 'backend'), [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        $SnapshotsPath = (Join-Path $ResolvedRoot '.runtime\snapshots') + '\'
        if (-not $ResolvedBackend.StartsWith($SnapshotsPath, [System.StringComparison]::OrdinalIgnoreCase) -or -not $ResolvedBackend.EndsWith('\backend', [System.StringComparison]::OrdinalIgnoreCase)) { return $false }
        $RuntimeRoot = Split-Path -Parent $ResolvedBackend
        $ManifestPath = Join-Path $RuntimeRoot 'runtime-manifest.json'
        if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { return $false }
        $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        return ($Manifest.schema_version -eq 1 -and $Manifest.build_id -eq (Split-Path -Leaf $RuntimeRoot) -and $Manifest.shared_data_copied -eq $false)
    } catch { return $false }
}
