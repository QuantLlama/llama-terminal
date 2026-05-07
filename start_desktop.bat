@echo off

REM Verificar si existe el entorno virtual y activarlo
if exist "venv\Scripts\activate.bat" (
    echo Activando entorno virtual...
    call venv\Scripts\activate.bat
) else (
    echo [ADVERTENCIA] No se encontro el entorno virtual en 'venv\'. 
    echo Asegurese de ejecutar setup.bat primero.
)

echo Iniciando Quantum Llama Desktop...
npm start

