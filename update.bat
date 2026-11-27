<# :
@echo off
rem ============================================================================================================
rem  UPDATE THE SERVER FROM GITHUB (master) AND RESTART THE APPLICATION. The server's data is never replaced.
rem  Schedule it in Task Scheduler with "Run with highest privileges". Log: logs\update.log
rem ============================================================================================================
set "IT_ROOT=%~dp0"
set "IT_SELF=%~f0"
rem all on one line: Windows has read it before the update replaces this file
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-Expression (Get-Content -LiteralPath $env:IT_SELF -Raw)" & call exit /b %%errorlevel%%
#>
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $env:IT_ROOT
$root = (Get-Location).Path
$env:GIT_TERMINAL_PROMPT = '0'                       # a scheduled run fails instead of waiting for a password
$py = Join-Path $root 'venv\Scripts\python.exe'
$keep = Join-Path $root 'data_keep'                  # the server's data as it was just before the last update
$pending = Join-Path $keep 'NOT_YET_PUT_BACK'
$databases = 'database\master_system.db', 'database\newsletter_system.db'
$settings = 'config\form_mappings.json', 'config\section_categories.json', 'config\section_layouts.json', 'config\front_matter.json'
New-Item -ItemType Directory -Force (Join-Path $root 'logs') | Out-Null

function Log($text) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $text"
    Write-Host $line
    Add-Content -LiteralPath (Join-Path $root 'logs\update.log') -Value $line
}
function Git-Run {
    $ErrorActionPreference = 'Continue'              # git writes ordinary messages to the error stream
    $out = & git @args 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') failed: $($out -join ' ')" }
    $out
}
# a complete, checked copy of a database (includes what is still in the -wal file)
function Copy-Database($from, $to) {
    $code = @'
import sqlite3, sys
s = sqlite3.connect(sys.argv[1], timeout=60)
d = sqlite3.connect(sys.argv[2])
s.backup(d)
d.execute("PRAGMA journal_mode = DELETE")
ok = d.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
d.close()
s.close()
sys.exit(0 if ok else 1)
'@
    $code | & $py - $from $to
    if ($LASTEXITCODE -ne 0) { throw "Could not copy $from" }
}

# ---- the running application (BEGIN SERVER CONTROL)
function Get-Port {
    $line = Get-Content -LiteralPath (Join-Path $root '.env') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*PORT\s*=\s*\d+' } | Select-Object -Last 1
    if ($line) { [int]($line -replace '\D', '') } else { 8000 }
}
function Find-ServerTask {
    $found = @(Get-ScheduledTask | Where-Object { @($_.Actions | Where-Object { "$($_.Execute) $($_.Arguments)" -like '*start_app.bat*' }).Count -gt 0 })
    if ($found.Count -ne 1) { throw "Expected exactly one scheduled task that runs start_app.bat, found $($found.Count). Run this as an administrator." }
    $found[0]
}
function Get-ServerProcessIds($port) {
    $ids = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -like '*run_server.py*' -and "$($_.ExecutablePath) $($_.CommandLine)" -like "*$root\*" } | ForEach-Object { $_.ProcessId })
    foreach ($c in @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -like 'python*') { $ids += $p.Id }
    }
    @($ids | Sort-Object -Unique)
}
function Stop-App($task) {
    $port = Get-Port
    Stop-ScheduledTask -InputObject $task
    foreach ($id in Get-ServerProcessIds $port) {    # ending the task can leave Python running
        $ErrorActionPreference = 'Continue'
        & taskkill /PID $id /T /F 2>&1 | Out-Null
        $ErrorActionPreference = 'Stop'
    }
    foreach ($try in 1..30) {
        if (@(Get-ServerProcessIds $port).Count -eq 0 -and -not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { return }
        Start-Sleep -Seconds 1
    }
    throw "The application did not stop (port $port is still in use). Run this task with highest privileges."
}
function Start-App($task) { Start-ScheduledTask -InputObject $task }
function Test-App {
    $address = "http://127.0.0.1:$(Get-Port)/healthz"
    foreach ($try in 1..40) {
        try { if ((Invoke-WebRequest -Uri $address -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) { return $true } } catch { }
        Start-Sleep -Seconds 3
    }
    $false
}
# ---- (END SERVER CONTROL)

function Save-Data {
    if (Test-Path -LiteralPath $keep) { Remove-Item -LiteralPath $keep -Recurse -Force }
    New-Item -ItemType Directory -Force (Join-Path $keep 'database'), (Join-Path $keep 'config'), (Join-Path $keep 'output') | Out-Null
    foreach ($f in $databases) { if (Test-Path -LiteralPath $f) { Copy-Database $f (Join-Path $keep $f) } }
    foreach ($f in $settings) { if (Test-Path -LiteralPath $f) { Copy-Item -LiteralPath $f (Join-Path $keep $f) } }
    if (Test-Path 'output\uploads') { Copy-Item 'output\uploads' (Join-Path $keep 'output') -Recurse }
    Get-ChildItem 'output\*.docx' -ErrorAction SilentlyContinue | Copy-Item -Destination (Join-Path $keep 'output')
    Set-Content -LiteralPath $pending -Value 'The data in this folder still has to be put back.'
}
function Restore-Data {
    New-Item -ItemType Directory -Force 'database', 'config', 'output\uploads' | Out-Null
    foreach ($f in $databases) {
        if (Test-Path -LiteralPath (Join-Path $keep $f)) {
            foreach ($extra in "$f-wal", "$f-shm") { if (Test-Path -LiteralPath $extra) { Remove-Item -LiteralPath $extra -Force } }
            Copy-Item -LiteralPath (Join-Path $keep $f) $f -Force
        }
    }
    foreach ($f in $settings) { if (Test-Path -LiteralPath (Join-Path $keep $f)) { Copy-Item -LiteralPath (Join-Path $keep $f) $f -Force } }
    if (Test-Path (Join-Path $keep 'output\uploads')) { Copy-Item (Join-Path $keep 'output\uploads\*') 'output\uploads' -Recurse -Force }
    Get-ChildItem (Join-Path $keep 'output\*.docx') -ErrorAction SilentlyContinue | Copy-Item -Destination 'output' -Force
    Remove-Item -LiteralPath $pending
}

try {
    $branch = Git-Run rev-parse --abbrev-ref HEAD
    if ($branch -ne 'master') { throw "This folder is on branch '$branch', not master." }
    if (Test-Path -LiteralPath $pending) { throw "An earlier update did not finish putting the data back. Copy the files in data_keep into the project, then delete data_keep\NOT_YET_PUT_BACK." }
    Git-Run fetch origin master | Out-Null
    $old = Git-Run rev-parse HEAD
    $new = Git-Run rev-parse origin/master
    $ahead = Git-Run rev-list --count "HEAD..origin/master"
    if ($ahead -eq '0') { Log 'Already up to date.'; exit 0 }
    if (-not (Test-Path -LiteralPath 'database\master_system.db')) { throw 'database\master_system.db was not found, so nothing was changed.' }
    $task = Find-ServerTask
    Log "Updating $($old.Substring(0, 7)) -> $($new.Substring(0, 7)). Stopping the application."
    try {
        Stop-App $task
        Save-Data
        try {
            Git-Run reset --hard origin/master | Out-Null      # the code becomes exactly what is on GitHub's master
        }
        finally {
            Restore-Data                                        # and the data becomes exactly what the server had
        }
        Log 'Code updated; the server data was kept.'
        $ErrorActionPreference = 'Continue'
        & $py -m pip install --disable-pip-version-check -q -r requirements.txt 2>&1 | Out-Null
        $installed = $LASTEXITCODE -eq 0
        $ErrorActionPreference = 'Stop'
        if (-not $installed) { Log 'WARNING: installing requirements.txt failed.' }
    }
    finally {
        Start-App $task                                         # whatever happened, the application is started again
        Log 'Application started.'
    }
    if (-not (Test-App)) { throw "The application did not answer after the update. See logs\api.log. The previous code was $old." }
    Log 'SUCCESS: the application is running the new code.'
    exit 0
}
catch {
    Log "FAILED: $($_.Exception.Message)"
    exit 1
}
