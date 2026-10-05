# Starts an h2h runner (-Runner: h2h_gaia.py, h2h_bcp.py or h2h_longdoc.py) with --live outside
# the calling session, the way long paid batches on this PC
# survive: through WMI (not this shell's process tree), in a new process group (CreateFlags 512,
# so a stray Ctrl+C on another console cannot reach it), with the pinned Claude Code 2.1.287
# first on PATH for that process only. Its log (-Log) gets START and EXIT lines around the
# runner's output; the PIDs (the cmd.exe started by WMI and the runner's python.exe under it) go
# to -PidFile, a file of their own. The runner logs its sessions beside
# ~/.cache/sanchopanza/gaia/h2h/<phase>/sessions.jsonl.
#
#   powershell -File benchmarks/h2h/launch.ps1 -RunnerArgs "--phase dev --ids ... --ceiling 25" `
#       -Log C:\sp-runs\h2h\dev.log -PidFile C:\sp-runs\h2h\dev.pids
#
# Stop it by those PIDs only (Stop-Process -Id), never by image name. PowerShell names are
# case-blind: no variable here may be called $runner, which would be the validated -Runner.
param(
    [Parameter(Mandatory = $true)][string]$RunnerArgs,
    [ValidateSet('h2h_gaia.py', 'h2h_bcp.py', 'h2h_longdoc.py')][string]$Runner = 'h2h_gaia.py',
    [string]$Log = "$env:USERPROFILE\.cache\sanchopanza\gaia\h2h\launch.log",
    [string]$PidFile = "$env:USERPROFILE\.cache\sanchopanza\gaia\h2h\launch.pids",
    [string]$Pin = 'C:\Users\roman\AppData\Local\Temp\claude\c--Users-roman-Desktop-proyectos-apps-indagis\ed2adcce-a92b-4af9-bb31-96872de0c1cd\scratchpad\pin'
)
$worktree = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py = 'C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe'
if (-not (Test-Path "$Pin\claude.exe")) { throw "no pinned claude.exe in $Pin" }
New-Item -ItemType Directory -Force (Split-Path -Parent $Log) | Out-Null
New-Item -ItemType Directory -Force (Split-Path -Parent $PidFile) | Out-Null
$cmdFile = [System.IO.Path]::ChangeExtension($Log, '.cmd')
@"
@echo off
set PATH=$Pin;%PATH%
set PYTHONPATH=$worktree\src
set PYTHONIOENCODING=utf-8
cd /d $worktree
echo START %DATE% %TIME% > "$Log"
"$py" benchmarks\h2h\$Runner --live $RunnerArgs >> "$Log" 2>&1
echo EXIT %ERRORLEVEL% %DATE% %TIME% >> "$Log"
"@ | Set-Content -Encoding ascii $cmdFile
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ CreateFlags = [uint32]512 }
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "cmd.exe /c `"$cmdFile`""; CurrentDirectory = $worktree; ProcessStartupInformation = $startup
}
$runnerProc = $null
foreach ($i in 1..20) {
    $runnerProc = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($r.ProcessId) AND Name='python.exe'"
    if ($runnerProc) { break }
    Start-Sleep -Milliseconds 500
}
$runnerPid = if ($runnerProc) { ($runnerProc | Select-Object -First 1).ProcessId } else { 'not-found' }
# A venv's python.exe is a launcher that starts the base interpreter as its child: record both.
$base = 'none'
if ($runnerProc) {
    foreach ($i in 1..10) {
        $child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$runnerPid AND Name='python.exe'"
        if ($child) { $base = ($child | Select-Object -First 1).ProcessId; break }
        Start-Sleep -Milliseconds 500
    }
}
"cmd=$($r.ProcessId) runner=$runnerPid interpreter=$base started=$(Get-Date -Format s)" | Set-Content -Encoding ascii $PidFile
"ReturnValue=$($r.ReturnValue) cmd=$($r.ProcessId) runner=$runnerPid interpreter=$base log=$Log pids=$PidFile"
