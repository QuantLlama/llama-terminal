#!/bin/bash
# Setup environment for Linux/macOS

echo "Setting up environment..."

VENV_PATH="./venv_linux"

# Limpiar venv_linux local si está corrupto
rm -rf venv_linux

# Intentar crear venv localmente
python3 -m venv venv_linux 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Fallo al crear venv local (probablemente debido a sistema de archivos NTFS/exFAT)."
    echo "Creando el entorno virtual en la partición nativa de Linux del usuario..."
    VENV_PATH="/home/pabloezm/.gemini/antigravity-cli/venv_linux"
    mkdir -p "/home/pabloezm/.gemini/antigravity-cli"
    rm -rf "$VENV_PATH"
    python3 -m venv "$VENV_PATH"
    if [ $? -eq 0 ]; then
        echo "Virtual environment creado con éxito en: $VENV_PATH"
        # Guardar la ruta del venv para los scripts de node/python
        echo "$VENV_PATH" > .venv_linux_path
    else
        echo "Error crítico: No se pudo crear el entorno virtual."
        exit 1
    fi
else
    echo "Virtual environment creado localmente con éxito."
    echo "./venv_linux" > .venv_linux_path
fi

# Activar virtual environment
source "${VENV_PATH}/bin/activate"

# Instalar requirements
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "Requirements installed."
else
    echo "requirements.txt not found."
fi

echo "Setup complete."
