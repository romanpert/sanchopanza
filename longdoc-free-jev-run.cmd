@echo off
rem Lot longdoc-free, phase J (Jev only): longdoc-free-jev-run.cmd dev ^| confirm ^| probe ^| dev2.
rem Hard caps in each phase's ledger: dev 1.80 USD (1.50 at its seal, 1.80 by amendment 1),
rem confirm 12.50 (the owner's 14.30 for the lot), probe 0.06, dev2 1.00. Sealed in
rem docs/results/2026-10-16-longdoc-free/prereg-dev.md and prereg.md: each prereg.sha256 holds
rem the sha256 of this file with the two values below read as placeholders. Run it from the
rem detached worktree at the sealed commit, outside the Claude Code session (WMI, CreateFlags
rem 512), never between 00:00 and 08:00, once per phase; jev_phase.py allows one relaunch, none
rem after a 402, a 429 or the cap. Fill PY and SANCHOPANZA_KEYS_ENV in that worktree's copy
rem only; never commit them. The key is read from the file SANCHOPANZA_KEYS_ENV names, never
rem printed. Stop: Get-CimInstance Win32_Process with jev_phase.py in its command line, then
rem Stop-Process -Id <pid>. Never by name.
rem Exit codes of jev_phase.py paid: 0 everything asked, 1 refused (see the log), 2 stopped mid-run.
rem Phase probe (the BM25 prefilter's probe, 3 dev questions at K = 200, ids and K in
rem jev_phase.py): sealed in docs/results/2026-10-17-lfree-bm25-dry/prereg-probe.md, its own
rem ledger capped at 0.06 USD (0.0626 at worst with calls in flight and the preflight, under
rem the owner's 0.10), one launch and never another. Results are committed from outside the
rem sealed run worktree, never with git add -A there: its filled copy of this file holds the
rem key file's path.
rem Phase dev2 (the 41 dev questions with the same prefilter at K = 200, fixed in
rem jev_phase.py): sealed in docs/results/2026-10-17-lfree-dev2/prereg-dev2.md, its own ledger
rem capped at 1.00 USD (1.0026 at worst with calls in flight and the preflight), one launch
rem and never another, its passages in the private cache under dev2.
cd /d "%~dp0"
set "PHASE=%~1"
if not "%PHASE%"=="dev" if not "%PHASE%"=="confirm" if not "%PHASE%"=="probe" if not "%PHASE%"=="dev2" (
  echo refused: the first argument is the phase, dev, confirm, probe or dev2
  exit /b 1
)
set "HOUR=%TIME:~0,2%"
set "HOUR=%HOUR: =0%"
if "%HOUR%" LSS "08" (
  echo refused: not between 00:00 and 08:00 ^(Windows Update restarts, midnight^)
  exit /b 1
)
set "PY=<PYTHON>"
set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"
rem -I ignores PYTHONPATH: each script puts this worktree's src on its path itself.
if "%PY%"=="<PYTHON>" (
  echo refused: set PY in this copy
  exit /b 1
)
if "%SANCHOPANZA_KEYS_ENV%"=="<KEYS_ENV_PATH>" (
  echo refused: set SANCHOPANZA_KEYS_ENV in this copy
  exit /b 1
)
set "OUT=%USERPROFILE%\.cache\sanchopanza\longdoc-free-%PHASE%"
if "%PHASE%"=="confirm" set "OUT=%USERPROFILE%\.cache\sanchopanza\longdoc-free"
if "%PHASE%"=="probe" set "OUT=%USERPROFILE%\.cache\sanchopanza\longdoc-free-bm25-probe"
if not exist "%OUT%" mkdir "%OUT%"
echo start %PHASE% %DATE% %TIME% >> "%OUT%\launch.log"
git rev-parse HEAD >> "%OUT%\launch.log" 2>&1
"%PY%" -I -u benchmarks\longdoc_free\jev_phase.py paid --phase %PHASE% --launcher "%~f0" >> "%OUT%\launch.log" 2>&1
set RUNEXIT=%ERRORLEVEL%
echo paid-exit %RUNEXIT% %DATE% %TIME% >> "%OUT%\launch.log"
if "%RUNEXIT%"=="0" "%PY%" -I benchmarks\longdoc_free\jev_phase.py rows --phase %PHASE% >> "%OUT%\launch.log" 2>&1
if "%RUNEXIT%"=="0" echo rows-exit %ERRORLEVEL% %DATE% %TIME% >> "%OUT%\launch.log"
exit /b %RUNEXIT%
