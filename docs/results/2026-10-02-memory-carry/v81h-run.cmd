@echo off
rem Memory v8.1 on Haiku 4.5, sealed by the commit that adds prereg-v81-haiku.sha256 (branch memoria-v8).
rem Started outside the Claude Code session (prereg-v81-haiku.md, "Commands"). Never run it twice.
cd /d C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8
set PY=C:\Users\roman\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set OUT=%USERPROFILE%\.cache\sanchopanza\memory-carry
set PIN=%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
set PATH=%PIN%;%PATH%
set PYTHONPATH=C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8\src
set DISABLE_AUTOUPDATER=1
set STATUS=%OUT%\v81h-run.status
if exist "%OUT%\v81h-all\carry.json" (
  echo refused %DATE% %TIME% v81h-all already has rows >> "%STATUS%"
  exit /b 1
)
if exist "%OUT%\v81h-cross\carry.json" (
  echo refused %DATE% %TIME% v81h-cross already has rows >> "%STATUS%"
  exit /b 1
)
echo start %DATE% %TIME% > "%STATUS%"
where claude >> "%STATUS%" 2>&1
claude --version >> "%STATUS%" 2>&1
claude --version | findstr /l /b /c:"2.1.287 " > nul || (
  echo refused: claude first on PATH is not 2.1.287 >> "%STATUS%"
  exit /b 3
)
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\v81h-all" --models haiku --scenes all --arms M,V --repeats 3 --total-cap 24 >> "%OUT%\v81h-all.log" 2>&1
echo all-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
findstr /l /b /c:"stop:" "%OUT%\v81h-all.log" > nul && (
  echo cross-skipped: v81h-all stopped before its plan ended, see v81h-all.log >> "%STATUS%"
  exit /b 2
)
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\v81h-cross" --models haiku --scenes cross --arms M,V --repeats 3 --total-cap 13 >> "%OUT%\v81h-cross.log" 2>&1
echo cross-exit %ERRORLEVEL% %DATE% %TIME% >> "%STATUS%"
