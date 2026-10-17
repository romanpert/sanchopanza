@echo off
rem F2, memory against the handoff ritual (docs/results/2026-10-16-memory-f2/prereg.md): one
rem unattended night, f2-pilot, its automatic gate, f2-sonnet, f2-opus (handoff_night.py), root
rem C:\sp-runs\memory-f2, NIGHT_CAP 230 USD at list price in code. Runs from a detached worktree at
rem the sealing commit, started by WMI outside any Claude Code session, never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this folder>\f2-night-run.cmd"; CurrentDirectory = "<this folder>";
rem     ProcessStartupInformation = $s }
rem Run it again to resume (after a crash, a reboot or a removed LIMIT.flag): recorded arms are
rem kept. Stop between arms: a STOP file in the root. Now: Get-CimInstance Win32_Process by command
rem line, then Stop-Process -Id (never by name).
rem   f2-night-run.cmd dry    builds every arm of the three runs under %ROOT%\dry, calls nothing.
rem The token and the TypeSafe key are read by carry.py from the file SANCHOPANZA_KEYS_ENV names
rem (a WMI process inherits no window variable); the token reaches only claude, the key only S's
rem hooks. That path is not in this file: the lead writes C:\sp-runs\memory-f2\keys-env.cmd, an
rem untracked file outside the repository holding only `set SANCHOPANZA_KEYS_ENV=<path>`. The
rem launcher checks that the file it names exists and never reads it.
rem The worktree's own path may not name the lot (S's installed hooks show it to the agent):
rem create it as, e.g., ..\sp-w16; a path with f2, memory or handoff in it is refused (exit 10).
rem handoff_night.py itself refuses (exit 11) unless the files match the seal, HEAD is the
rem sealing commit and git status is clean.
rem Exits: 1 keys, 2 arguments, 3 LIMIT.flag, 9 wrong claude version, 10 worktree path; then
rem handoff_night.py's (0 done, 2 cap, 3 limit, 4 harness, 5 gate, 6 STOP, 7 broken, 11 seal).
setlocal
set SANCHOPANZA_KEYS_ENV=
if exist C:\sp-runs\memory-f2\keys-env.cmd call C:\sp-runs\memory-f2\keys-env.cmd
set WT=%~dp0
set WT=%WT:~0,-1%
rem PY: SANCHOPANZA_PY, else the .venv of the main checkout (the folder above git's common
rem directory, which this worktree shares; the only checkout with a .venv). Checked below.
set "PY=%SANCHOPANZA_PY%"
if not defined PY for /f "delims=" %%G in ('git -C "%~dp0." rev-parse --path-format^=absolute --git-common-dir 2^>nul') do set "PY=%%~dpG.venv\Scripts\python.exe"
set ROOT=C:\sp-runs\memory-f2
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
cd /d "%WT%"
set PATH=%PIN%;%PATH%
set PYTHONPATH=%WT%\src
set DISABLE_AUTOUPDATER=1
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
if not exist "%PY%" (
  echo refused %DATE% %TIME%: no python, neither SANCHOPANZA_PY nor the main checkout's .venv >> "%STATUS%"
  exit /b 2
)
rem dry: Python runs from a one-line if, so CODE holds its own exit (inside a ( ) block
rem the errorlevel would be read before Python ran); the status line and the exit carry it.
if /i "%~1"=="dry" "%PY%" -u benchmarks\memory_carry\handoff_night.py --root "%ROOT%" --dry > "%ROOT%\dry.log" 2>&1
set CODE=%ERRORLEVEL%
if /i "%~1"=="dry" (
  echo dry-exit %CODE% %DATE% %TIME% >> "%STATUS%"
  exit /b %CODE%
)
if not "%~1"=="" (
  echo refused: the only argument is dry >> "%STATUS%"
  exit /b 2
)
echo %WT%| findstr /i "f2 memory handoff" > nul && (
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
echo start %DATE% %TIME% >> "%STATUS%"
git rev-parse HEAD >> "%STATUS%" 2>&1
git status --porcelain --untracked-files=no >> "%STATUS%" 2>&1
"%PY%" -c "import sanchopanza; print(sanchopanza.__file__)" >> "%STATUS%" 2>&1
where claude >> "%STATUS%" 2>&1
call claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused %DATE% %TIME%: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 9
)
"%PY%" -u benchmarks\memory_carry\handoff_night.py --root "%ROOT%" >> "%ROOT%\night.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
