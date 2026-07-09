[CmdletBinding()]
param(
    [string]$LogDir              = $(if ($env:LOG_DIR) { $env:LOG_DIR } else { 'output' }),
    [int]$GracefulTimeoutSeconds = 15
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── helpers ──────────────────────────────────────────────────────────────────

function Resolve-FullPath ([string]$RelOrAbs, [string]$Root) {
    if ([System.IO.Path]::IsPathRooted($RelOrAbs)) {
        return [System.IO.Path]::GetFullPath($RelOrAbs)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $RelOrAbs))
}

function Test-ProcessRunning ([int]$ProcessId) {
    return [bool](Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-Pid ([int]$ProcessId, [switch]$Force) {
    if (-not (Test-ProcessRunning -ProcessId $ProcessId)) { return }
    if ($Force) { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue }
    else        { Stop-Process -Id $ProcessId         -ErrorAction SilentlyContinue }
}

function Read-PidFile ([string]$PidPath) {
    if (-not (Test-Path -LiteralPath $PidPath -PathType Leaf)) { return 0 }
    $raw = (Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) { return 0 }
    $txt = $raw.ToString().Trim()
    if ($txt -as [int]) { return [int]$txt }
    return 0
}

function Get-OrphanedProjectPids ([string]$RootDir) {
    $found = [System.Collections.Generic.List[int]]::new()
    $filter = "Name='python.exe' OR Name='python3.exe' OR Name='py.exe'"
    $procs  = Get-CimInstance Win32_Process -Filter $filter -ErrorAction SilentlyContinue
    if (-not $procs) { return $found }
    foreach ($p in $procs) {
        if ($p.ProcessId -eq $PID) { continue }
        $cmd = $p.CommandLine
        if (-not $cmd) { continue }
        if ($cmd -like "*$RootDir*") {
            $found.Add([int]$p.ProcessId)
        }
    }
    return $found
}

function Stop-Service ([string]$Label, [string]$PidPath,
                       [System.Collections.Generic.List[int]]$Tracked) {
    $id = Read-PidFile -PidPath $PidPath
    if ($id -gt 0) {
        if (-not $Tracked.Contains($id)) { $Tracked.Add($id) }
        Write-Host "  Stopping $Label (PID $id) ..." -ForegroundColor White
        Stop-Pid -ProcessId $id
    }
    else {
        Write-Host "  $Label : not running." -ForegroundColor DarkGray
    }
    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
}

# ── main ─────────────────────────────────────────────────────────────────────

try {
    $rootDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $rootDir
    $logPath  = Resolve-FullPath -RelOrAbs $LogDir -Root $rootDir
    $stopTime = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')

    $allPids  = [System.Collections.Generic.List[int]]::new()

    Write-Host ''
    Write-Host '==========================================================' -ForegroundColor Cyan
    Write-Host '   PowerCenter -> IICS  |  Stopping Services' -ForegroundColor Cyan
    Write-Host "   Stopped  : $stopTime" -ForegroundColor Cyan
    Write-Host '==========================================================' -ForegroundColor Cyan
    Write-Host ''

    Stop-Service -Label 'Migration Pipeline' -PidPath (Join-Path $logPath 'app.pid')       -Tracked $allPids
    Stop-Service -Label 'FastAPI/Uvicorn'    -PidPath (Join-Path $logPath 'uvicorn.pid')   -Tracked $allPids
    Stop-Service -Label 'Streamlit'          -PidPath (Join-Path $logPath 'streamlit.pid') -Tracked $allPids

    # sweep for orphaned project processes not in any PID file
    foreach ($id in (Get-OrphanedProjectPids -RootDir $rootDir)) {
        if (-not $allPids.Contains($id)) {
            Write-Host "  Stopping orphaned process (PID $id) ..." -ForegroundColor Yellow
            Stop-Pid -ProcessId $id
            $allPids.Add($id)
        }
    }

    if ($allPids.Count -eq 0) {
        Write-Host '  No running project processes found.' -ForegroundColor DarkGray
        Write-Host ''
        Write-Host '==========================================================' -ForegroundColor Cyan
        exit 0
    }

    # wait for graceful shutdown
    $remaining = $GracefulTimeoutSeconds
    while ($remaining -gt 0) {
        Start-Sleep -Seconds 1
        $remaining--
        $anyAlive = $false
        foreach ($id in $allPids) {
            if (Test-ProcessRunning -ProcessId $id) { $anyAlive = $true; break }
        }
        if (-not $anyAlive) {
            Write-Host ''
            Write-Host '  All services stopped.' -ForegroundColor Green
            Write-Host '==========================================================' -ForegroundColor Cyan
            exit 0
        }
    }

    # force kill anything still alive
    Write-Host "  Graceful shutdown timed out (${GracefulTimeoutSeconds}s). Forcing ..." -ForegroundColor Yellow
    foreach ($id in $allPids) { Stop-Pid -ProcessId $id -Force }

    Write-Host ''
    Write-Host '  All services stopped (forced).' -ForegroundColor Green
    Write-Host '==========================================================' -ForegroundColor Cyan
}
catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
