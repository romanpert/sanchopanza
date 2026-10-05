@echo off
rem Phase D of the adoption study (benchmarks/adopt_d/run_d.py). Paid: list price under the
rem ceiling sealed in run_d.py (CEILING_BASE_USD + CEILING_ADDED_USD), 1.50 per call, 9.00 held
rem per instance.
rem Only once the prereg is sealed. Start it outside any Claude Code session, and not alongside
rem another run on the subscription:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "C:\Users\roman\Desktop\proyectos\apps\sanchopanza\benchmarks\adopt_d\run-d.cmd"'}
rem Ends with a log line D DONE, D STOP: <why>, D REFUSED: <why> or D FAILED: <why>, then
rem "exit <n>". Started again, it resumes: what ran is graded, what did not is run.
rem ADOPT_SANCHO is cleared: run_d.py sets it to the frozen copy of D_COMMIT itself.
set PATH=C:\Users\roman\.cache\sanchopanza\adopt\claude-2.1.285;%PATH%
set DISABLE_AUTOUPDATER=1
set ADOPT_SANCHO=
set PYTHONIOENCODING=utf-8
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set L=C:\Users\roman\.cache\sanchopanza\adopt
cd /d C:\Users\roman\Desktop\proyectos\apps\sanchopanza
claude --version > "%L%\D.version" 2>&1
"%PY%" -u benchmarks\adopt_d\run_d.py run >> "%L%\D.log" 2>> "%L%\D.log.err"
echo exit %errorlevel% >> "%L%\D.log"
