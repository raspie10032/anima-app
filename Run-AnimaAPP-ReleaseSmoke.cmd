@echo off
setlocal

set "APP_ROOT=%~dp0"
if "%APP_ROOT:~-1%"=="\" set "APP_ROOT=%APP_ROOT:~0,-1%"

set "PYTHONPATH=%APP_ROOT%\src"
set "CUDA_VISIBLE_DEVICES=0"

cd /d "%APP_ROOT%"
echo Running Anima APP source-checkout release smoke.
echo This uses CPU-safe dry-run checks and pins CUDA visibility to GPU 0.
python scripts\release_smoke.py --include-tests
set "SMOKE_EXIT=%ERRORLEVEL%"

echo.
if "%SMOKE_EXIT%"=="0" (
  echo Release smoke passed.
) else (
  echo Release smoke failed with exit code %SMOKE_EXIT%.
)
pause
exit /b %SMOKE_EXIT%
