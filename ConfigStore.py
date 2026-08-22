import json
import os
import shutil
from datetime import datetime
from pathlib import Path


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


def _prune_timestamp_backups(directory, stem, suffix, keep):
    if keep <= 0:
        return
    pattern = f"{stem}_*.{suffix}.bak"
    backups = sorted(Path(directory).glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[keep:]:
        try:
            old.unlink()
        except Exception:
            pass


def save_config(cfg, app_name="StockWidget", file_name="SW_config.json", base_dir=None, backup=True, keep_backups=20):
    directory = config_dir(app_name, base_dir)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, file_name)
    if backup and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
        except Exception:
            pass
        try:
            file_path = Path(path)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            stamped = file_path.with_name(f"{file_path.stem}_{stamp}{file_path.suffix}.bak")
            shutil.copy2(path, stamped)
            _prune_timestamp_backups(directory, file_path.stem, file_path.suffix.lstrip("."), keep_backups)
        except Exception:
            pass
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(dict(cfg or {}), file, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path
