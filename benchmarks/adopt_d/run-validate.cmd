@echo off
rem Phase D: free validation of the drawn SWE-bench images (benchmarks/adopt_d/validate_d.py).
rem Docker only, no session, no spend. Resumable: run it again after any stop and it skips what
rem singles-validated.json already holds. Refuses once the prereg is sealed. Start it outside any
rem Claude Code session:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "C:\Users\roman\Desktop\proyectos\apps\sanchopanza\benchmarks\adopt_d\run-validate.cmd"'}
rem Watch:  tail -f ~/.cache/sanchopanza/adopt/validate-d/validate.log
rem Ends with a log line VALIDATION DONE, VALIDATION PAUSED or VALIDATION STOP: <why>, and the
rem wrapper appends "exit <n>" to validate.out.
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set L=C:\Users\roman\.cache\sanchopanza\adopt\validate-d
if not exist "%L%" mkdir "%L%"
cd /d C:\Users\roman\Desktop\proyectos\apps\sanchopanza
"%PY%" -u benchmarks\adopt_d\validate_d.py run >> "%L%\validate.out" 2>> "%L%\validate.out.err"
echo exit %errorlevel% >> "%L%\validate.out"
