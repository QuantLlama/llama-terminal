@echo off
echo Starting Quantum Llama Platform API...
echo.

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Start the API server
echo Starting API server (default port 8050, will auto-detect free port if in use)
echo Press Ctrl+C to stop the server
echo.
python start_api.py

pause
