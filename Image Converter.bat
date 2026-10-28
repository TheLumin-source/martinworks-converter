@echo off
rem Launch the Converter with no console window.
rem
rem Tries a local .venv first, then pythonw on PATH, then the windowed py
rem launcher. pythonw rather than python is deliberate: it has no console, so
rem the app opens without a black box behind it.
setlocal

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0image_converter.py" %*
    exit /b 0
)

where pythonw.exe >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0image_converter.py" %*
    exit /b 0
)

where pyw.exe >nul 2>&1
if %errorlevel%==0 (
    start "" pyw.exe -3 "%~dp0image_converter.py" %*
    exit /b 0
)

echo Could not find pythonw.exe.
echo.
echo Install Python 3.10 or newer from python.org, or create a virtual
echo environment next to this file:
echo.
echo     python -m venv .venv
echo     .venv\Scripts\pip install -r requirements.txt
echo.
pause
exit /b 1
