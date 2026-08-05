import re


DEFAULT_GROUP_NAME = "默认"
DEFAULT_WARNING_TEXT = "谨慎交易，信号只是辅助，仓位和纪律优先。"
DEFAULT_STRATEGY_ALERT_CONFIG = {
    "enabled": False,
    "positions": [],
    "notifications": {
        "desktop_popup": True,
        "panel_highlight": True,
        "remote_push": False,
        "remote_channel": "wecom",
        "webhook_url": "",
    },
    "rules": {
        "max_loss_enabled": True,
        "max_loss_pct": 5.0,
        "stock_ma5_break_enabled": True,
        "index_ma5_break_enabled": True,
        "index_ma10_break_enabled": True,
        "trailing_profit_enabled": True,
        "trailing_tiers": [
            {"profit_pct": 20.0, "lock_pct": 10.0},
            {"profit_pct": 30.0, "lock_pct": 20.0},
            {"profit_pct": 40.0, "lock_pct": 30.0},
        ],
        "skip_raise_on_volume_drop": True,
        "reduce_half_enabled": True,
        "reduce_half_profit_pct": 45.0,
        "max_position_pct": 20.0,
        "block_heavy_position_on_index_ma5_down": True,
        "stale_position_enabled": True,
        "stale_position_days": 12,
    },
}

_RE_FULL = re.compile(r"^(sh|sz|bj|bk|gn|sw)\d+$")
_RE_6 = re.compile(r"^\d{6}$")


def normalize_code_or_none(value: str):
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    if not s:
        return None
    if _RE_FULL.match(s):
        return s
    if _RE_6.match(s):
        if s.startswith("86"):
            return "bk" + s
        if s[0] == "6" or s[0:2] == "90" or s[0] == "5":
            return "sh" + s
        if s[0] in ("0", "1", "2", "3"):
            return "sz" + s
        if s[0] in ("8", "4") or s[0:2] == "92":
            return "bj" + s
    return None


def normalize_codes(codes):
    seen = set()
    result = []
    for code in codes or []:
        norm = normalize_code_or_none(str(code))
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def normalize_groups(groups, legacy_codes=None):
    normalized = []
    seen_group_names = set()
    for group in groups or []:
        if not isinstance(group, dict):
            continue
        name = str(group.get("name") or DEFAULT_GROUP_NAME).strip() or DEFAULT_GROUP_NAME
        base = name
        i = 2
        while name in seen_group_names:
            name = f"{base}{i}"
            i += 1
        codes = normalize_codes(group.get("codes") or [])
        if not codes:
            continue
        seen_group_names.add(name)
        normalized.append({"name": name, "codes": codes})

    if normalized:
        return normalized

    codes = normalize_codes(legacy_codes or ["sh000001"])
    return [{"name": DEFAULT_GROUP_NAME, "codes": codes or ["sh000001"]}]


def flatten_group_codes(groups):
    return normalize_codes(code for group in groups or [] for code in group.get("codes", []))


def default_alert_rule():
    return {
        "enabled": False,
        "name": "科技共振提醒",
        "display_mode": "on_trigger",
        "targets": [
            {"code": "sh000001", "op": ">", "pct": 0.0, "volume": False},
            {"code": "sh512000", "op": ">=", "pct": 2.0, "volume": True},
            {"code": "sh515880", "op": ">=", "pct": 3.0, "volume": False},
        ],
        "message": "共振信号出现，先观察量能持续性，避免冲动交易。",
    }


def normalize_alert_target(target):
    if not isinstance(target, dict):
        target = {}
    code = normalize_code_or_none(target.get("code"))
    if not code:
        return None
    op = target.get("op") if target.get("op") in (">", ">=") else ">="
    try:
        pct = float(target.get("pct", 0.0))
    except Exception:
        pct = 0.0
    return {
        "code": code,
        "op": op,
        "pct": pct,
        "volume": bool(target.get("volume", False)),
    }


def _legacy_alert_targets(rule):
    targets = []
    index_code = normalize_code_or_none(rule.get("index_code"))
    if index_code:
        targets.append({"code": index_code, "op": ">", "pct": 0.0, "volume": False})
    code_a = normalize_code_or_none(rule.get("code_a"))
    if code_a:
        targets.append({
            "code": code_a,
            "op": ">=",
            "pct": rule.get("pct_a", 0.0),
            "volume": bool(rule.get("volume_a", False)),
        })
    code_b = normalize_code_or_none(rule.get("code_b"))
    if code_b:
        targets.append({
            "code": code_b,
            "op": ">=",
            "pct": rule.get("pct_b", 0.0),
            "volume": bool(rule.get("volume_b", False)),
        })
    return targets


def normalize_alert_targets(targets, legacy_rule=None):
    source = targets if isinstance(targets, list) else _legacy_alert_targets(legacy_rule or {})
    normalized = []
    seen = set()
    for target in source:
        item = normalize_alert_target(target)
        if not item or item["code"] in seen:
            continue
        seen.add(item["code"])
        normalized.append(item)
    return normalized or list(default_alert_rule()["targets"])


def normalize_alert_rule(rule):
    if not isinstance(rule, dict):
        rule = {}
    base = default_alert_rule()
    base.update(rule)
    base["enabled"] = bool(base.get("enabled", False))
    base["name"] = str(base.get("name") or "联动提醒").strip() or "联动提醒"
    base["display_mode"] = base.get("display_mode") if base.get("display_mode") in ("always", "on_trigger") else "on_trigger"
    base["targets"] = normalize_alert_targets(base.get("targets"), base)
    base["message"] = str(base.get("message") or "").strip()
    return base


def normalize_alert_rules(rules):
    normalized = [normalize_alert_rule(rule) for rule in (rules or []) if isinstance(rule, dict)]
    return normalized or [default_alert_rule()]


def _quote_pct(quotes, code):
    q = (quotes or {}).get(code) or {}
    try:
        return float(q.get("change_pct", 0.0))
    except Exception:
        return 0.0


def _volume_ok(target, quotes, previous_quotes):
    if not target.get("volume"):
        return True
    code = target.get("code")
    current = (quotes or {}).get(code) or {}
    previous = (previous_quotes or {}).get(code) or {}
    try:
        cur_vol = float(current.get("volume", 0.0))
        prev_vol = float(previous.get("volume", 0.0))
    except Exception:
        return False
    return prev_vol > 0 and cur_vol > prev_vol


def _target_pct_ok(target, quotes):
    pct = _quote_pct(quotes, target.get("code"))
    threshold = float(target.get("pct", 0.0))
    if target.get("op") == ">":
        return pct > threshold
    return pct >= threshold


def evaluate_alert_rule(rule, quotes, previous_quotes=None):
    rule = normalize_alert_rule(rule)
    if not rule["enabled"]:
        return {"triggered": False, "status": "未启用", "text": ""}

    targets = rule.get("targets", [])
    missing = [target["code"] for target in targets if target["code"] not in (quotes or {})]
    if missing:
        return {"triggered": False, "status": f"缺少行情：{','.join(missing)}", "text": ""}

    checks = [_target_pct_ok(target, quotes) and _volume_ok(target, quotes, previous_quotes) for target in targets]
    triggered = all(checks)
    if triggered:
        return {"triggered": True, "status": "已触发", "text": rule["message"]}
    return {"triggered": False, "status": "未触发", "text": ""}


def evaluate_alert_rules(rules, quotes, previous_quotes=None):
    results = []
    for rule in normalize_alert_rules(rules):
        state = evaluate_alert_rule(rule, quotes, previous_quotes)
        state["rule"] = rule
        results.append(state)
    return results


def default_price_alert():
    return {
        "enabled": True,
        "code": "sh000001",
        "direction": "above",
        "price": 0.0,
        "message": "价格提醒触发",
    }


def normalize_price_alert(alert):
    if not isinstance(alert, dict):
        alert = {}
    code = normalize_code_or_none(alert.get("code")) or "sh000001"
    direction = alert.get("direction") if alert.get("direction") in ("above", "below") else "above"
    try:
        price = float(alert.get("price", 0.0))
    except Exception:
        price = 0.0
    return {
        "enabled": bool(alert.get("enabled", True)),
        "code": code,
        "direction": direction,
        "price": max(0.0, price),
        "message": str(alert.get("message") or "").strip(),
    }


def normalize_price_alerts(alerts):
    return [normalize_price_alert(alert) for alert in (alerts or []) if isinstance(alert, dict)]


def evaluate_price_alerts(alerts, quotes):
    triggered_by_code = {}
    for alert in normalize_price_alerts(alerts):
        if not alert.get("enabled"):
            continue
        quote = (quotes or {}).get(alert["code"]) or {}
        try:
            current_price = float(quote.get("price", 0.0))
        except Exception:
            continue
        if current_price <= 0:
            continue
        if alert["direction"] == "above":
            triggered = current_price >= alert["price"]
            direction_text = "高于"
        else:
            triggered = current_price <= alert["price"]
            direction_text = "低于"
        name = str(quote.get("name") or alert["code"])
        message = alert.get("message") or "价格提醒触发"
        status_text = "已触发" if triggered else "未触发"
        detail = (
            f"{name} {alert['code']}\n"
            f"状态：{status_text}\n"
            f"当前价：{current_price:.3f}\n"
            f"条件：{direction_text} {alert['price']:.3f}\n"
            f"提示：{message}"
        )
        triggered_by_code.setdefault(alert["code"], []).append({
            "triggered": triggered,
            "direction": alert["direction"],
            "price": alert["price"],
            "current_price": current_price,
            "message": message,
            "detail": detail,
        })
    return triggered_by_code


def _bounded_float(value, default, minimum=0.0, maximum=99999.0):
    try:
        number = float(value)
    except Exception:
        number = float(default)
    return max(float(minimum), min(float(maximum), number))


def _bounded_int(value, default, minimum=0, maximum=99999):
    try:
        number = int(value)
    except Exception:
        number = int(default)
    return max(int(minimum), min(int(maximum), number))


def normalize_strategy_position(position):
    if not isinstance(position, dict):
        position = {}
    code = normalize_code_or_none(position.get("code"))
    if not code:
        return None
    return {
        "code": code,
        "cost_price": _bounded_float(position.get("cost_price"), 0.0, 0.0, 99999.999),
        "buy_date": str(position.get("buy_date") or "").strip(),
        "position_pct": _bounded_float(position.get("position_pct"), 0.0, 0.0, 100.0),
        "peak_profit_pct": _bounded_float(position.get("peak_profit_pct"), 0.0, -100.0, 10000.0),
        "locked_profit_pct": _bounded_float(position.get("locked_profit_pct"), 0.0, 0.0, 10000.0),
        "note": str(position.get("note") or "").strip(),
    }


def normalize_strategy_alert_config(config):
    if not isinstance(config, dict):
        config = {}
    default_rules = DEFAULT_STRATEGY_ALERT_CONFIG["rules"]
    default_notifications = DEFAULT_STRATEGY_ALERT_CONFIG["notifications"]
    source_rules = config.get("rules") if isinstance(config.get("rules"), dict) else {}
    source_notifications = config.get("notifications") if isinstance(config.get("notifications"), dict) else {}
    positions = []
    seen_codes = set()
    for item in config.get("positions", []) if isinstance(config.get("positions"), list) else []:
        position = normalize_strategy_position(item)
        if not position or position["code"] in seen_codes:
            continue
        seen_codes.add(position["code"])
        positions.append(position)

    tiers = []
    source_tiers = source_rules.get("trailing_tiers")
    if not isinstance(source_tiers, list):
        source_tiers = default_rules["trailing_tiers"]
    for tier in source_tiers:
        if not isinstance(tier, dict):
            continue
        tiers.append({
            "profit_pct": _bounded_float(tier.get("profit_pct"), 0.0, 0.0, 1000.0),
            "lock_pct": _bounded_float(tier.get("lock_pct"), 0.0, 0.0, 1000.0),
        })
    if not tiers:
        tiers = list(default_rules["trailing_tiers"])

    return {
        "enabled": bool(config.get("enabled", DEFAULT_STRATEGY_ALERT_CONFIG["enabled"])),
        "positions": positions,
        "notifications": {
            "desktop_popup": bool(source_notifications.get("desktop_popup", default_notifications["desktop_popup"])),
            "panel_highlight": bool(source_notifications.get("panel_highlight", default_notifications["panel_highlight"])),
            "remote_push": bool(source_notifications.get("remote_push", default_notifications["remote_push"])),
            "remote_channel": source_notifications.get("remote_channel") if source_notifications.get("remote_channel") in ("wecom", "custom") else default_notifications["remote_channel"],
            "webhook_url": str(source_notifications.get("webhook_url") or "").strip(),
        },
        "rules": {
            "max_loss_enabled": bool(source_rules.get("max_loss_enabled", default_rules["max_loss_enabled"])),
            "max_loss_pct": _bounded_float(source_rules.get("max_loss_pct"), default_rules["max_loss_pct"], 0.0, 100.0),
            "stock_ma5_break_enabled": bool(source_rules.get("stock_ma5_break_enabled", default_rules["stock_ma5_break_enabled"])),
            "index_ma5_break_enabled": bool(source_rules.get("index_ma5_break_enabled", default_rules["index_ma5_break_enabled"])),
            "index_ma10_break_enabled": bool(source_rules.get("index_ma10_break_enabled", default_rules["index_ma10_break_enabled"])),
            "trailing_profit_enabled": bool(source_rules.get("trailing_profit_enabled", default_rules["trailing_profit_enabled"])),
            "trailing_tiers": tiers,
            "skip_raise_on_volume_drop": bool(source_rules.get("skip_raise_on_volume_drop", default_rules["skip_raise_on_volume_drop"])),
            "reduce_half_enabled": bool(source_rules.get("reduce_half_enabled", default_rules["reduce_half_enabled"])),
            "reduce_half_profit_pct": _bounded_float(source_rules.get("reduce_half_profit_pct"), default_rules["reduce_half_profit_pct"], 0.0, 1000.0),
            "max_position_pct": _bounded_float(source_rules.get("max_position_pct"), default_rules["max_position_pct"], 0.0, 100.0),
            "block_heavy_position_on_index_ma5_down": bool(source_rules.get("block_heavy_position_on_index_ma5_down", default_rules["block_heavy_position_on_index_ma5_down"])),
            "stale_position_enabled": bool(source_rules.get("stale_position_enabled", default_rules["stale_position_enabled"])),
            "stale_position_days": _bounded_int(source_rules.get("stale_position_days"), default_rules["stale_position_days"], 1, 3650),
        },
    }


def strategy_request_codes(config):
    config = normalize_strategy_alert_config(config)
    return normalize_codes(position.get("code") for position in config.get("positions", []))


def strategy_daily_request_codes(config):
    config = normalize_strategy_alert_config(config)
    codes = strategy_request_codes(config)
    rules = config.get("rules", {})
    if rules.get("index_ma5_break_enabled") or rules.get("index_ma10_break_enabled") or rules.get("block_heavy_position_on_index_ma5_down"):
        codes.extend(["sh000001", "sz399001"])
    return normalize_codes(codes)


def moving_average(daily_rows, days):
    closes = []
    for row in daily_rows or []:
        if not isinstance(row, dict):
            continue
        try:
            close = float(row.get("close", 0.0))
        except Exception:
            close = 0.0
        if close > 0:
            closes.append(close)
    if len(closes) < int(days):
        return None
    return sum(closes[-int(days):]) / int(days)


def ma_is_down(daily_rows, days):
    closes = []
    for row in daily_rows or []:
        if not isinstance(row, dict):
            continue
        try:
            close = float(row.get("close", 0.0))
        except Exception:
            close = 0.0
        if close > 0:
            closes.append(close)
    days = int(days)
    if len(closes) < days + 1:
        return False
    current = sum(closes[-days:]) / days
    previous = sum(closes[-days - 1:-1]) / days
    return current < previous


def daily_error_text(daily_rows):
    if isinstance(daily_rows, dict):
        return str(daily_rows.get("error") or "").strip()
    return ""


def trailing_lock_pct(rules, peak_profit_pct):
    if not rules.get("trailing_profit_enabled"):
        return 0.0
    lock_pct = 0.0
    for tier in rules.get("trailing_tiers", []):
        if float(peak_profit_pct) >= float(tier.get("profit_pct", 0.0)):
            lock_pct = max(lock_pct, float(tier.get("lock_pct", 0.0)))
    return lock_pct


def update_strategy_position_state(config, quotes):
    config = normalize_strategy_alert_config(config)
    if not config.get("enabled"):
        return config, False
    changed = False
    rules = config["rules"]
    positions = []
    for position in config.get("positions", []):
        item = dict(position)
        quote = (quotes or {}).get(item["code"]) or {}
        cost = float(item.get("cost_price", 0.0))
        try:
            price = float(quote.get("price", 0.0))
        except Exception:
            price = 0.0
        if cost > 0 and price > 0:
            profit_pct = round((price / cost - 1.0) * 100.0, 4)
            peak_pct = max(float(item.get("peak_profit_pct", 0.0)), profit_pct)
            lock_pct = max(float(item.get("locked_profit_pct", 0.0)), trailing_lock_pct(rules, peak_pct))
            if abs(peak_pct - float(item.get("peak_profit_pct", 0.0))) > 0.0001:
                item["peak_profit_pct"] = round(peak_pct, 4)
                changed = True
            if abs(lock_pct - float(item.get("locked_profit_pct", 0.0))) > 0.0001:
                item["locked_profit_pct"] = round(lock_pct, 4)
                changed = True
        positions.append(item)
    config["positions"] = positions
    return config, changed


def evaluate_strategy_alerts(config, quotes, daily_by_code=None):
    config = normalize_strategy_alert_config(config)
    if not config.get("enabled"):
        return []
    rules = config["rules"]
    daily_by_code = daily_by_code or {}
    index_breaks = []
    index_daily_errors = []
    if rules.get("index_ma5_break_enabled"):
        for index_code, label in (("sh000001", "上证"), ("sz399001", "深成")):
            error_text = daily_error_text(daily_by_code.get(index_code))
            if error_text:
                index_daily_errors.append(f"{label}{error_text}")
                continue
            index_quote = (quotes or {}).get(index_code) or {}
            try:
                index_price = float(index_quote.get("price", 0.0))
            except Exception:
                index_price = 0.0
            ma5 = moving_average(daily_by_code.get(index_code), 5)
            if index_price > 0 and ma5 and index_price < ma5:
                index_breaks.append(f"{label}破5日线")
    if rules.get("index_ma10_break_enabled"):
        for index_code, label in (("sh000001", "上证"), ("sz399001", "深成")):
            error_text = daily_error_text(daily_by_code.get(index_code))
            if error_text:
                if f"{label}{error_text}" not in index_daily_errors:
                    index_daily_errors.append(f"{label}{error_text}")
                continue
            index_quote = (quotes or {}).get(index_code) or {}
            try:
                index_price = float(index_quote.get("price", 0.0))
            except Exception:
                index_price = 0.0
            ma10 = moving_average(daily_by_code.get(index_code), 10)
            if index_price > 0 and ma10 and index_price < ma10:
                index_breaks.append(f"{label}破10日线")
    index_ma5_down = any(ma_is_down(daily_by_code.get(code), 5) for code in ("sh000001", "sz399001"))

    states = []
    for position in config.get("positions", []):
        quote = (quotes or {}).get(position["code"]) or {}
        name = str(quote.get("name") or position["code"])
        cost = float(position.get("cost_price", 0.0))
        try:
            price = float(quote.get("price", 0.0))
        except Exception:
            price = 0.0
        if cost <= 0 or price <= 0:
            states.append({
                "code": position["code"],
                "name": name,
                "profit_pct": None,
                "locked_profit_pct": float(position.get("locked_profit_pct", 0.0)),
                "triggered": False,
                "severity": "neutral",
                "status": "等待价格",
            })
            continue

        profit_pct = round((price / cost - 1.0) * 100.0, 4)
        lock_pct = float(position.get("locked_profit_pct", 0.0))
        status_parts = []
        triggered = False
        severity = "neutral"
        if rules.get("max_loss_enabled") and profit_pct <= -float(rules.get("max_loss_pct", 0.0)):
            status_parts.append("触发止损")
            triggered = True
            severity = "danger"
        if lock_pct > 0:
            if profit_pct <= lock_pct:
                status_parts.append(f"触发锁盈{lock_pct:.0f}%")
                triggered = True
                severity = "danger"
            else:
                status_parts.append(f"已锁盈{lock_pct:.0f}%")
        if rules.get("reduce_half_enabled") and profit_pct >= float(rules.get("reduce_half_profit_pct", 0.0)):
            status_parts.append("减半仓提醒")
            triggered = True
            if severity != "danger":
                severity = "warning"
        if rules.get("stock_ma5_break_enabled"):
            daily_rows = daily_by_code.get(position["code"])
            error_text = daily_error_text(daily_rows)
            ma5 = moving_average(daily_rows, 5)
            if error_text:
                status_parts.append(error_text)
            elif ma5 is None:
                status_parts.append("个股日线不足")
            elif price < ma5:
                status_parts.append("个股破5日线")
                triggered = True
                severity = "danger"
        if index_breaks:
            status_parts.append("大盘" + "/".join(index_breaks))
            triggered = True
            severity = "danger"
        elif index_daily_errors:
            status_parts.append("大盘" + "/".join(index_daily_errors))
        if rules.get("block_heavy_position_on_index_ma5_down") and index_ma5_down:
            status_parts.append("大盘5日线向下")
        if not status_parts:
            status_parts.append("未触发")

        states.append({
            "code": position["code"],
            "name": name,
            "profit_pct": profit_pct,
            "locked_profit_pct": lock_pct,
            "triggered": triggered,
            "severity": severity,
            "status": "，".join(status_parts),
        })
    return states
