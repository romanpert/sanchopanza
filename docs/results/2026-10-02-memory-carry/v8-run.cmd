@echo off
rem Memory v8, sealed in f1ffa20 (prereg-v8.md). Launched outside the Claude Code session.
cd /d %USERPROFILE%\Desktop\proyectos\apps\sanchopanza-memoria-v8
set PY=%USERPROFILE%\Desktop\proyectos\apps\sanchopanza\.venv\Scripts\python.exe
set OUT=%USERPROFILE%\.cache\sanchopanza\memory-carry
echo start %DATE% %TIME% > "%OUT%\v8-run.status"
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\v8-cross" --scenes cross --arms M,V --repeats 3 --total-cap 20 >> "%OUT%\v8-cross.log" 2>&1
echo cross-exit %ERRORLEVEL% %DATE% %TIME% >> "%OUT%\v8-run.status"
"%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\v8-all" --scenes all --arms V --repeats 1 --total-cap 8 >> "%OUT%\v8-all.log" 2>&1
echo all-exit %ERRORLEVEL% %DATE% %TIME% >> "%OUT%\v8-run.status"
