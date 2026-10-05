@echo off
rem Memory v8 on Haiku 4.5 (prereg-v8-haiku.md, 906aa0a): SUPERSEDED before any data by
rem prereg-v81-haiku.md, whose launcher is v81h-run.cmd. This one refuses to start, so the v8 seal
rem never runs against v8.1 code.
echo refused %DATE% %TIME% superseded by prereg-v81-haiku.md, use v81h-run.cmd >> "%USERPROFILE%\.cache\sanchopanza\memory-carry\v8h-run.status"
exit /b 4
