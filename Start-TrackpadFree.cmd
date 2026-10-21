@echo off
rem Starts Trackpad Free without a console window when pythonw is available.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw app.py) || python app.py
