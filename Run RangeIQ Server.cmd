@echo off
setlocal

title RangeIQ Server
cd /d "%~dp0"
set "PYTHONPATH=%cd%\src"
set "PYTHON_LAUNCHER=%SystemRoot%\py.exe"

"%PYTHON_LAUNCHER%" -3.10 -m ranch_ai
if errorlevel 1 (
    echo.
    echo RangeIQ setup failed before the dashboard could launch.
    echo Keep this window open and share the error if you want me to fix it.
    pause
    exit /b %errorlevel%
)

"%PYTHON_LAUNCHER%" -3.10 -m streamlit run app\dashboard.py --server.headless true --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo The dashboard server stopped unexpectedly.
    pause
    exit /b %errorlevel%
)
