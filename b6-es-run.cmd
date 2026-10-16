@echo off
rem B6: triage_pages and select_passages in Spanish against English (Jev only, no Claude;
rem docs/results/2026-10-16-b6-es/prereg.md). Caps in code (benchmarks/b6_es/b6_run.py): pages
rem 0.30 USD, docs 5.00 USD, each smoke 0.10 USD, ledger 5.50, in %SANCHOPANZA_B6_RUN%.
rem   b6-es-run.cmd pages          the pages bench (first, to completion)
rem   b6-es-run.cmd docs           the docs bench (refused until pages is complete or terminal)
rem   b6-es-run.cmd smoke          two dev questions of each bench, on the smoke caps
rem   b6-es-run.cmd pages dry      free: the dry count of that bench, no key, no call
rem Start it by WMI from a worktree --detach at the sealed commit, outside any Claude Code session,
rem in its own process group, never between 02:00 and 08:00, and never twice at once:
rem   $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}
rem   Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
rem     CommandLine = "cmd.exe /c <this file> pages"; ProcessStartupInformation = $s }
rem A relaunch replays what was paid and asks the rest (b6_run.launch_gate holds the rule).
rem Stop: Get-CimInstance Win32_Process -Filter "Name='python.exe'" with b6_run.py in its
rem command line, then Stop-Process -Id <pid>. Never by name.
rem Four local values stay placeholders in the repository (it is public) and are filled only in
rem an untracked copy, e.g. C:\sp-runs\b6-es\b6-es-run.cmd: the python, the keys file, the
rem sealed worktree (left as <WORKTREE>, the folder of this file) and the bench's data folder.
rem The seal hashes this file with those four lines read as placeholders, so filling them keeps
rem the seal and any other change breaks it; b6_run.py checks the copy it was started from.
setlocal
set "PY=<PYTHON>"
set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"
set "WT=<WORKTREE>"
set "SANCHOPANZA_B6_DATA=<DATA_DIR>"
if "%WT%"=="<WORKTREE>" set "WT=%~dp0"
if "%WT:~-1%"=="\" set "WT=%WT:~0,-1%"
if "%SANCHOPANZA_B6_RUN%"=="" set SANCHOPANZA_B6_RUN=C:\sp-runs\b6-es
set BENCH=%~1
set MODE=%~2
if /i not "%BENCH%"=="pages" if /i not "%BENCH%"=="docs" if /i not "%BENCH%"=="smoke" (
  echo refused: the arguments are pages^|docs^|smoke [dry]
  exit /b 2
)
if not "%MODE%"=="" if /i not "%MODE%"=="dry" (
  echo refused: the second argument can only be dry
  exit /b 2
)
if "%PY%"=="<PYTHON>" (
  echo refused: name the python in a filled copy of b6-es-run.cmd
  exit /b 3
)
if "%SANCHOPANZA_B6_DATA%"=="<DATA_DIR>" (
  echo refused: name the data folder in a filled copy of b6-es-run.cmd
  exit /b 3
)
cd /d "%WT%"
if not exist "%SANCHOPANZA_B6_RUN%" mkdir "%SANCHOPANZA_B6_RUN%"
set STATUS=%SANCHOPANZA_B6_RUN%\launch.status
set LOG=%SANCHOPANZA_B6_RUN%\launch.log
if /i "%MODE%"=="dry" if /i "%BENCH%"=="smoke" (
  echo refused: dry takes pages or docs
  exit /b 2
)
if /i "%MODE%"=="dry" goto dry
if "%SANCHOPANZA_KEYS_ENV%"=="<KEYS_ENV_PATH>" (
  echo refused %DATE% %TIME%: the keys file is still the placeholder >> "%STATUS%"
  echo refused: name the keys file in a filled copy of b6-es-run.cmd
  exit /b 3
)
echo start %DATE% %TIME% %BENCH% >> "%STATUS%"
if /i "%BENCH%"=="smoke" (
  "%PY%" -I -u benchmarks\b6_es\b6_run.py --bench pages --smoke --live --data "%SANCHOPANZA_B6_DATA%" --launcher "%~f0" >> "%LOG%" 2>&1
  if errorlevel 1 goto done
  "%PY%" -I -u benchmarks\b6_es\b6_run.py --bench docs --smoke --live --data "%SANCHOPANZA_B6_DATA%" --launcher "%~f0" >> "%LOG%" 2>&1
  goto done
)
"%PY%" -I -u benchmarks\b6_es\b6_run.py --bench %BENCH% --live --data "%SANCHOPANZA_B6_DATA%" --launcher "%~f0" >> "%LOG%" 2>&1
:done
set CODE=%ERRORLEVEL%
echo exit %CODE% %DATE% %TIME% >> "%STATUS%"
exit /b %CODE%
:dry
"%PY%" -I -u benchmarks\b6_es\b6_run.py --bench %BENCH% --dry --data "%SANCHOPANZA_B6_DATA%"
exit /b %ERRORLEVEL%
