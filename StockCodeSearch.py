import json
import os
import sys

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


def load_stock_code_index(path=None):
    cache_key = path or "default"
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]
    candidates = []
    if path:
        candidates.append(path)
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
