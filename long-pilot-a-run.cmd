@echo off
rem Long bench, pilot of bet A: passages on arrival (benchmarks/adopt/long_pilot.py).
rem Arm A (N + `sanchopanza install --passages --provider jev`, 25 %%) or A10 (--passages-fraction
rem 0.10), nothing else installed (the runner keeps the passages hook alone and checks it), on
rem conan-io__conan-long60-1 and pydantic__pydantic-long60-1 with claude-sonnet-5-5: the gate's
rem chains, model and caps, compared with the gate's N rows (pilot_a_compare.py, free).
rem Caps (owner USD, in code): 4.50 per call (--max-budget-usd 3.00) and 38 per chain; hard
rem ceiling 80 per root (2 x 38 = 76 held). A: C:\sp-runs\L-pilot-a; A10: C:\sp-runs\L-pilot-a10.
rem The arm runs the FROZEN sanchopanza of the commit given first (freeze.py <commit>, free), which
rem must carry the 402 breaker and answer `passages-hook --help`; `python -m sanchopanza
rem jev-preflight` runs first: a non-zero exit (10 no_funds, 11 auth, 12 no_key, 13 unreachable,
rem 14 other) ends the launch before any model is asked. An arm whose cuts are asked again whole
rem more than half the time (after >= 10 cuts) stops: stopped "rerequest", exit 5.
rem Start it by WMI, outside any Claude Code session, and never twice at once:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\long-pilot-a-run.cmd <commit> A" }
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem PIDs: <root>\launch.json. Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root <root>` (verified PID only).
rem Third argument `dry` (tests only): LL_ROOT, LL_PIN, LL_MANIFESTS, LL_DRY_CONFIG replace the
rem root, the pinned Claude Code folder, the manifests and the runner (a stand-in claude).
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=%USERPROFILE%\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set MANIFESTS=%WT%\benchmarks\adopt\long60
set COMMIT=%~1
set ARM=%~2
if "%ARM%"=="" set ARM=A
if "%COMMIT%"=="" goto usage
if /i "%ARM%"=="A" (
  set ARM=A
  set ROOT=C:\sp-runs\L-pilot-a
) else if /i "%ARM%"=="A10" (
  set ARM=A10
  set ROOT=C:\sp-runs\L-pilot-a10
) else (
  goto usage
)
set DRY=
if /i "%~3"=="dry" (
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
echo start %DATE% %TIME% pilot-a %ARM% commit %COMMIT% %DRY% >> "%STATUS%"
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
"%PY%" -u benchmarks\adopt\long_launch.py pilot-a --commit %COMMIT% --arm %ARM% --root "%ROOT%" %DRY% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%

:usage
echo usage: long-pilot-a-run.cmd ^<commit frozen with freeze.py^> [A^|A10]
exit /b 1
