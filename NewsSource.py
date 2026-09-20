import hashlib
import html
import json
import re
import uuid
from datetime import datetime

import requests


CLS_NEWS_URL = "https://www.cls.cn/v1/roll/get_roll_list"
EASTMONEY_NEWS_URL = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
SINA_NEWS_URL = "https://zhibo.sina.com.cn/api/zhibo/feed"
DEFAULT_NEWS_ALERT_CONFIG = {
    "enabled": True,
    "important_only": False,
    "interval_seconds": 30,
    "source": "sina",
}


def normalize_news_alert_config(value):
    value = value if isinstance(value, dict) else {}
    try:
        interval = int(value.get("interval_seconds", 30))
    except (TypeError, ValueError):
        interval = 30
    if interval not in (15, 30, 60):
        interval = 30
    source = str(value.get("source") or "sina").strip().lower()
    if source not in ("sina", "cls", "auto"):
        source = "sina"
    return {
        "enabled": bool(value.get("enabled", True)),
        "important_only": bool(value.get("important_only", False)),
        "interval_seconds": interval,
        "source": source,
    }


def _clean_text(value):
    text = re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))
    return " ".join(text.split()).strip()


def _stock_codes(values):
    result = []
    for value in values or []:
        if isinstance(value, dict):
            raw = value.get("StockID") or value.get("stock_id") or value.get("code") or value.get("symbol")
        else:
            raw = value
        match = re.search(r"(?<!\d)(\d{6})(?!\d)", str(raw or ""))
        if match and match.group(1) not in result:
            result.append(match.group(1))
    return result


def _split_bracket_title(text):
    text = _clean_text(text)
    match = re.match(r"^[【\[]([^】\]]+)[】\]]\s*(.*)$", text)
    if not match:
        sentence = re.match(r"^(.{1,42}?[。！？!?])\s*(.*)$", text)
        if sentence:
            return sentence.group(1).strip(), sentence.group(2).strip()
        if len(text) > 42:
            return text[:42].rstrip() + "…", text[42:].strip()
        return text, ""
    return match.group(1).strip(), match.group(2).strip()


def parse_sina_payload(payload):
    rows = []
    result = payload.get("result", {}) if isinstance(payload, dict) else {}
    items = result.get("data", {}).get("feed", {}).get("list", []) if isinstance(result, dict) else []
    important_terms = ("突发", "重磅", "央行", "证监会", "国务院", "降息", "降准", "停牌", "复牌")
    for item in items or []:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        title, summary = _split_bracket_title(item.get("rich_text"))
        if not title:
            continue
        published_at = str(item.get("create_time") or "").strip()
        try:
            timestamp = int(datetime.strptime(published_at, "%Y-%m-%d %H:%M:%S").timestamp())
        except (TypeError, ValueError):
            timestamp = 0
        tags = item.get("tag") if isinstance(item.get("tag"), list) else []
        category = " / ".join(
            str(tag.get("name") or "").strip() for tag in tags
            if isinstance(tag, dict) and str(tag.get("name") or "").strip()
        )
        try:
            ext = json.loads(item.get("ext") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            ext = {}
        stocks = ext.get("stocks", []) if isinstance(ext, dict) else []
        full_text = f"{title} {summary}"
        rows.append({
            "id": f"sina:{item.get('id')}",
            "source": "新浪财经",
            "title": title,
            "summary": summary,
            "published_at": published_at,
            "timestamp": timestamp,
            "important": bool(item.get("is_focus") or item.get("top_value")) or any(term in full_text for term in important_terms),
            "category": category,
            "stocks": _stock_codes(stocks),
            "url": str(item.get("docurl") or ext.get("docurl") or "").strip(),
        })
    return rows


def parse_cls_payload(payload):
    rows = []
    items = payload.get("data", {}).get("roll_data", []) if isinstance(payload, dict) else []
    for item in items or []:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        title = _clean_text(item.get("title") or item.get("brief") or item.get("content"))
        if not title:
            continue
        timestamp = int(item.get("ctime") or 0)
        published_at = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else ""
        level = str(item.get("level") or "").upper()
        rows.append({
            "id": f"cls:{item.get('id')}",
            "source": "财联社",
            "title": title,
            "summary": _clean_text(item.get("content") or item.get("brief")),
            "published_at": published_at,
            "timestamp": timestamp,
            "important": level in ("A", "B") or bool(item.get("bold")),
            "stocks": _stock_codes(item.get("stock_list")),
            "url": str(item.get("shareurl") or "").strip(),
        })
    return rows


def parse_eastmoney_payload(payload):
    rows = []
    items = payload.get("data", {}).get("fastNewsList", []) if isinstance(payload, dict) else []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("code"):
            continue
        title = _clean_text(item.get("title") or item.get("summary"))
        if not title:
            continue
        published_at = str(item.get("showTime") or "").strip()
        try:
            timestamp = int(datetime.strptime(published_at, "%Y-%m-%d %H:%M:%S").timestamp())
        except (TypeError, ValueError):
            timestamp = 0
        code = str(item.get("code"))
        rows.append({
            "id": f"eastmoney:{code}",
            "source": "东方财富",
            "title": title,
            "summary": _clean_text(item.get("summary")),
            "published_at": published_at,
            "timestamp": timestamp,
            "important": str(item.get("titleColor") or "0") not in ("", "0"),
            "stocks": _stock_codes(item.get("stockList")),
            "url": f"https://finance.eastmoney.com/a/{code}.html",
        })
    return rows


def _response_json(response):
    response.raise_for_status()
    if hasattr(response, "encoding"):
        response.encoding = "utf-8"
    return response.json()


def fetch_cls_news(session=None, page_size=20):
    session = session or requests.Session()
    params = {
        "appName": "CailianpressWeb",
        "last_time": "",
        "os": "web",
        "refresh_type": "1",
        "rn": str(max(1, min(50, int(page_size)))),
        "sv": "7.7.5",
    }
    query = "&".join(f"{key}={params[key]}" for key in sorted(params))
    sign = hashlib.md5(hashlib.sha1(query.encode("utf-8")).hexdigest().encode("ascii")).hexdigest()
    response = session.get(
        CLS_NEWS_URL,
        params={**params, "sign": sign},
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cls.cn/"},
        timeout=10,
    )
    return parse_cls_payload(_response_json(response))


def fetch_sina_news(session=None, page_size=20):
    session = session or requests.Session()
    response = session.get(
        SINA_NEWS_URL,
        params={
            "page": 1,
            "page_size": max(1, min(50, int(page_size))),
            "zhibo_id": 152,
        },
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/7x24/"},
        timeout=10,
    )
    return parse_sina_payload(_response_json(response))


def fetch_eastmoney_news(session=None, page_size=20):
    session = session or requests.Session()
    response = session.get(
        EASTMONEY_NEWS_URL,
        params={
            "client": "web",
            "biz": "web_724",
            "fastColumn": "102",
            "sortEnd": "",
            "pageSize": str(max(1, min(50, int(page_size)))),
            "req_trace": str(uuid.uuid4()),
        },
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://kuaixun.eastmoney.com/"},
        timeout=10,
    )
    return parse_eastmoney_payload(_response_json(response))


def fetch_fast_news(session=None, page_size=20, source="auto"):
    session = session or requests.Session()
    source = str(source or "auto").strip().lower()
    fetchers = {
        "sina": (fetch_sina_news, fetch_cls_news, fetch_eastmoney_news),
        "cls": (fetch_cls_news, fetch_sina_news, fetch_eastmoney_news),
        "auto": (fetch_cls_news, fetch_sina_news, fetch_eastmoney_news),
    }.get(source, (fetch_sina_news, fetch_cls_news, fetch_eastmoney_news))
    for fetcher in fetchers:
        try:
            rows = fetcher(session=session, page_size=page_size)
            if rows:
                return rows
        except Exception:
            continue
    return []
