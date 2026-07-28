[CmdletBinding()]
param(
    [ValidateSet('canonical','parse','explore','classify','persist','reports','enterprise','automation','iics-package','all')]
    [string]$Mode   = $(if ($env:MODE)   { $env:MODE }   else { 'all' }),
    [string]$Config = $(if ($env:CONFIG) { $env:CONFIG } else { 'common/config/config.json' }),
    [string]$LogDir = $(if ($env:LOG_DIR){ $env:LOG_DIR } else { 'output' }),
    [bool]$PersistToMySql = $(if ($null -ne $env:PERSIST_TO_MYSQL) {
        $env:PERSIST_TO_MYSQL -notin @('0', 'false', 'False', 'FALSE', 'no', 'No', 'NO', 'off', 'Off', 'OFF')
    } else {
        $true
    })
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# helpers

function Resolve-FullPath ([string]$RelOrAbs, [string]$Root) {
    if ([System.IO.Path]::IsPathRooted($RelOrAbs)) {
        return [System.IO.Path]::GetFullPath($RelOrAbs)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Root $RelOrAbs))
}

function Find-Python {
    foreach ($candidate in @('python', 'py', 'python3')) {
        $found = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    throw 'Python not found on PATH. Install Python 3 and retry.'
}

function Load-EnvFile ([string]$EnvPath) {
    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) { return }
    foreach ($line in (Get-Content -LiteralPath $EnvPath)) {
        $line = $line.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        $idx = $line.IndexOf('=')
        if ($idx -lt 1) { continue }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim()
        if (-not [System.Environment]::GetEnvironmentVariable($key)) {
            [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }
}

function Test-PortFree ([int]$Port) {
    $inUse = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return ($null -eq $inUse)
}

function Invoke-Python ([string]$Exe, [string[]]$PArgs) {
    & $Exe @PArgs
    if ($LASTEXITCODE -ne 0) { throw "pip exited with code $LASTEXITCODE." }
}

function Test-DepsOk ([string]$Exe) {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("pc-iics-check-{0}.py" -f [System.Guid]::NewGuid().ToString('N'))
    $code = @'
import importlib.util, sys
need = ["sqlalchemy","mysql","pandas","lxml","openpyxl","plotly","dotenv",
        "huggingface_hub","fastapi","uvicorn","streamlit"]
miss = [m for m in need if importlib.util.find_spec(m) is None]
if miss:
    print("Missing: " + ", ".join(miss)); sys.exit(1)
print("OK")
'@
    try {
        Set-Content -LiteralPath $tmp -Value $code -Encoding ascii
        & $Exe $tmp | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

function Ensure-Deps ([string]$Exe, [string]$ReqFile) {
    $stamp = Join-Path (Split-Path -Parent $ReqFile) 'output\.deps-ok'
    if (-not (Test-Path -LiteralPath $ReqFile -PathType Leaf)) {
        Write-Host '  requirements.txt not found - skipping.' -ForegroundColor Yellow
        return
    }
    if ((Test-Path -LiteralPath $stamp -PathType Leaf) -and ((Get-Item -LiteralPath $stamp).LastWriteTime -ge (Get-Item -LiteralPath $ReqFile).LastWriteTime)) {
        Write-Host '  Dependency check already verified.' -ForegroundColor Green
        return
    }
    if (Test-DepsOk -Exe $Exe) {
        New-Item -ItemType File -Path $stamp -Force | Out-Null
        Write-Host '  All dependencies present.' -ForegroundColor Green
        return
    }
    Write-Host '  Installing dependencies (this may take a minute) ...' -ForegroundColor Cyan
    Invoke-Python -Exe $Exe -PArgs @('-m', 'pip', 'install', '--upgrade', 'pip', '--quiet')
    Invoke-Python -Exe $Exe -PArgs @('-m', 'pip', 'install', '-r', $ReqFile, '--quiet')
    New-Item -ItemType File -Path $stamp -Force | Out-Null
    Write-Host '  Dependencies installed.' -ForegroundColor Green
}

function Wait-ForPort ([int]$Port, [int]$TimeoutSec, [string]$Label) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = [System.Net.Sockets.TcpClient]::new()
            $tcp.Connect('127.0.0.1', $Port)
            $tcp.Close()
            return $true
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    Write-Host "  WARNING: $Label did not respond on port $Port within ${TimeoutSec}s." -ForegroundColor Yellow
    return $false
}

function Invoke-Pipeline ([string]$Label, [string]$Exe, [string[]]$SArgs,
                          [string]$WorkDir, [string]$StdOut, [string]$StdErr,
                          [string]$PidPath) {

    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue

    $proc = Start-Process `
        -FilePath         $Exe `
        -WorkingDirectory $WorkDir `
        -ArgumentList     $SArgs `
        -RedirectStandardOutput $StdOut `
        -RedirectStandardError  $StdErr `
        -PassThru `
        -Wait `
        -WindowStyle Hidden

    Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    $exitCode = $proc.ExitCode
    if ($null -eq $exitCode) { $exitCode = 0 }

    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode. Check logs: $StdErr"
    }
    Write-Host "  $Label completed successfully" -ForegroundColor Green
}

function Assert-IndividualPackages ([string]$InputXmlDir, [string]$OutputDir) {
    $expected = @(Get-ChildItem -LiteralPath $InputXmlDir -File -ErrorAction SilentlyContinue | Where-Object {
        $_.Extension -in @('.xml', '.XML')
    })
    $packageDir = Join-Path $OutputDir 'individual_idmc_exports'
    $actual = @()
    if (Test-Path -LiteralPath $packageDir -PathType Container) {
        $actual = @(Get-ChildItem -LiteralPath $packageDir -File -Filter '*.zip' | Where-Object {
            $_.BaseName -in $expected.BaseName
        })
    }
    if ($actual.Count -lt $expected.Count) {
        throw "Individual ZIP generation incomplete. Expected $($expected.Count) package(s), found $($actual.Count) in $packageDir."
    }
    Write-Host "  Individual ZIP packages: $($actual.Count)/$($expected.Count) generated in $packageDir" -ForegroundColor Green
}

function Start-Service ([string]$Label, [string]$Exe, [string[]]$SArgs,
                        [string]$WorkDir, [string]$StdOut, [string]$StdErr,
                        [string]$PidPath, [int]$HealthPort = 0) {

    if (Test-Path -LiteralPath $PidPath -PathType Leaf) {
        $raw = (Get-Content -LiteralPath $PidPath -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($raw -and ($raw.ToString().Trim() -as [int])) {
            $existing = [int]$raw.ToString().Trim()
            if (Get-Process -Id $existing -ErrorAction SilentlyContinue) {
                Write-Host "  $Label already running (PID $existing). Skipping." -ForegroundColor Yellow
                return
            }
        }
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
    }

    $proc = Start-Process `
        -FilePath         $Exe `
        -WorkingDirectory $WorkDir `
        -ArgumentList     $SArgs `
        -RedirectStandardOutput $StdOut `
        -RedirectStandardError  $StdErr `
        -PassThru `
        -WindowStyle Hidden

    Set-Content -LiteralPath $PidPath -Value ([string]$proc.Id) -Encoding ascii -NoNewline

    # wait for process to stay alive
    Start-Sleep -Seconds 1
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
        Remove-Item -LiteralPath $PidPath -Force -ErrorAction SilentlyContinue
        throw "$Label failed to start. Check log: $StdOut"
    }

    # health-check by probing the port (only for network services)
    if ($HealthPort -gt 0) {
        $ready = Wait-ForPort -Port $HealthPort -TimeoutSec 5 -Label $Label
        if ($ready) {
            Write-Host "  $Label started (PID $($proc.Id)) - port $HealthPort ready" -ForegroundColor Green
        }
        else {
            Write-Host "  $Label started (PID $($proc.Id)) - port $HealthPort not yet responding (check log)" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "  $Label started (PID $($proc.Id))" -ForegroundColor Green
    }
}

# main

try {
    $rootDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $rootDir

    $startTime = Get-Date
    $timestamp = $startTime.ToString('yyyy-MM-dd HH:mm:ss')

    $appPy    = Resolve-FullPath 'app.py'           $rootDir
    $stApp    = Resolve-FullPath 'streamlit_app.py' $rootDir
    $cfgFile  = Resolve-FullPath $Config            $rootDir
    $reqFile  = Resolve-FullPath 'requirements.txt' $rootDir
    $inputXml = Resolve-FullPath 'input_xml'        $rootDir
    $envFile  = Resolve-FullPath '.env'             $rootDir
    $logPath  = Resolve-FullPath $LogDir            $rootDir

    # pre-flight checks
    if (-not (Test-Path -LiteralPath $appPy    -PathType Leaf))      { throw 'app.py not found. Run from the project root.' }
    if (-not (Test-Path -LiteralPath $cfgFile  -PathType Leaf))      { throw "Config file not found: $Config" }
    if (-not (Test-Path -LiteralPath $inputXml -PathType Container)) { throw 'input_xml folder not found.' }

    New-Item -ItemType Directory -Path $logPath -Force | Out-Null

    Write-Host ''
    Write-Host '==========================================================' -ForegroundColor Cyan
    Write-Host '   PowerCenter -> IICS  |  Migration Platform' -ForegroundColor Cyan
    Write-Host "   Started : $timestamp" -ForegroundColor Cyan
    Write-Host '==========================================================' -ForegroundColor Cyan

    # [1] Load .env
    Write-Host ''
    Write-Host '[1/5] Loading environment ...' -ForegroundColor White
    Load-EnvFile -EnvPath $envFile
    if (Test-Path -LiteralPath $envFile -PathType Leaf) {
        Write-Host '  .env loaded.' -ForegroundColor Green
    }
    else {
        Write-Host '  No .env file found (optional).' -ForegroundColor Yellow
    }

    # [2] Python
    Write-Host ''
    Write-Host '[2/5] Checking Python ...' -ForegroundColor White
    $pyExe = Find-Python
    $pyVer = (& $pyExe --version 2>&1)
    Write-Host "  Python : $pyExe  ($pyVer)" -ForegroundColor Green

    # [3] Dependencies
    Write-Host ''
    Write-Host '[3/5] Checking dependencies ...' -ForegroundColor White
    Ensure-Deps -Exe $pyExe -ReqFile $reqFile

    # [4] Port availability
    Write-Host ''
    Write-Host '[4/5] Checking ports ...' -ForegroundColor White
    if (-not (Test-PortFree -Port 8000)) {
        Write-Host '  WARNING: Port 8000 is already in use. FastAPI may conflict.' -ForegroundColor Yellow
    }
    else { Write-Host '  Port 8000 (FastAPI)   - free' -ForegroundColor Green }

    if (-not (Test-PortFree -Port 8501)) {
        Write-Host '  WARNING: Port 8501 is already in use. Streamlit may conflict.' -ForegroundColor Yellow
    }
    else { Write-Host '  Port 8501 (Streamlit) - free' -ForegroundColor Green }

    # [5] Start services
    Write-Host ''
    Write-Host '[5/5] Starting services ...' -ForegroundColor White

    Write-Host ''
    Write-Host "  --> Migration Pipeline (mode: $Mode)" -ForegroundColor White
    $pipelineArgs = @('app.py', '--mode', $Mode, '--config', $Config)
    if ($PersistToMySql -and $Mode -in @('all', 'enterprise')) {
        $pipelineArgs += '--persist'
        Write-Host '      MySQL persistence: enabled' -ForegroundColor Green
    }
    elseif ($Mode -in @('all', 'enterprise')) {
        Write-Host '      MySQL persistence: disabled by PERSIST_TO_MYSQL' -ForegroundColor Yellow
    }
    Invoke-Pipeline `
        -Label   'Migration Pipeline' `
        -Exe     $pyExe `
        -SArgs   $pipelineArgs `
        -WorkDir $rootDir `
        -StdOut  (Join-Path $logPath 'app.log') `
        -StdErr  (Join-Path $logPath 'app.err') `
        -PidPath (Join-Path $logPath 'app.pid')

    if ($Mode -in @('all', 'iics-package')) {
        Assert-IndividualPackages `
            -InputXmlDir $inputXml `
            -OutputDir   (Resolve-FullPath 'output' $rootDir)
    }

    Write-Host ''
    Write-Host '  --> FastAPI / Uvicorn (port 8000)' -ForegroundColor White
    Start-Service `
        -Label      'FastAPI/Uvicorn' `
        -Exe        $pyExe `
        -SArgs      @('-m', 'uvicorn', 'app:create_app', '--factory', '--host', '0.0.0.0', '--port', '8000') `
        -WorkDir    $rootDir `
        -StdOut     (Join-Path $logPath 'uvicorn.log') `
        -StdErr     (Join-Path $logPath 'uvicorn.err') `
        -PidPath    (Join-Path $logPath 'uvicorn.pid') `
        -HealthPort 8000

    Write-Host ''
    Write-Host '  --> Streamlit Dashboard (port 8501)' -ForegroundColor White
    if (Test-Path -LiteralPath $stApp -PathType Leaf) {
        Start-Service `
            -Label      'Streamlit' `
            -Exe        $pyExe `
            -SArgs      @('-m', 'streamlit', 'run', 'streamlit_app.py', '--server.port', '8501', '--server.headless', 'true') `
            -WorkDir    $rootDir `
            -StdOut     (Join-Path $logPath 'streamlit.log') `
            -StdErr     (Join-Path $logPath 'streamlit.err') `
            -PidPath    (Join-Path $logPath 'streamlit.pid') `
            -HealthPort 8501
    }
    else {
        Write-Host '  streamlit_app.py not found - skipping Streamlit.' -ForegroundColor Yellow
    }
    $elapsed = [int]((Get-Date) - $startTime).TotalSeconds
    Write-Host ''
    Write-Host '==========================================================' -ForegroundColor Cyan
    Write-Host '  All services started.' -ForegroundColor Green
    Write-Host ''
    Write-Host "  FastAPI  : http://localhost:8000"
    Write-Host "  API Docs : http://localhost:8000/docs"
    Write-Host "  Streamlit: http://localhost:8501"
    Write-Host ''
    Write-Host "  Logs     : $logPath"
    Write-Host "  Elapsed  : ${elapsed}s"
    Write-Host ''
    Write-Host '  To stop all services run:  .\stop.ps1'
    Write-Host '==========================================================' -ForegroundColor Cyan
}
catch {
    Write-Host ''
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
