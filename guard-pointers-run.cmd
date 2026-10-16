@echo off
rem The guard-pointers lot (owner 2026-10-16; docs/results/2026-10-16-guard-pointers/prereg.md):
rem P, the default `sanchopanza install` (after a compaction the guard attaches the requests, the
rem files changed and pointers to archived output), against F, the same install with --guard-full
rem (the whole earlier results in 6 parts). No decider key in either arm: the null decider, no Jev
rem and no preflight. Sonnet 5.5, one run per arm and chain, Claude Code 2.1.287 pinned.
rem   guard-pointers-run.cmd <seal>         the five chains, 4.50 a call, 25 a run, 250 USD hard
rem                                         (profile guardptr, root C:\sp-runs\L-guardptr)
rem   guard-pointers-run.cmd <seal> 30      the first 30 bugs of each, 18 a run, 180 USD hard
rem                                         (profile guardptr-30, root C:\sp-runs\L-guardptr30)
rem   guard-pointers-run.cmd <seal> smoke   Haiku, 3 bugs of pydantic-1, both arms compacting near
rem                                         67k, 8 USD hard (root C:\sp-runs\L-guardptr-smoke)
rem <seal>: the instrument commit, the sealing commit's parent (named in the sealing commit's
rem message), frozen first with `python benchmarks\adopt\freeze.py <seal>` (free).
rem THIS FILE HOLDS PLACEHOLDERS ONLY. Copy it to the run's root (untracked) and fill PY (the
rem venv's python) and WT (the worktree --detach at the SEALING commit) there. The seal reads those
rem two values as placeholders, so the filled copy keeps the seal; long_launch.py refuses unless
rem the copy that ran (ADOPT_LAUNCHER, set below) equals this file but for them, HEAD is the
rem sealing commit (one parent, only the seal files), the tree is clean and the seal matches
rem (benchmarks/adopt/guardptr_seal.py). HEAD goes into launch.status.
rem Start the filled copy by WMI, outside any Claude Code session, in its own process group, at
rem 08:05 or later, and never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <root>\guard-pointers-run.cmd <seal>"; ProcessStartupInformation = $s }
rem A chain starts only if it ends before midnight, not between 00:00 and 08:00 (Windows Update
rem restarts the PC in 02:00-08:00) and not while Windows says a restart is pending.
rem Run it again to resume: finished arms are skipped, a stopped arm goes on at its next request.
rem Stop: a STOP file in the root (between calls), or
rem `python benchmarks\adopt\long_run.py kill --root <root>` (verified PID only).
rem Last argument `dry` (tests only): LL_ROOT, LL_PIN, LL_DRY_CONFIG replace the root, the pinned
rem Claude Code folder and the runner (a stand-in claude; the dry config names the manifests).
rem `dry` with any of the three unset is refused: it would fall back to the real root and runner.
setlocal
set "PY=<PYTHON>"
set "WT=<WORKTREE>"
if "%PY%"=="<PYTHON>" (
  echo refused: fill PY in the run root's copy
  exit /b 2
)
if "%WT%"=="<WORKTREE>" (
  echo refused: fill WT in the run root's copy
  exit /b 2
)
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set SEAL=%~1
set PROFILE=guardptr
set ROOT=C:\sp-runs\L-guardptr
set DRYARG=%~2
if "%SEAL%"=="" goto usage
if /i "%SEAL%"=="dry" goto usage
if /i "%~2"=="30" (
  set PROFILE=guardptr-30
  set ROOT=C:\sp-runs\L-guardptr30
  set DRYARG=%~3
)
if /i "%~2"=="smoke" (
  set PROFILE=guardptr-smoke
  set ROOT=C:\sp-runs\L-guardptr-smoke
  set DRYARG=%~3
)
if not "%DRYARG%"=="" if /i not "%DRYARG%"=="dry" goto usage
set DRY=
set ISDRY=
if /i "%DRYARG%"=="dry" if "%LL_ROOT%"=="" goto nodry
if /i "%DRYARG%"=="dry" if "%LL_PIN%"=="" goto nodry
if /i "%DRYARG%"=="dry" if "%LL_DRY_CONFIG%"=="" goto nodry
if /i "%DRYARG%"=="dry" (
  set ROOT=%LL_ROOT%
  set PIN=%LL_PIN%
  set DRY=--dry-config "%LL_DRY_CONFIG%"
  set ISDRY=1
)
set "ADOPT_LAUNCHER=%~f0"
cd /d "%WT%"
set PATH=%PIN%;%PATH%
set "PYTHONPATH=%WT%\src"
set DISABLE_AUTOUPDATER=1
set "ADOPT_PYTHON=%PY%"
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
echo start %DATE% %TIME% %PROFILE% seal %SEAL% %DRY% >> "%STATUS%"
git rev-parse HEAD >> "%STATUS%" 2>&1
if not defined ISDRY (
  reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired" > nul 2>&1 && (
    echo refused %DATE% %TIME%: Windows Update has a restart pending >> "%STATUS%"
    exit /b 6
  )
  reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending" > nul 2>&1 && (
    echo refused %DATE% %TIME%: Windows servicing has a restart pending >> "%STATUS%"
    exit /b 6
  )
)
where claude >> "%STATUS%" 2>&1
call claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused %DATE% %TIME%: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
"%PY%" -u benchmarks\adopt\long_launch.py %PROFILE% --seal %SEAL% --root "%ROOT%" %DRY% >> "%ROOT%\launch.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
:usage
echo usage: guard-pointers-run.cmd ^<seal commit^> [30^|smoke] [dry]
exit /b 2
:nodry
echo refused: dry needs LL_ROOT, LL_PIN and LL_DRY_CONFIG
exit /b 2
