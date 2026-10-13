@echo off
rem The context close-out on the long bench (owner 2026-10-13, 250 USD hard in code;
rem docs/results/2026-10-13-long-compact/prereg.md): N-early (Ne, window 193000, compacts near 160k)
rem against N-early-low (Nl, window 100000, compacts near 67k), Sonnet 5.5, one run per arm and
rem chain, root C:\sp-runs\L-compact, 4.50 a call, 25 a run. No S arm: no Jev, no preflight.
rem   long-compact-run.cmd          the chains of long_run.COMPACT_CHAINS (profile compact)
rem   long-compact-run.cmd extra    the conditional sixth chain (profile compact-extra, prereg 3):
rem                                 same root, the same 250 USD ceiling over everything in it
rem Start it by WMI from a worktree --detach at the sealed commit, outside any Claude Code session,
rem in its own process group, and never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\long-compact-run.cmd"; ProcessStartupInformation = $s }
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root C:\sp-runs\L-compact` (verified PID only).
rem Last argument `dry` (tests only): LL_ROOT, LL_PIN, LL_DRY_CONFIG replace the root, the pinned
rem Claude Code folder and the runner (a stand-in claude; the dry config names the manifests).
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set ROOT=C:\sp-runs\L-compact
set PROFILE=compact
set DRYARG=%~1
if /i "%~1"=="extra" (
  set PROFILE=compact-extra
  set DRYARG=%~2
)
if not "%DRYARG%"=="" if /i not "%DRYARG%"=="dry" (
  echo refused: the arguments are [extra] [dry]
  exit /b 2
)
set DRY=
if /i "%DRYARG%"=="dry" (
  set ROOT=%LL_ROOT%
  set PIN=%LL_PIN%
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
