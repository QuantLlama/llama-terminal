import os
import shutil
import appdirs

user_cache_dir = appdirs.user_cache_dir("py-yfinance")
print(f"yfinance cache dir: {user_cache_dir}")

if os.path.exists(user_cache_dir):
    try:
        shutil.rmtree(user_cache_dir)
        print("Cache cleared successfully.")
    except Exception as e:
        print(f"Error clearing cache: {e}")
else:
    print("Cache directory not found.")
