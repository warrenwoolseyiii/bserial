@echo off
setlocal
set PYTHONPATH=%~dp0src;%PYTHONPATH%
python.exe -m bserial.bserial
endlocal