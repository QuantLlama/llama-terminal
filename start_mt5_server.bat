@echo off
echo Iniciando MT5 Wine Server en FastAPI (Puerto 8081)
IF EXIST venv\Scripts\python.exe (
    venv\Scripts\python.exe -m uvicorn mt5_server:app --host 127.0.0.1 --port 8081
) ELSE (
    python -m uvicorn mt5_server:app --host 127.0.0.1 --port 8081
)
pause
