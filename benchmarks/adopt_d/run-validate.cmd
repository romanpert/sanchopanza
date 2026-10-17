@echo off
rem Phase D: free validation of the drawn SWE-bench images (benchmarks/adopt_d/validate_d.py).
rem Docker only, no session, no spend. Resumable: run it again after any stop and it skips what
rem singles-validated.json already holds. Refuses once the prereg is sealed. Start it outside any
rem Claude Code session:
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='cmd.exe /c "<main checkout>\benchmarks\adopt_d\run-validate.cmd"'}
rem Watch:  tail -f ~/.cache/sanchopanza/adopt/validate-d/validate.log
rem Ends with a log line VALIDATION DONE, VALIDATION PAUSED or VALIDATION STOP: <why>, and the
rem wrapper appends "exit <n>" to validate.out.
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set L=%USERPROFILE%\.cache\sanchopanza\adopt\validate-d
if not exist "%L%" mkdir "%L%"
rem The run goes to the main checkout, as it always did: the folder above git's common
rem directory (a sibling worktree shares it), the only checkout with a .venv. Without it the
rem launcher refuses (exit 2, a VALIDATION REFUSED line in validate.out).
set "MAIN="
for /f "delims=" %%G in ('git -C "%~dp0." rev-parse --path-format^=absolute --git-common-dir 2^>nul') do set "MAIN=%%~dpG"
if not defined MAIN (
  echo VALIDATION REFUSED: this launcher is not in a git checkout >> "%L%\validate.out"
  exit /b 2
)
set "PY=%MAIN%.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo VALIDATION REFUSED: no python in the main checkout's .venv >> "%L%\validate.out"
  exit /b 2
)
cd /d "%MAIN%"
"%PY%" -u benchmarks\adopt_d\validate_d.py run >> "%L%\validate.out" 2>> "%L%\validate.out.err"
echo exit %errorlevel% >> "%L%\validate.out"
