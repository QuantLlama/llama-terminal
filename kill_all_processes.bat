@echo off
echo ============================================================
echo MATANDO TODOS LOS PROCESOS
echo ============================================================
echo.

echo Matando procesos Python...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM pythonw.exe 2>nul

echo Matando procesos MT5...
taskkill /F /IM terminal64.exe 2>nul

echo.
echo ============================================================
echo PROCESOS TERMINADOS
echo ============================================================
echo.
echo Ahora:
echo 1. Abre MT5 desde el menu de inicio
echo 2. Inicia sesion con tu cuenta
echo 3. Ejecuta: python test_mt5_quick.py
echo.
pause
