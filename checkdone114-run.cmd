@echo off
rem Lot jev114-checkdone (docs/results/2026-10-16-checkdone114/prereg.md): check_done at the 1.14
rem profile's 0.30 against 1.13 at 0.5 on 950 published AgentDojo trajectories. Jev only, no
rem Claude: 1,900 calls, about 0.13 USD expected, BATCH_CAP 0.25 USD in code on the shared ledger
rem C:\sp-runs\jev114\ledger.json (4.50 USD cap). An attended launch: about 10 minutes.
rem THIS FILE HOLDS PLACEHOLDERS ONLY. Copy it to C:\sp-runs\jev114\checkdone114\ (untracked) and
rem fill PY, SANCHOPANZA_KEYS_ENV and WT (the worktree --detach at the sealing commit) there. The
rem seal reads those three values as placeholders, so the filled copy keeps the seal; the runner
rem refuses unless the copy that ran (SANCHOPANZA_LAUNCHER) equals this file but for them.
rem Start the filled copy by WMI, outside any Claude Code session, in its own process group:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <copy>\checkdone114-run.cmd"; ProcessStartupInformation = $s }
rem The runner also refuses unless HEAD is the sealing commit and the worktree is clean. One
rem relaunch at most; a 402 is a pause (exit 6, no score, not counted): launch again once there
rem is balance. Stop between calls: a STOP file in C:\sp-runs\jev114\checkdone114. Kill only by
rem verified PID. The key is read inside the process from the file named below, never printed.
rem   checkdone114-run.cmd        the paid run
rem   checkdone114-run.cmd dry    the free plan through the same environment
setlocal
set "PY=<PYTHON>"
set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"
set "WT=<WORKTREE>"
if "%PY%"=="<PYTHON>" (
  echo refused: fill PY in the run folder's copy
  exit /b 2
)
if "%WT%"=="<WORKTREE>" (
  echo refused: fill WT in the run folder's copy
  exit /b 2
)
set MODE=--paid
if /i "%~1"=="dry" set MODE=--dry
if not "%~1"=="" if /i not "%~1"=="dry" (
  echo refused: the only argument is [dry]
  exit /b 2
)
if "%MODE%"=="--paid" if "%SANCHOPANZA_KEYS_ENV%"=="<KEYS_ENV_PATH>" (
  echo refused: fill SANCHOPANZA_KEYS_ENV in the run folder's copy
  exit /b 2
)
set "SANCHOPANZA_LAUNCHER=%~f0"
set SANCHOPANZA_JEV114_RUN=C:\sp-runs\jev114
set ROOT=C:\sp-runs\jev114\checkdone114
cd /d "%WT%"
set "PYTHONPATH=%WT%\src"
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
echo start %DATE% %TIME% %MODE% >> "%STATUS%"
git rev-parse HEAD >> "%STATUS%" 2>&1
"%PY%" -u benchmarks\jev114\checkdone114.py run %MODE% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
