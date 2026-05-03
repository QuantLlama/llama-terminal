@echo off
:: Setup environment for Windows

echo Setting up environment...

:: Create virtual environment if it doesn't exist
if not exist "venv" (
    python -m venv venv
    echo Virtual environment created.
)

:: Activate virtual environment and install requirements
call venv\Scripts\activate
if exist "requirements.txt" (
    pip install --upgrade pip
    pip install -r requirements.txt
    echo Requirements installed.
) else (
    echo requirements.txt not found.
)

echo Setup complete.
pause
