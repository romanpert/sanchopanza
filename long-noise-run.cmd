@echo off
rem Long bench, window and noise round (owner 2026-10-07; STATUS-launch.md; PLAN-GANAR-H2H.md 6).
rem   long-noise-run.cmd ne   N-early (N + CLAUDE_CODE_AUTO_COMPACT_WINDOW 193000 in the project
rem                           settings' env) on conan-long60-1 and pydantic-long60-1, root L-ne,
rem                           Sonnet 5.5, 4.50 a call, 35 a chain, hard ceiling 70.
rem   long-noise-run.cmd n    N again on pydantic-long60-1, root L-n2, 4.50 a call, hard ceiling 40.
rem 70 + 40 = the 110 USD the owner approved. No S arm: no Jev, no preflight, no frozen copy.
rem Start it by WMI, outside any Claude Code session, and never twice at once:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\long-noise-run.cmd ne" }
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root <root>` (verified PID only).
rem Second argument `dry` (tests only): LL_ROOT, LL_PIN, LL_MANIFESTS, LL_DRY_CONFIG replace the
rem root, the pinned Claude Code folder, the manifests and the runner (a stand-in claude).
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set MANIFESTS=%WT%\benchmarks\adopt\long60
if /i "%~1"=="ne" (
  set PROFILE=noise-ne
  set ROOT=C:\sp-runs\L-ne
) else if /i "%~1"=="n" (
  set PROFILE=noise-n
  set ROOT=C:\sp-runs\L-n2
) else (
  echo refused: the first argument is ne or n
  exit /b 2
)
set DRY=
if /i "%~2"=="dry" (
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
echo start %DATE% %TIME% %PROFILE% %DRY% >> "%STATUS%"
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
"%PY%" -u benchmarks\adopt\long_launch.py %PROFILE% --root "%ROOT%" %DRY% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
