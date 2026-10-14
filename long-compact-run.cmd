@echo off
rem The context close-out on the long bench (owner 2026-10-13, 250 USD hard in code;
rem docs/results/2026-10-13-long-compact/prereg.md): N-early (Ne, window 193000, compacts near 160k)
rem against N-early-low (Nl, window 100000, compacts near 67k), Sonnet 5.5, one run per arm and
rem chain, root C:\sp-runs\L-compact, 4.50 a call, 25 a run. No S arm: no Jev, no preflight.
rem   long-compact-run.cmd          the chains of long_run.COMPACT_CHAINS (profile compact)
rem   long-compact-run.cmd fifth    the fifth chain once it validates (profile compact-fifth)
rem   long-compact-run.cmd extra    the conditional sixth chain (profile compact-extra, prereg 3)
rem The three under the same root and the same 250 USD ceiling over everything in it.
rem   long-compact-run.cmd conan2   the conan-2 repeat (profile compact-conan2, owner 2026-10-14;
rem                                 amendment-conan2.md): its own root C:\sp-runs\L-compact-conan2,
rem                                 22.5 a run, 45 USD hard in code
rem Start it by WMI from a worktree --detach at the sealed commit, outside any Claude Code session,
rem in its own process group, and never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\long-compact-run.cmd [fifth|extra|conan2]";
rem     ProcessStartupInformation = $s }   (the repeat needs `conan2`: without it, L-compact runs)
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root <root>` (verified PID only; the repeat's root
rem is C:\sp-runs\L-compact-conan2).
rem Last argument `dry` (tests only): LL_ROOT, LL_PIN, LL_DRY_CONFIG replace the root, the pinned
rem Claude Code folder and the runner (a stand-in claude; the dry config names the manifests).
rem `dry` with any of the three unset is refused: it would fall back to the real root and runner.
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set ROOT=C:\sp-runs\L-compact
set PROFILE=compact
set DRYARG=%~1
if /i "%~1"=="fifth" (
  set PROFILE=compact-fifth
  set DRYARG=%~2
)
if /i "%~1"=="extra" (
  set PROFILE=compact-extra
  set DRYARG=%~2
)
if /i "%~1"=="conan2" (
  set PROFILE=compact-conan2
  set ROOT=C:\sp-runs\L-compact-conan2
  set DRYARG=%~2
)
if not "%DRYARG%"=="" if /i not "%DRYARG%"=="dry" (
  echo refused: the arguments are [fifth^|extra^|conan2] [dry]
  exit /b 2
)
set DRY=
if /i "%DRYARG%"=="dry" if "%LL_ROOT%"=="" goto nodry
if /i "%DRYARG%"=="dry" if "%LL_PIN%"=="" goto nodry
if /i "%DRYARG%"=="dry" if "%LL_DRY_CONFIG%"=="" goto nodry
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
:nodry
echo refused: dry needs LL_ROOT, LL_PIN and LL_DRY_CONFIG
exit /b 2
