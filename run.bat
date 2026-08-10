@echo off
where py >nul 2>nul
if %ERRORLEVEL% == 0 (
    py setup_and_run.py
) else (
    python setup_and_run.py
)
pause
