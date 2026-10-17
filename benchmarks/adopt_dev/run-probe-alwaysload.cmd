@echo off
rem The alwaysLoad development probe (benchmarks/adopt_dev/probe_alwaysload.py). Paid: list
rem price under 8.00 USD in all, 1.50 per call. Start it outside any Claude Code session:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "<main checkout>\benchmarks\adopt_dev\run-probe-alwaysload.cmd"'}
rem Ends with a log line PROBE DONE, PROBE STOP: <why> or PROBE FAILED: <why>, then "exit <n>".
set PATH=%USERPROFILE%\.cache\sanchopanza\adopt\claude-2.1.285;%PATH%
set DISABLE_AUTOUPDATER=1
set ADOPT_SANCHO=%USERPROFILE%\.cache\sanchopanza\adopt\frozen\1ea9302c8b4c-jev-mcp\Scripts\sanchopanza.exe
set PYTHONIOENCODING=utf-8
set PY=%~dp0..\..\.venv\Scripts\python.exe
set L=%USERPROFILE%\.cache\sanchopanza\adopt\dev-alwaysload
if not exist "%L%" mkdir "%L%"
cd /d "%~dp0..\.."
claude --version > "%L%\probe.version" 2>&1
"%PY%" -u -m benchmarks.adopt_dev.probe_alwaysload run >> "%L%\probe.log" 2>> "%L%\probe.log.err"
echo exit %errorlevel% >> "%L%\probe.log"
