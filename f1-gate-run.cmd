@echo off
rem F1 headroom gate (docs/results/2026-10-05-memory-frontier/prereg-f1-correctness.md, DRAFT: not
rem sealed until its commit adds the sha256). Arm N only, clean user, repetition 0: Sonnet 5.5
rem (cap 16.5 USD), then Opus 5.5 (cap 31 USD) only if Sonnet exits 0 (carry.py exits 2 on a cap
rem stop or the usage limit, 3 on a session timeout), then the gate table. Started outside the
rem Claude Code session. Never run it twice.
rem Needs CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) set in this window only: carry.py
rem passes it to the claude processes and never writes it anywhere. OUT is outside the home
rem folder: under it, Claude Code's upward CLAUDE.md search would reach ~/.claude/CLAUDE.md and
rem ~/.claude/rules, and carry.py refuses a clean user there.
cd /d C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-f1
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set OUT=C:\sp-runs\memory-carry
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set PATH=%PIN%;%PATH%
set PYTHONPATH=C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-f1\src
set DISABLE_AUTOUPDATER=1
if not exist "%OUT%" mkdir "%OUT%"
set STATUS=%OUT%\f1-gate-run.status
if not defined CLAUDE_CODE_OAUTH_TOKEN (
  echo refused %DATE% %TIME% CLAUDE_CODE_OAUTH_TOKEN is not set >> "%STATUS%"
  exit /b 1
)
if exist "%OUT%\f1-gate-sonnet\carry.json" (
  echo refused %DATE% %TIME% f1-gate-sonnet already has rows >> "%STATUS%"
  exit /b 1
)
if exist "%OUT%\f1-gate-opus\carry.json" (
  echo refused %DATE% %TIME% f1-gate-opus already has rows >> "%STATUS%"
  exit /b 1
)
echo start %DATE% %TIME% > "%STATUS%"
where claude >> "%STATUS%" 2>&1
claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\f1-gate-sonnet" --models sonnet --scenes f1 --arms N --repeats 1 --clean-user --total-cap 16.5 >> "%OUT%\f1-gate-sonnet.log" 2>&1
set SONNETEXIT=%ERRORLEVEL%
echo sonnet-exit %SONNETEXIT% %DATE% %TIME% >> "%STATUS%"
if not "%SONNETEXIT%"=="0" echo opus-skipped: f1-gate-sonnet exited %SONNETEXIT%, see f1-gate-sonnet.log >> "%STATUS%"
if "%SONNETEXIT%"=="0" "%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\f1-gate-opus" --models opus --scenes f1 --arms N --repeats 1 --clean-user --total-cap 31 >> "%OUT%\f1-gate-opus.log" 2>&1
if "%SONNETEXIT%"=="0" echo opus-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
"%PY%" benchmarks\memory_carry\analyze.py "%OUT%\f1-gate-sonnet" "%OUT%\f1-gate-opus" --gate --arm N --need 3 > "%OUT%\f1-gate-table.txt" 2>&1
echo table-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
