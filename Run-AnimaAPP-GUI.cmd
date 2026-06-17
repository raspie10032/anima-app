@echo off
setlocal

set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"

set "PYTHONPATH=%APP_ROOT%\src"

cd /d "%APP_ROOT%"
echo Starting Anima APP GUI in real generation mode.
if defined CUDA_VISIBLE_DEVICES echo CUDA_VISIBLE_DEVICES=%CUDA_VISIBLE_DEVICES%
echo A browser window will open after the server chooses a free local port.
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open

echo.
echo Anima APP stopped.
pause
