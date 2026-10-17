@echo off
rem Long bench, smoke chain (STATUS-launch.md; HANDOFF-2026-10-06 "Lista de lanzamiento" item 2).
rem Haiku 4.5, pydantic__pydantic-long60-1, first 3 bugs (+2 callbacks), arms N / N-early / S.
rem Caps (owner USD, in code): 1.00 per call, 2.00 per arm, hard ceiling 8 for the whole root.
rem S runs the FROZEN sanchopanza of the seal commit given as the first argument (freeze.py) and
rem is checked with `python -m sanchopanza jev-preflight` first: a non-zero exit (10 no_funds,
rem 11 auth, 12 no_key, 13 unreachable, 14 other) ends the launch before any model is asked.
rem Start it by WMI, outside any Claude Code session, and never twice at once:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\long-smoke-run.cmd <seal commit>" }
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem PIDs: C:\sp-runs\L-smoke\launch.json. Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root C:\sp-runs\L-smoke` (verified PID only).
rem Second argument `dry` (tests only): LL_ROOT, LL_PIN, LL_MANIFESTS, LL_DRY_CONFIG replace the
rem root, the pinned Claude Code folder, the manifests and the runner (a stand-in claude).
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
rem PY: SANCHOPANZA_PY, else the .venv of the main checkout (the folder above git's common
rem directory, which this worktree shares; the only checkout with a .venv). Checked below.
set "PY=%SANCHOPANZA_PY%"
if not defined PY for /f "delims=" %%G in ('git -C "%~dp0." rev-parse --path-format^=absolute --git-common-dir 2^>nul') do set "PY=%%~dpG.venv\Scripts\python.exe"
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set ROOT=C:\sp-runs\L-smoke
set MANIFESTS=%WT%\benchmarks\adopt\long60
set CHAIN=pydantic__pydantic-long60-1
set SEAL=%~1
set DRY=
if /i "%~2"=="dry" (
  set ROOT=%LL_ROOT%
  set PIN=%LL_PIN%
  set MANIFESTS=%LL_MANIFESTS%
  set DRY=--dry-config "%LL_DRY_CONFIG%"
)
if "%SEAL%"=="" (
  echo usage: long-smoke-run.cmd ^<sealed S commit^>
  exit /b 1
)
cd /d "%WT%"
set PATH=%PIN%;%PATH%
set PYTHONPATH=%WT%\src
set DISABLE_AUTOUPDATER=1
set ADOPT_PYTHON=%PY%
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
if not exist "%PY%" (
  echo refused %DATE% %TIME%: no python, neither SANCHOPANZA_PY nor the main checkout's .venv >> "%STATUS%"
  exit /b 2
)
echo start %DATE% %TIME% smoke seal %SEAL% %DRY% >> "%STATUS%"
if not exist "%MANIFESTS%\%CHAIN%.json" (
  echo refused %DATE% %TIME%: no manifest %MANIFESTS%\%CHAIN%.json ^(validate the chain first^) >> "%STATUS%"
  exit /b 1
)
where claude >> "%STATUS%" 2>&1
call claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused %DATE% %TIME%: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
"%PY%" -u benchmarks\adopt\long_launch.py smoke --seal %SEAL% --root "%ROOT%" %DRY% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
