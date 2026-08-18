import json
import os
import shutil


def config_dir(app_name="StockWidget", base_dir=None):
    root = base_dir or os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, app_name)


def config_path(app_name="StockWidget", file_name="SW_config.json", base_dir=None):
    return os.path.join(config_dir(app_name, base_dir), file_name)


def load_config(app_name="StockWidget", file_name="SW_config.json", default=None, base_dir=None):
    fallback = {} if default is None else default
    path = config_path(app_name, file_name, base_dir)
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else fallback
    except Exception:
        return fallback


def save_config(cfg, app_name="StockWidget", file_name="SW_config.json", base_dir=None, backup=True):
    directory = config_dir(app_name, base_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, file_name)
    if backup and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except Exception:
            pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(dict(cfg or {}), file, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path
