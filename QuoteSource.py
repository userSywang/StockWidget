# -*- coding: utf-8 -*-
"""行情数据源层：HTTP 拉取与响应解析（新浪/腾讯/东财），纯函数、不含 UI 逻辑。

WidgetPanel 中的同名方法是对本模块的委托，保持类方法签名不变以便测试注入。
"""
import requests

from StockLogic import normalize_codes


def _resolve_getter(getter=None):
    return getter or requests.get


def eastmoney_secid(code):
    """sh600000 -> 1.600000（东财 secid：沪 1 深 0）。"""
    code = normalize_codes([code])
    if not code:
        return ""
    code = code[0]
    market = "1" if code.startswith("sh") else "0"
    return f"{market}.{code[2:]}"


def baostock_code(code):
    """sh600000 -> sh.600000（baostock 代码格式）。"""
    code = normalize_codes([code])
    if not code:
        return ""
    code = code[0]
    return f"{code[:2]}.{code[2:]}"


def intraday_minute_index(time_text):
    """交易时间 -> 分钟序号：9:30 起 0~120，13:00 起 121~240；非交易时间返回 None。"""
    text = str(time_text or "").strip()
    if " " in text:
        text = text.split()[-1]
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    total = hour * 60 + minute
    if 9 * 60 + 30 <= total <= 11 * 60 + 30:
        return total - (9 * 60 + 30)
    if 13 * 60 <= total <= 15 * 60:
        return 121 + total - (13 * 60)
    return None


def parse_sina_response(text):
    """解析新浪批量行情响应文本，返回 {code: 字段列表}。

    行格式：var hq_str_sh600000="名称,今开,昨收,...,日期,时间,00";
    与 WidgetPanel._get_price 原内联解析逻辑一致（含 len(parts)<30 跳过规则）。
    """
    result = {}
    for line in str(text or "").split("\n"):
        if not line or '"' not in line:
            continue
        heads = line.split('="')[0].split("_")
        parts = line.split('="')[1].split(",")
        if len(parts) < 30:
            continue
        result[heads[2]] = parts
    return result


def fetch_sina_quotes(codes, getter=None):
    """一次 HTTP 批量拉取新浪实时行情，返回 {code: 字段列表}。"""
    label = ",".join(codes)
    if not label:
        return {}
    url = "https://hq.sinajs.cn/list=" + label
    headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
    getter = _resolve_getter(getter)
    response = getter(url, headers=headers, timeout=3)
    response.encoding = "gbk"
    return parse_sina_response(getattr(response, "text", ""))


def parse_tencent_daily_payload(code, payload):
    """解析腾讯日 K 响应 JSON，返回 [{date, open, close, high, low, volume, amount}]。"""
    data = ((payload or {}).get("data") or {}).get(code) or {}
    klines = data.get("qfqday") or data.get("day") or []
    rows = []
    for parts in klines:
        if not isinstance(parts, (list, tuple)) or len(parts) < 6:
            continue
        try:
            rows.append({
                "date": str(parts[0]),
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]) if len(parts) > 6 else 0.0,
            })
        except Exception:
            continue
    return rows


def fetch_tencent_daily_klines(code, limit=20, getter=None):
    """拉取腾讯前复权日 K 线。"""
    getter = _resolve_getter(getter)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{int(limit)},qfq"
    response = getter(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
    return parse_tencent_daily_payload(code, response.json())


def fetch_eastmoney_daily_klines(code, limit=20, getter=None):
    """拉取东财前复权日 K 线。"""
    getter = _resolve_getter(getter)
    headers = {"Referer": "https://quote.eastmoney.com", "User-Agent": "Mozilla/5.0"}
    secid = eastmoney_secid(code)
    if not secid:
        return []
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&klt=101&fqt=1&lmt={int(limit)}&end=20500101"
    )
    response = getter(url, headers=headers, timeout=5)
    payload = response.json()
    klines = (((payload or {}).get("data") or {}).get("klines") or [])
    rows = []
    for raw in klines:
        parts = str(raw).split(",")
        if len(parts) < 6:
            continue
        try:
            rows.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]) if len(parts) > 6 else 0.0,
            })
        except Exception:
            continue
    return rows


def parse_eastmoney_intraday_payload(payload):
    """解析东财分时响应 JSON，返回 {points, prev_close, max_minute}。"""
    data = (payload or {}).get("data") or {}
    trends = data.get("trends") or []
    points = []
    prev_close = 0.0
    try:
        prev_close = float(data.get("preClose") or data.get("pre_close") or 0.0)
    except Exception:
        prev_close = 0.0
    for raw in trends:
        parts = str(raw or "").split(",")
        if len(parts) < 3:
            continue
        minute = intraday_minute_index(parts[0])
        if minute is None:
            continue
        try:
            price = float(parts[2] or 0.0)
        except Exception:
            continue
        if price <= 0:
            continue
        point = {"minute": minute, "price": price}
        if len(parts) > 7:
            try:
                avg = float(parts[7] or 0.0)
                if avg > 0:
                    point["avg"] = avg
            except Exception:
                pass
        points.append(point)
    points.sort(key=lambda item: item["minute"])
    return {"points": points, "prev_close": prev_close, "max_minute": 241}


def fetch_eastmoney_intraday_trend(code, getter=None):
    """拉取东财当日分时走势。"""
    getter = _resolve_getter(getter)
    secid = eastmoney_secid(code)
    if not secid:
        return {}
    headers = {"Referer": "https://quote.eastmoney.com", "User-Agent": "Mozilla/5.0"}
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
        f"?secid={secid}&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58&iscr=0&iscca=0&ndays=1"
    )
    response = getter(url, headers=headers, timeout=5)
    return parse_eastmoney_intraday_payload(response.json())
