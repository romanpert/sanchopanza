@echo off
rem Phase D of the adoption study (benchmarks/adopt_d/run_d.py). Paid: list price under the
rem ceiling sealed in run_d.py (CEILING_BASE_USD + CEILING_ADDED_USD), 1.50 per call, 9.00 held
rem per instance.
rem Only once the prereg is sealed. Start it outside any Claude Code session (other batches on
rem the subscription may run alongside):
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "<main checkout>\benchmarks\adopt_d\run-d.cmd"'}
rem Ends with a log line D DONE, D STOP: <why>, D REFUSED: <why> or D FAILED: <why>, then
rem "exit <n>". Started again, it resumes: what ran is graded, what did not is run.
rem ADOPT_SANCHO is cleared: run_d.py sets it to the frozen copy of D_COMMIT itself.
set PATH=%USERPROFILE%\.cache\sanchopanza\adopt\claude-2.1.285;%PATH%
set DISABLE_AUTOUPDATER=1
set ADOPT_SANCHO=
set PYTHONIOENCODING=utf-8
set L=%USERPROFILE%\.cache\sanchopanza\adopt
rem The run goes to the main checkout, as it always did: the folder above git's common
rem directory (a sibling worktree shares it), the only checkout with a .venv. Without it the
rem launcher refuses (exit 2, a D REFUSED line in D.log).
set "MAIN="
for /f "delims=" %%G in ('git -C "%~dp0." rev-parse --path-format^=absolute --git-common-dir 2^>nul') do set "MAIN=%%~dpG"
if not defined MAIN (
  echo D REFUSED: this launcher is not in a git checkout >> "%L%\D.log"
  exit /b 2
)
set "PY=%MAIN%.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo D REFUSED: no python in the main checkout's .venv >> "%L%\D.log"
  exit /b 2
)
cd /d "%MAIN%"
claude --version > "%L%\D.version" 2>&1
"%PY%" -u benchmarks\adopt_d\run_d.py run >> "%L%\D.log" 2>> "%L%\D.log.err"
echo exit %errorlevel% >> "%L%\D.log"
