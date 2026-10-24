"""Product identity shared by API and desktop distribution metadata."""
import json
import sys
from pathlib import Path


def load_product_version():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    version = package.get('version')
    if not isinstance(version, str) or not version.strip():
        raise ValueError('Product metadata is missing a nonempty version')
    return version


PRODUCT_VERSION = load_product_version()
