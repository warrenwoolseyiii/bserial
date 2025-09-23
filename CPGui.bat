@echo off
setlocal
set PYTHONPATH=%~dp0src;%PYTHONPATH%
echo "Installing dependencies..."
python.exe -m pip install -r requirements.txt
echo "Launching bserial..."
python.exe -m bserial.bserial
endlocal