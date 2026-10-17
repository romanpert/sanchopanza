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
set PY=%~dp0..\..\.venv\Scripts\python.exe
set L=%USERPROFILE%\.cache\sanchopanza\adopt\dev-need
if not exist "%L%" mkdir "%L%"
cd /d "%~dp0..\.."
claude --version > "%L%\probe.version" 2>&1
"%PY%" -u -m benchmarks.adopt_dev.probe_need run >> "%L%\probe.log" 2>> "%L%\probe.log.err"
echo exit %errorlevel% >> "%L%\probe.log"
