@echo off
rem Lot W17 (benchmarks/a3_mcp/w17_prereg.md): the MCP guard after the call, a development replay
rem on A3's 500 ATBench-Codex trajectories. Jev only, no Claude: 1,188 calls, about 0.06-0.08 USD
rem expected, CAP_USD 0.20 ledger USD (batch cap the same) in code on C:\sp-runs\w17-mcp-post\
rem ledger.json. An attended launch, in the foreground of this process: about 2 minutes.
rem THIS FILE HOLDS PLACEHOLDERS ONLY. Copy it to C:\sp-runs\w17-mcp-post\ (untracked) and fill
rem PY, SANCHOPANZA_KEYS_ENV and WT (the worktree --detach at the sealing commit) there. The seal
rem reads those three values as placeholders, so the filled copy keeps the seal; the runner
rem refuses unless the copy that ran (SANCHOPANZA_LAUNCHER) equals this file but for them.
rem Start the filled copy by WMI, outside any Claude Code session, in its own process group:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <copy>\w17-mcp-post-run.cmd"; ProcessStartupInformation = $s }
rem The runner also refuses unless HEAD is the sealing commit and the worktree is clean. A cap stop
rem leaves the lot NOT RUN; a pause (outage, another model) is relaunched; three counted launches
rem at most. Kill only by verified PID. The key is read inside the process from the file named
rem below, never printed.
rem   w17-mcp-post-run.cmd        the paid run
rem   w17-mcp-post-run.cmd dry    the free plan through the same environment
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
set MODE=--run --live
set ROOT=C:\sp-runs\w17-mcp-post
if /i "%~1"=="dry" set MODE=--dry --dry-out %ROOT%\w17_dry.json
if not "%~1"=="" if /i not "%~1"=="dry" (
  echo refused: the only argument is [dry]
  exit /b 2
)
if /i not "%~1"=="dry" if "%SANCHOPANZA_KEYS_ENV%"=="<KEYS_ENV_PATH>" (
  echo refused: fill SANCHOPANZA_KEYS_ENV in the run folder's copy
  exit /b 2
)
set "SANCHOPANZA_LAUNCHER=%~f0"
cd /d "%WT%"
set "PYTHONPATH=%WT%\src"
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
echo start %DATE% %TIME% %MODE% >> "%STATUS%"
git rev-parse HEAD >> "%STATUS%" 2>&1
"%PY%" -u benchmarks\a3_mcp\w17_replay.py %MODE% --root %ROOT% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
