@echo off
rem Memory v8.1 on Haiku 4.5, amendment 1 (prereg-v81-haiku-amendment-1.md): resumes v81h-all with
rem --continue after the runner's crash of 2026-10-05 12:30, then v81h-cross only if v81h-all ends
rem with exit 0 and no stop: line. Started outside the Claude Code session. Never run it twice.
cd /d C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set OUT=%USERPROFILE%\.cache\sanchopanza\memory-carry
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set PATH=%PIN%;%PATH%
set PYTHONPATH=C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8\src
set DISABLE_AUTOUPDATER=1
set STATUS=%OUT%\v81h-run.status
if not exist "%OUT%\v81h-all\carry.json" (
  echo refused %DATE% %TIME% v81h-all has no rows to continue >> "%STATUS%"
  exit /b 1
)
if exist "%OUT%\v81h-cross\carry.json" (
  echo refused %DATE% %TIME% v81h-cross already has rows >> "%STATUS%"
  exit /b 1
)
echo resume %DATE% %TIME% >> "%STATUS%"
claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
echo resume %DATE% %TIME% >> "%OUT%\v81h-all.log"
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\v81h-all" --models haiku --scenes all --arms M,V --repeats 3 --total-cap 24 --continue >> "%OUT%\v81h-all.log" 2>&1
set ALLEXIT=%ERRORLEVEL%
echo all-exit %ALLEXIT% %DATE% %TIME% >> "%STATUS%"
if not "%ALLEXIT%"=="0" (
  echo cross-skipped: v81h-all exited %ALLEXIT% >> "%STATUS%"
  exit /b 2
)
findstr /l /b /c:"stop:" "%OUT%\v81h-all.log" > nul && (
  echo cross-skipped: v81h-all stopped before its plan ended, see v81h-all.log >> "%STATUS%"
  exit /b 2
)
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\v81h-cross" --models haiku --scenes cross --arms M,V --repeats 3 --total-cap 13 --continue >> "%OUT%\v81h-cross.log" 2>&1
echo cross-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
