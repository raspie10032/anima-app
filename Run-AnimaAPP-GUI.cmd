@echo off
setlocal
set "APP_ROOT=%~dp0"
cd /d "%APP_ROOT%" || exit /b 1
set "PYTHONPATH=%APP_ROOT%\src"
if not defined ANIMA_APP_CUDA_VISIBLE_DEVICES set "ANIMA_APP_CUDA_VISIBLE_DEVICES=0"
set "CUDA_VISIBLE_DEVICES=%ANIMA_APP_CUDA_VISIBLE_DEVICES%"
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open
set "APP_EXIT_CODE=%ERRORLEVEL%"
if "%APP_EXIT_CODE%"=="0" exit /b 0

echo.
echo Anima APP failed to start. Exit code: %APP_EXIT_CODE%
echo Check that Python and the project dependencies are installed, then run this launcher again.
echo See README.md for setup and model preparation instructions.
pause >nul
exit /b %APP_EXIT_CODE%
