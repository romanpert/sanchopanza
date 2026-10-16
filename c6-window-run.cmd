@echo off
rem C6 paid lot (Jev only, about 2.5-3.3 USD expected, hard cap 6.00 in the ledger), sealed in
rem docs/results/2026-10-16-c6-window/prereg.md: prereg.sha256 holds the sha256 of this file with
rem the two values below read as placeholders. Build the input first (c6_window.py build, free,
rem offline from B6's MLQA archive and article cache), then run this from the detached worktree at
rem the sealed commit, outside the Claude Code session (WMI, CreateFlags 512), never between 02:00
rem and 08:00, once; c6_window.py allows one relaunch, none after a 402, a 429 or the cap. Fill PY
rem and SANCHOPANZA_KEYS_ENV in that worktree's copy only; never commit them. The key is read from
rem the file SANCHOPANZA_KEYS_ENV names, never printed. Stop: Get-CimInstance Win32_Process with
rem c6_window.py in its command line, then Stop-Process -Id <pid>. Never by name.
rem Exit codes of c6_window.py paid: 0 everything asked, 1 refused (see the log), 2 stopped mid-run.
cd /d "%~dp0"
set "HOUR=%TIME:~0,2%"
set "HOUR=%HOUR: =0%"
if "%HOUR%" LSS "08" (
  echo refused: not between 00:00 and 08:00 ^(Windows Update restarts, midnight^)
  exit /b 1
)
set "PY=<PYTHON>"
set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"
set "PYTHONPATH=%~dp0src"
if "%PY%"=="<PYTHON>" (
  echo refused: set PY in this copy
  exit /b 1
)
if "%SANCHOPANZA_KEYS_ENV%"=="<KEYS_ENV_PATH>" (
  echo refused: set SANCHOPANZA_KEYS_ENV in this copy
  exit /b 1
)
set "OUT=%USERPROFILE%\.cache\sanchopanza\c6-window"
if not exist "%OUT%" mkdir "%OUT%"
echo start %DATE% %TIME% >> "%OUT%\launch.log"
git rev-parse HEAD >> "%OUT%\launch.log" 2>&1
"%PY%" -I -u benchmarks\b6_es\c6_window.py paid --launcher "%~f0" >> "%OUT%\launch.log" 2>&1
set RUNEXIT=%ERRORLEVEL%
echo paid-exit %RUNEXIT% %DATE% %TIME% >> "%OUT%\launch.log"
if "%RUNEXIT%"=="0" "%PY%" -I benchmarks\b6_es\c6_window.py report >> "%OUT%\launch.log" 2>&1
if "%RUNEXIT%"=="0" echo report-exit %ERRORLEVEL% %DATE% %TIME% >> "%OUT%\launch.log"
exit /b %RUNEXIT%
