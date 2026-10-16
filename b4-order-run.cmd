@echo off
rem B4 paid lot (Jev only, about 0.05 USD, hard cap 0.10 in the ledger), sealed in
rem docs/results/2026-10-16-b4-order/prereg.md: prereg.sha256 holds the sha256 of this file with
rem the two values below read as placeholders. Run it from the detached worktree at the sealed
rem commit, outside the Claude Code session (WMI), once; run.py allows one relaunch, none after a
rem 402, a 429 or the cap. Fill PY and SANCHOPANZA_KEYS_ENV in that worktree's copy only; never
rem commit them. The key is read from the file SANCHOPANZA_KEYS_ENV names, never printed.
rem Exit codes of run.py paid: 0 everything asked, 1 refused (see the log), 2 stopped mid-run.
cd /d "%~dp0"
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
set "OUT=%USERPROFILE%\.cache\sanchopanza\b4-order"
if not exist "%OUT%" mkdir "%OUT%"
echo start %DATE% %TIME% >> "%OUT%\launch.log"
git rev-parse HEAD >> "%OUT%\launch.log" 2>&1
"%PY%" -u benchmarks\passage_fit\run.py paid >> "%OUT%\launch.log" 2>&1
set RUNEXIT=%ERRORLEVEL%
echo paid-exit %RUNEXIT% %DATE% %TIME% >> "%OUT%\launch.log"
if "%RUNEXIT%"=="0" "%PY%" benchmarks\passage_fit\run.py report >> "%OUT%\launch.log" 2>&1
if "%RUNEXIT%"=="0" echo report-exit %ERRORLEVEL% %DATE% %TIME% >> "%OUT%\launch.log"
exit /b %RUNEXIT%
