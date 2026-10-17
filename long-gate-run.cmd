@echo off
rem Long bench, headroom gate (STATUS-launch.md; HANDOFF-2026-10-06 "Lista de lanzamiento" item 3).
rem Arm N only, clean user: conan-io__conan-long60-1 and pydantic__pydantic-long60-1 on
rem claude-sonnet-5-5, then on claude-opus-5-5 only if Sonnet exits 0. No S arm: no Jev, no
rem preflight. Caps (owner USD, in code): Sonnet 4.50 per call (--max-budget-usd 3.00) and 38 per
rem chain; Opus 8.00 per call (3.20) and 75 per chain; ceiling 230 (2x38 + 2x75 = 226 held).
rem Every call writes the session's own autocompact line (--debug=autocompact): N's server-set
rem window per model lands in C:\sp-runs\L\windows.json and the gate table (report.json).
rem Start it by WMI, outside any Claude Code session, and never twice at once:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\long-gate-run.cmd" }
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem PIDs: C:\sp-runs\L\launch.json. Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root C:\sp-runs\L` (verified PID only).
rem First argument `dry` (tests only): LL_ROOT, LL_PIN, LL_MANIFESTS, LL_DRY_CONFIG replace the
rem root, the pinned Claude Code folder, the manifests and the runner (a stand-in claude).
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
rem PY: SANCHOPANZA_PY, else the .venv of the main checkout (the folder above git's common
rem directory, which this worktree shares; the only checkout with a .venv). Checked below.
set "PY=%SANCHOPANZA_PY%"
if not defined PY for /f "delims=" %%G in ('git -C "%~dp0." rev-parse --path-format^=absolute --git-common-dir 2^>nul') do set "PY=%%~dpG.venv\Scripts\python.exe"
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set ROOT=C:\sp-runs\L
set MANIFESTS=%WT%\benchmarks\adopt\long60
set DRY=
if /i "%~1"=="dry" (
  set ROOT=%LL_ROOT%
  set PIN=%LL_PIN%
  set MANIFESTS=%LL_MANIFESTS%
  set DRY=--dry-config "%LL_DRY_CONFIG%"
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
echo start %DATE% %TIME% gate %DRY% >> "%STATUS%"
for %%C in (conan-io__conan-long60-1 pydantic__pydantic-long60-1) do (
  if not exist "%MANIFESTS%\%%C.json" (
    echo refused %DATE% %TIME%: no manifest %MANIFESTS%\%%C.json ^(validate the chain first^) >> "%STATUS%"
    exit /b 1
  )
)
where claude >> "%STATUS%" 2>&1
call claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused %DATE% %TIME%: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
"%PY%" -u benchmarks\adopt\long_launch.py gate --root "%ROOT%" %DRY% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
