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
rem hooks. The lead fills the next line before sealing.
set SANCHOPANZA_KEYS_ENV=__FILL_BEFORE_SEALING__
setlocal
set WT=%~dp0
set WT=%WT:~0,-1%
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set ROOT=C:\sp-runs\memory-f2
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
cd /d "%WT%"
set PATH=%PIN%;%PATH%
set PYTHONPATH=%WT%\src
set DISABLE_AUTOUPDATER=1
if not exist "%ROOT%" mkdir "%ROOT%"
set STATUS=%ROOT%\launch.status
if /i "%~1"=="dry" (
  "%PY%" -u benchmarks\memory_carry\handoff_night.py --root "%ROOT%" --dry > "%ROOT%\dry.log" 2>&1
  echo dry-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
  exit /b 0
)
if not "%~1"=="" (
  echo refused: the only argument is dry >> "%STATUS%"
  exit /b 2
)
if "%SANCHOPANZA_KEYS_ENV%"=="__FILL_BEFORE_SEALING__" (
  echo refused %DATE% %TIME%: SANCHOPANZA_KEYS_ENV is not filled in >> "%STATUS%"
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
  exit /b 3
)
"%PY%" -u benchmarks\memory_carry\handoff_night.py --root "%ROOT%" >> "%ROOT%\night.log" 2>&1
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
