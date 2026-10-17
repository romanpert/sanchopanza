@echo off
rem W17, memory at user scope against clean Claude Code (docs/results/2026-10-16-memory-w17/prereg.md),
rem on F2's runner: handoff_night.py --lot w17. Amendment 1 (2026-10-17): this launcher runs only
rem the Opus redo, w17-opus, in a new root C:\sp-runs\memory-w17-redo (agents in C:\sp-runs\w19);
rem the interrupted run's C:\sp-runs\memory-w17 and C:\sp-runs\w18 are evidence, never touched
rem (handoff_night.py refuses them, exit 11). w17-sonnet ran and is published: refused here.
rem The run cap is 33 USD at list price, in code. Runs from a detached worktree at the sealing
rem commit, started by WMI outside any Claude Code session, never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\memlot-night-run.cmd opus"; CurrentDirectory = "<this folder>";
rem     ProcessStartupInformation = $s }
rem   memlot-night-run.cmd opus      only w17-opus (the redo)
rem   memlot-night-run.cmd dry       builds every arm of w17-opus under %ROOT%\dry, calls nothing
rem Run it again to resume (after a crash, a reboot or a removed LIMIT.flag): recorded arms are
rem kept. No arm starts that would run into 02:00-08:00 (exit 8) unless Windows Update is paused
rem at least 24 h past that arm's check and no restart is pending (winupdate.quiet_lifted,
rem handoff.restart_pending; the log says so). Launch by day, 08:00-21:30. Stop between
rem arms: a STOP file in the root. Now: Get-CimInstance Win32_Process by command line, then
rem Stop-Process -Id (never by name).
rem The token and the TypeSafe key are read by carry.py from the file SANCHOPANZA_KEYS_ENV names
rem (a WMI process inherits no window variable); the token reaches only claude, the key only S's
rem hooks. That path is not in this file: the lead writes %ROOT%\keys-env.cmd, an untracked file
rem outside the repository holding only `set SANCHOPANZA_KEYS_ENV=<path>`. The launcher checks
rem that the file it names exists and never reads it.
rem The Python is not in this file either: %ROOT%\python-env.cmd, untracked, holds only
rem `set PY=<main checkout>\.venv\Scripts\python.exe` (refused, exit 1, without it).
rem The worktree's own path may not name the lot (S's installed hooks show it to the agent):
rem create it as, e.g., ..\sp-w19; a path with f2, memory, handoff, memlot, w17, sonnet or opus in
rem it is refused (exit 10). handoff_night.py itself refuses (exit 11) unless the files match the
rem seal, HEAD is the sealing commit and git status is clean.
rem Exits: 1 keys or Python, 2 arguments, 3 LIMIT.flag, 9 wrong claude version, 10 worktree path; then
rem handoff_night.py's (0 done, 2 cap, 3 limit, 4 harness, 6 STOP, 7 broken, 8 quiet, 11 seal or root).
setlocal
set ROOT=C:\sp-runs\memory-w17-redo
set SANCHOPANZA_KEYS_ENV=
if exist "%ROOT%\keys-env.cmd" call "%ROOT%\keys-env.cmd"
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=
if exist "%ROOT%\python-env.cmd" call "%ROOT%\python-env.cmd"
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
cd /d "%WT%"
set PATH=%PIN%;%PATH%
set PYTHONPATH=%WT%\src
set DISABLE_AUTOUPDATER=1
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
if "%PY%"=="" (
  echo refused %DATE% %TIME%: no PY, write %ROOT%\python-env.cmd >> "%STATUS%"
  exit /b 1
)
set ONLY=--only w17-opus
rem dry: Python runs from a one-line if, so CODE holds its own exit (inside a ( ) block
rem the errorlevel would be read before Python ran); the status line and the exit carry it.
if /i "%~1"=="dry" "%PY%" -u benchmarks\memory_carry\handoff_night.py --lot w17 --root "%ROOT%" %ONLY% --dry > "%ROOT%\dry.log" 2>&1
set CODE=%ERRORLEVEL%
if /i "%~1"=="dry" (
  echo dry-exit %CODE% %DATE% %TIME% >> "%STATUS%"
  exit /b %CODE%
)
if /i not "%~1"=="opus" (
  echo refused %DATE% %TIME%: the only arguments are opus and dry, got "%~1" >> "%STATUS%"
  exit /b 2
)
echo %WT%| findstr /i "f2 memory handoff memlot w17 sonnet opus" > nul && (
  echo refused %DATE% %TIME%: the worktree path %WT% names the lot >> "%STATUS%"
  exit /b 10
)
if "%SANCHOPANZA_KEYS_ENV%"=="" (
  echo refused %DATE% %TIME%: no SANCHOPANZA_KEYS_ENV, write %ROOT%\keys-env.cmd >> "%STATUS%"
  exit /b 1
)
if not exist "%SANCHOPANZA_KEYS_ENV%" (
  echo refused %DATE% %TIME%: the keys file SANCHOPANZA_KEYS_ENV names does not exist >> "%STATUS%"
  exit /b 1
)
if exist "%ROOT%\LIMIT.flag" (
  echo refused %DATE% %TIME%: LIMIT.flag, a usage limit paused the night >> "%STATUS%"
  exit /b 3
)
echo start %DATE% %TIME% %ONLY% >> "%STATUS%"
git rev-parse HEAD >> "%STATUS%" 2>&1
git status --porcelain --untracked-files=no >> "%STATUS%" 2>&1
"%PY%" -c "import sanchopanza; print(sanchopanza.__file__)" >> "%STATUS%" 2>&1
where claude >> "%STATUS%" 2>&1
call claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused %DATE% %TIME%: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 9
)
"%PY%" -u benchmarks\memory_carry\handoff_night.py --lot w17 --root "%ROOT%" %ONLY% >> "%ROOT%\night.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
