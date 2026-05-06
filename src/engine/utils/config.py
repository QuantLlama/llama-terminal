import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Carga configuración desde archivo YAML."""
    if config_path is None:
        config_path = str(BASE_DIR / 'config' / 'config.yaml')
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_env(key: str, default=None):
    """Obtiene variable de entorno."""
    import os
    return os.getenv(key, default)


CONFIG = load_config()
