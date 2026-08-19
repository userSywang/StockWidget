import json
import os
import sys
from datetime import date

import requests

from StockLogic import normalize_code_or_none


BUILTIN_STOCK_CODES = {
    "sh000001": "上证指数",
    "sh512000": "券商ETF华宝",
    "sh515880": "通信ETF国泰",
    "sh588060": "科创50ETF广发",
    "sh588170": "科创半导体ETF华夏",
    "sz159801": "芯片基金",
    "sz159516": "半导设备",
    "sz159530": "机器人E",
    "sz000636": "风华高科",
    "sz000938": "紫光股份",
    "sz002273": "水晶光电",
    "sz002281": "光迅科技",
    "sz002384": "东山精密",
    "sz300308": "中际旭创",
    "sh600183": "生益科技",
    "sh600186": "莲花控股",
    "sh600487": "亨通光电",
    "sh600584": "长电科技",
    "sh603118": "共进股份",
    "sh603259": "药明康德",
    "sh603986": "兆易创新",
}


def _compact(text):
    return "".join(str(text or "").split()).lower()


_INDEX_CACHE = {}

_UPDATE_REPO = os.environ.get("STOCKWIDGET_UPDATE_REPO", "userSywang/StockWidget")
_UPDATE_BRANCH = os.environ.get("STOCKWIDGET_UPDATE_BRANCH", "main")
REMOTE_INDEX_URL = f"https://raw.githubusercontent.com/{_UPDATE_REPO}/{_UPDATE_BRANCH}/resources/stock_codes_list.json"


def downloaded_index_path():
    """后台下载的代码索引缓存路径（%APPDATA%/StockWidget）。"""
    root = os.getenv("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "StockWidget", "stock_codes_list.json")


def _index_updated_today(path):
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return False
    updated_at = str((payload or {}).get("updated_at") or "")
    return updated_at.startswith(date.today().strftime("%Y-%m-%d"))


def refresh_code_index_from_remote(getter=None, force=False, cache_path=None):
    """后台拉取远端代码索引到本地缓存，成功后使内存索引缓存失效。

    当天已刷新过则跳过（force=True 强制）。返回 True 表示缓存已更新。
    任何失败都静默返回 False，保持旧的本地数据可用。
    """
    cache_path = cache_path or downloaded_index_path()
    if not force and _index_updated_today(cache_path):
        return False
    getter = getter or requests.get
    try:
        response = getter(REMOTE_INDEX_URL, timeout=5, headers={"User-Agent": "StockWidget"})
        if getattr(response, "status_code", 0) != 200:
            return False
        payload = json.loads(response.text)
    except Exception:
        return False
    codes = payload.get("codes") if isinstance(payload, dict) else None
    if not isinstance(codes, dict) or not codes:
        return False
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        tmp = cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False)
        os.replace(tmp, cache_path)
    except Exception:
        return False
    _INDEX_CACHE.pop("default", None)
    return True


def load_stock_code_index(path=None):
    cache_key = path or "default"
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]
    candidates = []
    if path:
        candidates.append(path)
    else:
        # 后台下载的缓存（每日自动更新）优先于打包时内置的静态索引
        candidates.append(downloaded_index_path())
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(base, "resources", "stock_codes_list.json"))
    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as file:
                payload = json.load(file)
            codes = payload.get("codes") if isinstance(payload, dict) else payload
            if isinstance(codes, dict):
                _INDEX_CACHE[cache_key] = codes
                return codes
        except Exception:
            continue
    _INDEX_CACHE[cache_key] = {}
    return {}


def _iter_index_entries(code_index):
    for key, value in (code_index or {}).items():
        if not isinstance(value, dict):
            continue
        code = normalize_code_or_none(key) or normalize_code_or_none(f"{value.get('market', '')}{value.get('code', '')}")
        name = str(value.get("name") or "").strip()
        if code and name:
            yield code, name


def resolve_stock_code(text, code_names=None, code_index=None):
    raw = str(text or "").strip()
    code = normalize_code_or_none(raw)
    if code:
        return code

    query = _compact(raw)
    if not query:
        return ""

    entries = []
    for source in (code_names or {}, BUILTIN_STOCK_CODES):
        if isinstance(source, dict):
            entries.extend((normalize_code_or_none(code), str(name or "").strip()) for code, name in source.items())
    entries.extend(_iter_index_entries(code_index if code_index is not None else load_stock_code_index()))

    scored = []
    seen = set()
    for code, name in entries:
        if not code or not name or (code, name) in seen:
            continue
        seen.add((code, name))
        candidate = _compact(name)
        if candidate == query:
            score = 100
        elif candidate.startswith(query):
            score = 80
        elif query in candidate:
            score = 60
        else:
            continue
        scored.append((score, len(candidate), code, name))

    if not scored:
        return ""
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return scored[0][2]
