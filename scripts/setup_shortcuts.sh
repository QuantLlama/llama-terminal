#!/bin/bash
# Script de automatización de accesos directos para Quantum Llama Terminal en Linux

# Colores para salida visualmente atractiva (Skin Senior)
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

echo -e "${BLUE}=== Configurando Accesos Directos de Quantum Llama Terminal ===${NC}"

# 1. Determinar rutas por defecto
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESOURCES_DIR="${APP_DIR}/resources"
ICON_PATH="${APP_DIR}/images/QuantumLLama.png"

# Permitir sobrescribir rutas mediante parámetros
MAIN_EXEC="${1:-${APP_DIR}/quantum-llama-terminal}"
TRAINER_EXEC="${2:-${RESOURCES_DIR}/Trainer}"
BROWSER_EXEC="${3:-${RESOURCES_DIR}/BrowserMode}"
CUSTOM_ICON="${4:-${ICON_PATH}}"

# Si no está empaquetada en resources, verificar si estamos en desarrollo
if [ ! -f "$TRAINER_EXEC" ]; then
    # En desarrollo, el Trainer es run.py ejecutado por venv_linux
    TRAINER_EXEC="${APP_DIR}/venv_linux/bin/python ${APP_DIR}/run.py"
fi
if [ ! -f "$BROWSER_EXEC" ]; then
    BROWSER_EXEC="${APP_DIR}/venv_linux/bin/python ${APP_DIR}/browser_launcher.py"
fi
if [ ! -f "$CUSTOM_ICON" ]; then
    CUSTOM_ICON="${APP_DIR}/images/QuantumLLama.png"
fi

# Detectar directorios de Escritorio del usuario (inglés / español)
DESKTOP_DIR=""
if [ -d "$HOME/Desktop" ]; then
    DESKTOP_DIR="$HOME/Desktop"
elif [ -d "$HOME/Escritorio" ]; then
    DESKTOP_DIR="$HOME/Escritorio"
else
    DESKTOP_DIR="$HOME/Desktop"
    mkdir -p "$DESKTOP_DIR"
fi

APPLICATIONS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPLICATIONS_DIR"

echo -e "Directorio de Escritorio detectado: ${GREEN}${DESKTOP_DIR}${NC}"
echo -e "Directorio de Aplicaciones: ${GREEN}${APPLICATIONS_DIR}${NC}"

# --- 1. Crear Acceso Directo Principal (Terminal Llama) ---
DESKTOP_MAIN="[Desktop Entry]
Name=Quantum Llama Terminal
Comment=Quantum Llama Advanced AI-Powered Trading Platform
Exec=${MAIN_EXEC}
Icon=${CUSTOM_ICON}
Terminal=false
Type=Application
Categories=Utility;Finance;
Keywords=trading;finance;llama;"

# --- 2. Crear Acceso Directo de Llama Trainer (CLI en consola) ---
DESKTOP_TRAINER="[Desktop Entry]
Name=Llama Trainer
Comment=Quantum Llama Machine Learning & Training CLI
Exec=${TRAINER_EXEC}
Icon=${APP_DIR}/images/QuantumLLama_Trainer.png
Terminal=true
Type=Application
Categories=Utility;Finance;
Keywords=trading;machinelearning;llama;"

# --- 3. Crear Acceso Directo de Quantum Llama Browser (Modo Navegador) ---
DESKTOP_BROWSER="[Desktop Entry]
Name=Quantum Llama Browser
Comment=Quantum Llama Browser Launch Mode
Exec=${BROWSER_EXEC}
Icon=${APP_DIR}/images/QuantumLLama_Browser.png
Terminal=false
Type=Application
Categories=Utility;Finance;
Keywords=trading;browser;llama;"

# Guardar archivos de escritorio en aplicaciones del menú
echo -e "${BLUE}Instalando accesos directos en el menú de aplicaciones...${NC}"
echo "$DESKTOP_MAIN" > "${APPLICATIONS_DIR}/quantum-llama-terminal.desktop"
echo "$DESKTOP_TRAINER" > "${APPLICATIONS_DIR}/llama-trainer.desktop"
echo "$DESKTOP_BROWSER" > "${APPLICATIONS_DIR}/quantum-llama-browser.desktop"

# Guardar archivos en el Escritorio
echo -e "${BLUE}Instalando accesos directos en el Escritorio del usuario...${NC}"
echo "$DESKTOP_MAIN" > "${DESKTOP_DIR}/quantum-llama-terminal.desktop"
echo "$DESKTOP_TRAINER" > "${DESKTOP_DIR}/llama-trainer.desktop"
echo "$DESKTOP_BROWSER" > "${DESKTOP_DIR}/quantum-llama-browser.desktop"

# Dar permisos de ejecución a los archivos de escritorio
chmod +x "${APPLICATIONS_DIR}/quantum-llama-terminal.desktop"
chmod +x "${APPLICATIONS_DIR}/llama-trainer.desktop"
chmod +x "${APPLICATIONS_DIR}/quantum-llama-browser.desktop"

chmod +x "${DESKTOP_DIR}/quantum-llama-terminal.desktop"
chmod +x "${DESKTOP_DIR}/llama-trainer.desktop"
chmod +x "${DESKTOP_DIR}/quantum-llama-browser.desktop"

# En entornos GNOME modernos, a veces hay que marcar los archivos del Escritorio como confiables
if command -v gio &> /dev/null; then
    gio set "${DESKTOP_DIR}/quantum-llama-terminal.desktop" metadata::trusted true 2>/dev/null
    gio set "${DESKTOP_DIR}/llama-trainer.desktop" metadata::trusted true 2>/dev/null
    gio set "${DESKTOP_DIR}/quantum-llama-browser.desktop" metadata::trusted true 2>/dev/null
fi

echo -e "${GREEN}¡Felicidades! Los tres accesos directos se crearon con éxito tanto en tu menú de aplicaciones como en tu Escritorio.${NC}"
