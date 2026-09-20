import json
import os
from datetime import datetime, timedelta

from ConfigStore import config_path


NEWS_CACHE_FILE = "realtime_news_cache.json"
NEWS_CACHE_VERSION = 2
NEWS_CACHE_DAYS = 3
NEWS_CACHE_MAX_ITEMS = 5000


def news_cache_path(base_dir=None):
    return config_path(file_name=NEWS_CACHE_FILE, base_dir=base_dir)


def _cutoff_timestamp(now=None, days=NEWS_CACHE_DAYS):
    current = now if isinstance(now, datetime) else datetime.now()
    return int((current - timedelta(days=max(1, int(days)))).timestamp())


def _normalize_item(value):
    if not isinstance(value, dict):
        return None
    item_id = str(value.get("id") or "").strip()[:120]
    try:
        timestamp = int(value.get("timestamp") or 0)
    except (TypeError, ValueError):
        timestamp = 0
    if not item_id or timestamp <= 0:
        return None
    stocks = value.get("stocks") if isinstance(value.get("stocks"), list) else []
    return {
        "id": item_id,
        "source": str(value.get("source") or "财经快讯").strip()[:40],
        "title": str(value.get("title") or "").strip()[:240],
        "summary": str(value.get("summary") or "").strip()[:1200],
        "published_at": str(value.get("published_at") or "").strip()[:32],
        "timestamp": timestamp,
        "important": bool(value.get("important")),
        "category": str(value.get("category") or "").strip()[:80],
        "stocks": [str(code).strip()[:20] for code in stocks[:20] if str(code).strip()],
        "url": str(value.get("url") or "").strip()[:600],
    }


def merge_news_items(existing, incoming, now=None, days=NEWS_CACHE_DAYS, max_items=NEWS_CACHE_MAX_ITEMS):
    cutoff = _cutoff_timestamp(now=now, days=days)
    by_id = {}
    for value in list(incoming or []) + list(existing or []):
        item = _normalize_item(value)
        if item is None or item["timestamp"] < cutoff or item["id"] in by_id:
            continue
        by_id[item["id"]] = item
    return sorted(by_id.values(), key=lambda item: item["timestamp"], reverse=True)[:max(1, int(max_items))]


def load_news_cache(base_dir=None, now=None, days=NEWS_CACHE_DAYS):
    try:
        with open(news_cache_path(base_dir=base_dir), "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("version") != NEWS_CACHE_VERSION:
        return []
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return merge_news_items([], items, now=now, days=days)


def save_news_cache(items, base_dir=None, now=None, days=NEWS_CACHE_DAYS):
    path = news_cache_path(base_dir=base_dir)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    normalized = merge_news_items([], items, now=now, days=days)
    current = now if isinstance(now, datetime) else datetime.now()
    payload = {
        "version": NEWS_CACHE_VERSION,
        "updated_at": current.strftime("%Y-%m-%d %H:%M:%S"),
        "items": normalized,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return path
