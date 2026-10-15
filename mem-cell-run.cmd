@echo off
rem Memory cell N against S, Sonnet 5.5, F1 family (iii) parallel; sealed in
rem docs/results/2026-10-13-memory-cell/prereg.md. Runs from the detached worktree at the sealing
rem commit, never from the main checkout (the hooks are read from disk at every call). Started
rem outside the Claude Code session (WMI). Never run it twice. carry.py reads
rem CLAUDE_CODE_OAUTH_TOKEN and TYPESAFE_API_KEY from this window or from the .env file
rem SANCHOPANZA_KEYS_ENV names;
rem the token reaches only the claude processes, the TypeSafe key only S's hooks. OUT is outside
rem the home folder (carry.py refuses a clean user under a CLAUDE.md). Exit codes of carry.py: 0 ran
rem to the end, 1 refused or crashed (see the log), 2 the cap or the usage limit,
rem 3 a session timed out, 4 S did not run as S.
cd /d C:\Users\roman\Desktop\proyectos\apps\sanchopanza-mem-cell
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set OUT=C:\sp-runs\memory-carry
set RUN=%OUT%\mem-cell-sonnet-parallel
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set PATH=%PIN%;%PATH%
set PYTHONPATH=C:\Users\roman\Desktop\proyectos\apps\sanchopanza-mem-cell\src
set DISABLE_AUTOUPDATER=1
if not exist "%OUT%" mkdir "%OUT%"
set STATUS=%OUT%\mem-cell-run.status
if exist "%RUN%\carry.json" (
  echo refused %DATE% %TIME% mem-cell-sonnet-parallel already has rows >> "%STATUS%"
  exit /b 1
)
echo start %DATE% %TIME% > "%STATUS%"
git rev-parse HEAD >> "%STATUS%" 2>&1
git status --porcelain --untracked-files=no >> "%STATUS%" 2>&1
"%PY%" -c "import sanchopanza; print(sanchopanza.__file__)" >> "%STATUS%" 2>&1
where claude >> "%STATUS%" 2>&1
claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
"%PY%" -u benchmarks\memory_carry\carry.py --out "%RUN%" --models sonnet --scenes parallel --arms N,S --repeats 3 --first-repeat 1 --rotate --clean-user --total-cap 36.5 >> "%OUT%\mem-cell-sonnet-parallel.log" 2>&1
set RUNEXIT=%ERRORLEVEL%
echo run-exit %RUNEXIT% %DATE% %TIME% >> "%STATUS%"
rem A session timeout (exit 3) leaves its pair without a row: the run resumes once, that pair again
rem whole and its spend counted (--continue); a second stop of any kind is final.
if "%RUNEXIT%"=="3" "%PY%" -u benchmarks\memory_carry\carry.py --out "%RUN%" --models sonnet --scenes parallel --arms N,S --repeats 3 --first-repeat 1 --rotate --clean-user --total-cap 36.5 --continue >> "%OUT%\mem-cell-sonnet-parallel.log" 2>&1
if "%RUNEXIT%"=="3" echo continue-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
"%PY%" benchmarks\memory_carry\cell.py "%RUN%" --a S --b N --scenes parallel --repeats 1,2,3 --model sonnet > "%OUT%\mem-cell-table.json" 2> "%OUT%\mem-cell-table.err"
echo table-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
"%PY%" benchmarks\memory_carry\sendbacks.py "%RUN%" > "%OUT%\mem-cell-sendbacks.txt" 2>&1
echo sendbacks-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
