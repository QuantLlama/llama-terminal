#!/bin/bash
# Setup environment for Linux/macOS

echo "Setting up environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv_linux" ]; then
    python3 -m venv venv_linux
    echo "Virtual environment created."
fi

# Activate virtual environment
source venv_linux/bin/activate

# Install requirements
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "Requirements installed."
else
    echo "requirements.txt not found."
fi

echo "Setup complete."
