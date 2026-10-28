@echo off
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 goto python_setup
uv sync --frozen
if errorlevel 1 goto failed
uv run python launch.py
goto finished
:python_setup
if exist .venv\Scripts\python.exe goto install
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:use_python
python -m venv .venv
if errorlevel 1 goto failed
:install
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe launch.py
goto finished
:failed
echo.
echo Setup failed. Install Python 3.11 or newer, check the network, and try again.
:finished
pause
