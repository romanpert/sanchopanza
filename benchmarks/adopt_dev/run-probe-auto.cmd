@echo off
rem The find-auto development probe (benchmarks/adopt_dev/probe_auto.py). Paid: list price
rem under 12.00 USD in all, 1.50 per call, plus the hook's Jev tournaments (cents).
rem Before it: AUTO_COMMIT set in common.py to the frozen commit, and
rem   python -m benchmarks.adopt_dev.probe_auto check     ending in CHECK OK.
rem Start it outside any Claude Code session:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "<main checkout>\benchmarks\adopt_dev\run-probe-auto.cmd"'}
rem Ends with a log line PROBE DONE, PROBE STOP: <why> or PROBE FAILED: <why>, then "exit <n>".
rem ADOPT_SANCHO is not set here: common.py pins it to the frozen copy of AUTO_COMMIT.
set PATH=%USERPROFILE%\.cache\sanchopanza\adopt\claude-2.1.285;%PATH%
set DISABLE_AUTOUPDATER=1
set ADOPT_DEV_PROFILE=auto
set PYTHONIOENCODING=utf-8
set L=%USERPROFILE%\.cache\sanchopanza\adopt\dev-auto
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
"%PY%" -u -m benchmarks.adopt_dev.probe_auto run >> "%L%\probe.log" 2>> "%L%\probe.log.err"
echo exit %errorlevel% >> "%L%\probe.log"
