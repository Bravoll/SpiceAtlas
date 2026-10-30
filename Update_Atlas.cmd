@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto use_py
where python >nul 2>nul
if not errorlevel 1 goto use_python
if exist "%~1\.venv\Scripts\python.exe" (
  "%~1\.venv\Scripts\python.exe" "%~dp0update.py" --target "%~1" --restart
  goto done
)
echo Python 3.11 or newer is required to run the updater.
goto done
:use_py
if "%~1"=="" (py -3 "%~dp0update.py" --restart) else (py -3 "%~dp0update.py" --target "%~1" --restart)
goto done
:use_python
if "%~1"=="" (python "%~dp0update.py" --restart) else (python "%~dp0update.py" --target "%~1" --restart)
:done
pause
