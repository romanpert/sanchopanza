@echo off
rem Lot jev114-redundant-drop (docs/results/2026-10-16-redundant-drop/prereg.md): redundant_page
rem on 1.13 and 1.14 over the 125 retrieval bench cases and 405 generated cases. Jev only, no
rem Claude: 1,060 calls, about 0.034 USD expected, BATCH_CAP 0.10 USD in code on the shared
rem ledger C:\sp-runs\jev114\ledger.json (4.50 USD cap). An attended launch: about 5 minutes.
rem Start it by WMI from a worktree --detach at the sealing commit, outside any Claude Code
rem session, in its own process group, and never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\redundant-drop-run.cmd"; ProcessStartupInformation = $s }
rem The runner refuses unless HEAD is the sealing commit, the worktree is clean and every sealed
rem file and input is as sealed; it preflights both versions first. Relaunch from the same
rem worktree (one relaunch at most): the recordings live in the run folder, not in the worktree.
rem Stop between calls: a STOP file in C:\sp-runs\jev114\redundant-drop. Kill only by verified PID.
rem SANCHOPANZA_KEYS_ENV below is filled in before the seal (a path only; this file is sealed;
rem the key is read inside the process and never printed).
rem   redundant-drop-run.cmd        the paid run
rem   redundant-drop-run.cmd dry    the free plan through the same environment
setlocal
set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set SANCHOPANZA_JEV114_RUN=C:\sp-runs\jev114
set ROOT=C:\sp-runs\jev114\redundant-drop
set MODE=--paid
if /i "%~1"=="dry" set MODE=--dry
if not "%~1"=="" if /i not "%~1"=="dry" (
  echo refused: the only argument is [dry]
  exit /b 2
)
if "%MODE%"=="--paid" if "%SANCHOPANZA_KEYS_ENV%"=="<KEYS_ENV_PATH>" (
  echo refused: SANCHOPANZA_KEYS_ENV is still the placeholder
  exit /b 2
)
cd /d "%WT%"
set PYTHONPATH=%WT%\src
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
echo start %DATE% %TIME% %MODE% >> "%STATUS%"
"%PY%" -u benchmarks\jev114\redundant_drop.py run %MODE% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
