import os
import sys

def get_appdata_dir():
    app_name = "QuantumLlama"
    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base_dir = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(base_dir, app_name)

def get_root_dir():
    """
    Returns the persistent directory for the application.
    In production (frozen), it is the directory where the .exe is.
    In development, it is the project root.
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # Return the directory 3 levels up from this file (src/utils/paths.py -> src -> project_root)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))

def get_core_dir():
    """
    Returns the directory for internal code and bundled assets.
    In production, it's sys._MEIPASS. In development, it's the root dir.
    """
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', get_root_dir())
    return get_root_dir()

def get_data_path(*path_parts):
    """
    Resolves a path to a location where we can READ AND WRITE data.
    This is always relative to ROOT_DIR.
    """
    if getattr(sys, 'frozen', False):
        base = get_appdata_dir()
    else:
        base = get_root_dir()
    full_path = os.path.join(base, *path_parts)
    # Ensure parents exist
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    return full_path

def get_internal_path(*path_parts):
    """
    Resolves a path to a location for internal assets (indicators, algorithms, web).
    In production, these are in sys._MEIPASS (CORE_DIR).
    """
    base = get_core_dir()
    return os.path.join(base, *path_parts)

def sync_config(relative_path):
    """
    Ensures that an internal config file is copied to the external data directory
    if it doesn't already exist.
    """
    external = get_data_path(relative_path)
    internal = get_internal_path(relative_path)
    
    if not os.path.exists(external) and os.path.exists(internal):
        try:
            import shutil
            os.makedirs(os.path.dirname(external), exist_ok=True)
            shutil.copy2(internal, external)
            print(f"Synced {relative_path} to data directory.")
        except Exception as e:
            print(f"Failed to sync {relative_path}: {e}")
    return external

def ensure_data_file(relative_path, default_content="{}"):
    """
    Ensures a file exists in the data directory. If not, creates it with default content.
    """
    path = get_data_path(relative_path)
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(default_content)
        except Exception as e:
            print(f"Failed to create {relative_path}: {e}")
    return path
