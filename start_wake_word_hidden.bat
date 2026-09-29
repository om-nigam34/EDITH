@echo off
REM Silent version of start_wake_word.bat — launches voice/wake_word.py with
REM pythonw.exe (the console-less Python interpreter that ships alongside
REM python.exe in every standard Windows install) instead of python.exe, so
REM no terminal window stays open. Use this once you've confirmed the
REM visible start_wake_word.bat works correctly — this version won't show
REM you any of its print() output if something goes wrong.
REM
REM To stop it later: open Task Manager -> Details tab -> end the
REM "pythonw.exe" process (if EDITH's main server also got auto-launched by
REM the wake word and it was also started via pythonw, you may see two
REM pythonw.exe entries — check the "Command line" column, or just end both
REM if you want to fully stop EDITH).

cd /d "%~dp0"

if not exist venv\Scripts\pythonw.exe (
    echo [EDITH] venv\Scripts\pythonw.exe not found.
    echo Either the virtual environment hasn't been created yet ^(see README.md^),
    echo or your Python install is missing pythonw.exe - the official
    echo python.org installer includes it by default.
    pause
    exit /b 1
)

start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0voice\wake_word.py"