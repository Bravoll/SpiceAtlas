@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe (
  start "" ".venv\Scripts\pythonw.exe" "%~dp0Start_Atlas.pyw"
  exit /b
)
where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0Start_Atlas.pyw"
  exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0Start_Atlas.pyw"
  exit /b
)
echo Python 3.11 or newer with Tcl/Tk is required.
echo Install Python, then double-click run.cmd again.
echo For a visible diagnostic console, use run_console.cmd.
pause
