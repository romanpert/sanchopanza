# Starts h2h_gaia.py --live outside the calling session, the way long paid batches on this PC
# survive: through WMI (not this shell's process tree), in a new process group (CreateFlags 512,
# so a stray Ctrl+C on another console cannot reach it), with the pinned Claude Code 2.1.287
# first on PATH for that process only. Its own log goes to -Log; the runner logs its sessions
# beside ~/.cache/sanchopanza/gaia/h2h/sessions.jsonl.
#
#   powershell -File benchmarks/h2h/launch.ps1 -RunnerArgs "--models HAIKU --limit 2 --ceiling 2"
#
# It prints the PID; stop it by that PID only (Stop-Process -Id), never by image name.
param(
    [Parameter(Mandatory = $true)][string]$RunnerArgs,
    [string]$Log = "$env:USERPROFILE\.cache\sanchopanza\gaia\h2h\launch.log",
    [string]$Pin = 'C:\Users\roman\AppData\Local\Temp\claude\c--Users-roman-Desktop-proyectos-apps-indagis\ed2adcce-a92b-4af9-bb31-96872de0c1cd\scratchpad\pin'
)
$worktree = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py = 'C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe'
if (-not (Test-Path "$Pin\claude.exe")) { throw "no pinned claude.exe in $Pin" }
New-Item -ItemType Directory -Force (Split-Path -Parent $Log) | Out-Null
$cmdFile = Join-Path (Split-Path -Parent $Log) 'launch.cmd'
@"
@echo off
set PATH=$Pin;%PATH%
set PYTHONPATH=$worktree\src
set PYTHONIOENCODING=utf-8
cd /d $worktree
echo START %DATE% %TIME% > "$Log"
"$py" benchmarks\h2h\h2h_gaia.py --live $RunnerArgs >> "$Log" 2>&1
echo EXIT %ERRORLEVEL% %DATE% %TIME% >> "$Log"
"@ | Set-Content -Encoding ascii $cmdFile
$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ CreateFlags = [uint32]512 }
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "cmd.exe /c `"$cmdFile`""; CurrentDirectory = $worktree; ProcessStartupInformation = $startup
}
"ReturnValue=$($r.ReturnValue) PID=$($r.ProcessId) log=$Log"
