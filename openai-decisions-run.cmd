@echo off
rem D1 paid lot (OpenAI's Decisions API only, about 0.013-0.04 USD, hard cap 0.10 in the
rem ledger), sealed in docs/results/2026-10-16-openai-decisions/prereg.md: prereg.sha256 holds the
rem sha256 of this file with the two values below read as placeholders. Run it from the detached
rem worktree at the sealed commit, outside the Claude Code session (WMI), once; run.py allows one
rem relaunch, none after a 402, a 429 or the cap. Fill PY and SANCHOPANZA_KEYS_ENV in that
rem worktree's copy only; never commit them. OPENAI_API_KEY is read from the file
rem SANCHOPANZA_KEYS_ENV names, never printed.
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
set "OUT=%USERPROFILE%\.cache\sanchopanza\openai-decisions"
if not exist "%OUT%" mkdir "%OUT%"
echo start %DATE% %TIME% >> "%OUT%\launch.log"
git rev-parse HEAD >> "%OUT%\launch.log" 2>&1
"%PY%" -u benchmarks\openai_decisions\run.py paid >> "%OUT%\launch.log" 2>&1
set RUNEXIT=%ERRORLEVEL%
echo paid-exit %RUNEXIT% %DATE% %TIME% >> "%OUT%\launch.log"
if "%RUNEXIT%"=="0" "%PY%" benchmarks\openai_decisions\run.py report >> "%OUT%\launch.log" 2>&1
if "%RUNEXIT%"=="0" echo report-exit %ERRORLEVEL% %DATE% %TIME% >> "%OUT%\launch.log"
exit /b %RUNEXIT%
