@echo off
REM MT5 bridge: keeps the MetaTrader 5 terminal on this machine and exposes it
REM over HTTP so the cloud app can read market data and place orders.
REM
REM Local default: 127.0.0.1:8081 without token.
REM To expose it over a private tunnel (Tailscale/WireGuard), set:
REM   set MT5_BRIDGE_BIND=0.0.0.0
REM   set MT5_BRIDGE_TOKEN=<long random value>
REM and keep the port closed in your firewall except on the tunnel interface.

echo Iniciando MT5 Wine Server (FastAPI)
echo Bind: %MT5_BRIDGE_BIND%  Port: %MT5_BRIDGE_PORT%  Token configurado: %MT5_BRIDGE_TOKEN%

IF EXIST venv\Scripts\python.exe (
    venv\Scripts\python.exe -m uvicorn mt5_server:app --host %MT5_BRIDGE_BIND% --port %MT5_BRIDGE_PORT%
) ELSE (
    python -m uvicorn mt5_server:app --host %MT5_BRIDGE_BIND% --port %MT5_BRIDGE_PORT%
)
pause
