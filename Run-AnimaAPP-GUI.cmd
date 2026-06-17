@echo off
setlocal

set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"

set "PYTHONPATH=%APP_ROOT%\src"
set "CUDA_VISIBLE_DEVICES=0"

cd /d "%APP_ROOT%"
echo Starting Anima APP GUI in real generation mode on CUDA device 0.
echo A browser window will open after the server chooses a free local port.
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open

echo.
echo Anima APP stopped.
pause
