@echo off
echo Starting Quantum Llama Platform API...
echo.

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Start the API server
echo Starting API server on http://127.0.0.1:8050
echo Press Ctrl+C to stop the server
echo.
python start_api.py

pause
