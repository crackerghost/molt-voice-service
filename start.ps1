# Rahul voice assistant (OmniVoice) - Windows launcher (PowerShell equivalent of start.sh).
# Re-running kills any previous `-m server` and restarts fresh.
# Runs FOREVER in a supervision loop: streams backend logs live and
# auto-restarts the server if it crashes or the health check fails.
# First run creates omnivoice-env (Python 3.11) and installs dependencies.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

# --- port from .env (VOICE_PORT=...), default 8000 ---
$Port = '8000'
if (Test-Path '.env') {
  $m = Get-Content '.env' | Select-String '^VOICE_PORT=' | Select-Object -First 1
  if ($m) { $Port = $m.ToString().Split('=', 2)[1].Trim().Trim('"') }
}
$Url = "http://127.0.0.1:$Port"
$Log = Join-Path $env:TEMP 'voice-api.log'
$LogErr = Join-Path $env:TEMP 'voice-api.err.log'
$Python = '.\omnivoice-env\Scripts\python.exe'

# Classic HTTP for HF weights (hf_xet stalls); quiet the symlink warning.
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'

function Test-Health {
  try { (Invoke-WebRequest -Uri "$Url/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200 }
  catch { $false }
}

function Test-PortBusy([int]$p) {
  [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

function Stop-OldServer([int]$p) {
  $killed = $false
  # 1) Any previous `-m server` (venv python or stray uv-shim python).
  try {
    $srv = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -like '*-m server*' }
    foreach ($proc in $srv) {
      Write-Host "Stopping old server (PID $($proc.ProcessId))..."
      try { Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue; $killed = $true } catch {}
    }
  } catch {}
  # 2) Anything else squatting on our port.
  try {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
      if ($c.OwningProcess -and $c.OwningProcess -ne $PID) {
        Write-Host "Freeing port $p (PID $($c.OwningProcess))..."
        try { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; $killed = $true } catch {}
      }
    }
  } catch {}
  if ($killed) {
    for ($i = 0; $i -lt 20; $i++) {
      if (-not (Test-PortBusy $p)) { break }
      Start-Sleep 1
    }
  }
  if (Test-PortBusy $p) {
    Write-Error "Port $p is still busy after kill attempt - free it manually."
    exit 1
  }
}

# --- first run: venv + deps (mirrors start.sh; resemblyzer is optional) ---
function Test-VenvSsl([string]$py) {
  try { & $py -c 'import ssl' 2>$null; return ($LASTEXITCODE -eq 0) }
  catch { return $false }
}
if (-not (Test-Path $Python)) {
  Write-Host 'First run - creating omnivoice-env and installing deps...'
  if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv python install 3.11
    uv venv --python 3.11 omnivoice-env
    if (-not (Test-VenvSsl $Python)) {
      # WDAC/Application Control on some machines blocks uv-managed Pythons
      # under AppData (import _ssl -> "An Application Control policy has
      # blocked this file"). Rebuild from an allowed system Python instead.
      Write-Host 'uv-managed Python is blocked (ssl import failed) - rebuilding env from system Python...'
      Remove-Item -Recurse -Force omnivoice-env -ErrorAction SilentlyContinue
      $sysPy = @('C:\Python314\python.exe', 'C:\Python313\python.exe', 'C:\Python311\python.exe') |
        Where-Object { Test-Path $_ } | Select-Object -First 1
      if (-not $sysPy) { $sysPy = (Get-Command python -ErrorAction SilentlyContinue).Source }
      if (-not $sysPy) { Write-Error 'No working system Python found.'; exit 1 }
      uv venv --python $sysPy omnivoice-env
    }
    # resemblyzer needs C++ Build Tools on Windows; without it the
    # speaker gate auto-disables, so fall back to a filtered install.
    uv pip install --python $Python -r requirements.txt 2>$null
    if ($LASTEXITCODE -ne 0) {
      Write-Host 'Full install failed (likely webrtcvad/C++ tools) - retrying without resemblyzer...'
      Get-Content requirements.txt | Where-Object { $_ -notmatch 'resemblyzer' } | Set-Content requirements.win.txt
      uv pip install --python $Python -r requirements.win.txt
    }
  } else {
    py -3.11 -m venv omnivoice-env
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r requirements.txt
  }
}

# Start one server process; returns the Process object (PID).
function Start-Server {
  Stop-OldServer $Port
  Remove-Item $Log, $LogErr -ErrorAction SilentlyContinue

  Write-Host 'Starting server (model load ~30-60s on first run)...'
  # NB: Windows PowerShell 5.1 Start-Process forbids the same file for both
  # stdout and stderr redirects, so keep separate logs.
  return Start-Process -FilePath (Resolve-Path $Python).Path -ArgumentList '-u -m server' `
    -RedirectStandardOutput $Log -RedirectStandardError $LogErr -WindowStyle Hidden -PassThru
}

# Background tail of both log files -> job output; Receive-Job prints it live.
function Start-LogTail {
  Start-Job -ScriptBlock {
    param($log, $logErr)
    # -Wait follows the files like `tail -f`; SilentlyContinue covers the
    # window where a just-restarted server hasn't recreated them yet.
    Get-Content $log, $logErr -Tail 40 -Wait -ErrorAction SilentlyContinue
  } -ArgumentList $Log, $LogErr
}

Write-Host ''
Write-Host "Supervision loop started - backend logs stream below. Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "URL: $Url | logs: $Log , $LogErr" -ForegroundColor DarkGray
Write-Host ''

$restartCount = 0
while ($true) {
  $proc = Start-Server
  $tailJob = Start-LogTail

  # --- wait for first healthy response ---
  $ready = $false
  for ($i = 0; $i -lt 90; $i++) {
    Receive-Job $tailJob | Write-Host   # stream startup logs (model load etc.)
    if (Test-Health) { $ready = $true; break }
    if ($proc.HasExited) { break }
    Start-Sleep 2
  }

  if (-not $ready) {
    Write-Host "Server failed to become healthy (restart #$restartCount). Last log lines:" -ForegroundColor Red
    if (Test-Path $Log)    { Get-Content $Log    -Tail 25 | ForEach-Object { Write-Host "  $_" } }
    if (Test-Path $LogErr) { Get-Content $LogErr -Tail 25 | ForEach-Object { Write-Host "  $_" -ForegroundColor Red } }
    Stop-Job $tailJob -ErrorAction SilentlyContinue; Remove-Job $tailJob -Force -ErrorAction SilentlyContinue
    if ($proc.HasExited) { Write-Host "Server process exited (code $($proc.ExitCode)) - restarting in 5s..." -ForegroundColor Red }
    Start-Sleep 5
    continue   # loop: try again
  }

  Write-Host "Server ready - open $Url in your browser if it didn't open." -ForegroundColor Green
  Start-Process $Url

  # --- supervision: stream logs live, restart on crash or dead health ---
  $misses = 0
  while ($true) {
    Receive-Job $tailJob | Write-Host   # live backend logs (planner/TTS/WS lines)
    if ($proc.HasExited) {
      Write-Host "Server process exited unexpectedly - restarting..." -ForegroundColor Red
      break
    }
    if (Test-Health) {
      $misses = 0
    } else {
      $misses++
      if ($misses -ge 10) {   # ~30s of dead health with a live process = hung; restart
        Write-Host "Health check failed 10x - server appears hung - restarting..." -ForegroundColor Red
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
        break
      }
    }
    Start-Sleep 3
  }

  $restartCount++
  Stop-Job $tailJob -ErrorAction SilentlyContinue; Remove-Job $tailJob -Force -ErrorAction SilentlyContinue
  try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
  Start-Sleep 2
  # outer while ($true) restarts the server
}
