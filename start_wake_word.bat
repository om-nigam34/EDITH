@echo off
REM Double-click launcher for the wake-word listener (voice/wake_word.py).
REM Same idea as the reference repo's START_*.bat files: wrap the venv
REM activation + python command so it can be double-clicked instead of
REM typed into a terminal every time. Keep this window open — closing it
REM stops the listener.

cd /d "%~dp0"

if not exist venv\Scripts\activate.bat (
    echo [EDITH] Virtual environment not found. Run the main setup first ^(see README.md^).
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
python voice\wake_word.py

pause