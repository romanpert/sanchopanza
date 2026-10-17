@echo off
rem The find need development probe (benchmarks/adopt_dev/probe_need.py). Paid: list price
rem under 12.00 USD in all, 1.50 per call. Start it outside any Claude Code session:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "<main checkout>\benchmarks\adopt_dev\run-probe-need.cmd"'}
rem Ends with a log line PROBE DONE, PROBE STOP: <why> or PROBE FAILED: <why>, then "exit <n>".
set PATH=%USERPROFILE%\.cache\sanchopanza\adopt\claude-2.1.285;%PATH%
set DISABLE_AUTOUPDATER=1
set ADOPT_DEV_PROFILE=need
set ADOPT_SANCHO=%USERPROFILE%\.cache\sanchopanza\adopt\frozen\7a39a1f0d4ff-jev-mcp\Scripts\sanchopanza.exe
set PYTHONIOENCODING=utf-8
set L=%USERPROFILE%\.cache\sanchopanza\adopt\dev-need
if not exist "%L%" mkdir "%L%"
rem The run goes to the main checkout, as it always did: the folder above git's common
rem directory (a sibling worktree shares it), the only checkout with a .venv. Without it the
rem launcher refuses (exit 2, a PROBE REFUSED line in probe.log).
set "MAIN="
for /f "delims=" %%G in ('git -C "%~dp0." rev-parse --path-format^=absolute --git-common-dir 2^>nul') do set "MAIN=%%~dpG"
if not defined MAIN (
  echo PROBE REFUSED: this launcher is not in a git checkout >> "%L%\probe.log"
  exit /b 2
)
set "PY=%MAIN%.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo PROBE REFUSED: no python in the main checkout's .venv >> "%L%\probe.log"
  exit /b 2
)
cd /d "%MAIN%"
claude --version > "%L%\probe.version" 2>&1
"%PY%" -u -m benchmarks.adopt_dev.probe_need run >> "%L%\probe.log" 2>> "%L%\probe.log.err"
echo exit %errorlevel% >> "%L%\probe.log"
