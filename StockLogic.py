import re


DEFAULT_GROUP_NAME = "默认"
DEFAULT_WARNING_TEXT = "谨慎交易，信号只是辅助，仓位和纪律优先。"
DEFAULT_STRATEGY_ALERT_CONFIG = {
    "enabled": False,
    "rule_schema_version": 1,
    "positions": [],
    "notifications": {
        "desktop_popup": True,
        "panel_highlight": True,
        "remote_push": False,
        "remote_channel": "wecom",
        "webhook_url": "",
        "daily_summary_time": "23:00",
        "push_cooldown_minutes": 30,
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

STRATEGY_ACTION_RULE_SCHEMA_VERSION = 1

ACTION_RULE_UNITS = {
    "percent": "%",
    "price": "元",
    "atr": "ATR",
    "day_high": "日新高",
    "day_low": "日低点",
    "ma_days": "日线MA",
    "days": "天",
    "trend": "趋势",
}

ACTION_RULE_ACTIONS = {
    "entry_signal": "提醒观察/买入",
    "clear_position": "提醒清仓",
    "add_position": "提醒加仓",
    "reduce_position": "提醒减仓",
    "update_stop_line": "提醒止盈线变化",
    "limit_position": "限制仓位",
    "block_open": "禁止新开仓",
}


DEFAULT_TURTLE_PARAMS = {
    "entry_days": 20,
    "exit_days": 10,
    "atr_stop_multiple": 2.0,
    "pyramid_atr_multiple": 0.5,
    "max_units": 4,
    "position_sizing": "atr_risk",
}


def _normalize_turtle_params(params):
    params = params if isinstance(params, dict) else {}
    sizing = str(params.get("position_sizing") or DEFAULT_TURTLE_PARAMS["position_sizing"]).strip()
    if sizing not in ("atr_risk", "fixed_percent", "manual"):
        sizing = DEFAULT_TURTLE_PARAMS["position_sizing"]
    return {
        "entry_days": _bounded_int(params.get("entry_days"), DEFAULT_TURTLE_PARAMS["entry_days"], 2, 250),
        "exit_days": _bounded_int(params.get("exit_days"), DEFAULT_TURTLE_PARAMS["exit_days"], 2, 250),
        "atr_stop_multiple": _bounded_float(params.get("atr_stop_multiple"), DEFAULT_TURTLE_PARAMS["atr_stop_multiple"], 0.1, 20.0),
        "pyramid_atr_multiple": _bounded_float(params.get("pyramid_atr_multiple"), DEFAULT_TURTLE_PARAMS["pyramid_atr_multiple"], 0.1, 20.0),
        "max_units": _bounded_int(params.get("max_units"), DEFAULT_TURTLE_PARAMS["max_units"], 1, 20),
        "position_sizing": sizing,
    }


def default_turtle_action_rules(params=None):
    params = _normalize_turtle_params(params)
    return [
        _action_rule(
            "turtle_entry_20d",
            f"{params['entry_days']}日新高突破买入提醒",
            True,
            {
                "metric": "stock_price",
                "operator": ">",
                "threshold": {"type": "donchian_high", "period": params["entry_days"]},
            },
            {"type": "entry_signal", "reason": "donchian_breakout", "position_sizing": params["position_sizing"]},
            "turtle",
        ),
        _action_rule(
            "turtle_atr_stop",
            f"{params['atr_stop_multiple']:.1f}ATR止损提醒",
            True,
            {
                "metric": "stock_price",
                "operator": "<=",
                "threshold": {"type": "atr_offset", "basis": "entry_price", "multiple": params["atr_stop_multiple"], "direction": "down"},
            },
            {"type": "clear_position", "reason": "atr_stop"},
            "turtle",
        ),
        _action_rule(
            "turtle_pyramid_0_5atr",
            f"{params['pyramid_atr_multiple']:.1f}ATR浮盈加仓提醒",
            True,
            {
                "metric": "stock_price",
                "operator": ">=",
                "threshold": {"type": "atr_offset", "basis": "last_entry_price", "multiple": params["pyramid_atr_multiple"], "direction": "up"},
            },
            {"type": "add_position", "max_units": params["max_units"], "reason": "pyramid_on_profit"},
            "turtle",
        ),
        _action_rule(
            "turtle_exit_10d",
            f"{params['exit_days']}日低点离场提醒",
            True,
            {
                "metric": "stock_price",
                "operator": "<",
                "threshold": {"type": "donchian_low", "period": params["exit_days"]},
            },
            {"type": "clear_position", "reason": "donchian_exit"},
            "turtle",
        ),
    ]


def default_strategy_profiles(normalized_rules=None):
    rules = dict(normalized_rules or DEFAULT_STRATEGY_ALERT_CONFIG["rules"])
    turtle_params = _normalize_turtle_params({})
    turtle_rules = _normalize_strategy_rules({
        "max_loss_enabled": False,
        "stock_ma5_break_enabled": False,
        "index_ma5_break_enabled": False,
        "index_ma10_break_enabled": False,
        "trailing_profit_enabled": False,
        "reduce_half_enabled": False,
        "max_position_pct": 20.0,
        "block_heavy_position_on_index_ma5_down": False,
        "stale_position_enabled": False,
    }, rules)
    return [
        {"id": "default", "name": "默认策略", "desc": "百分比止损、均线风控、阶梯移动止盈。", "strategy_type": "legacy", "rules": rules},
        {
            "id": "turtle:classic",
            "name": "海龟策略模板",
            "desc": "20日新高突破、2ATR止损、0.5ATR浮盈加仓、10日低点离场。当前作为动作提醒模板，不自动交易。",
            "strategy_type": "turtle",
            "turtle_params": turtle_params,
            "rules": turtle_rules,
            "action_rules": default_turtle_action_rules(turtle_params),
        },
    ]

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
    direction = alert.get("direction") if alert.get("direction") in ("above", "below", "below_ma5") else "above"
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


def evaluate_price_alerts(alerts, quotes, daily_by_code=None):
    triggered_by_code = {}
    daily_by_code = daily_by_code or {}
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
        threshold_price = alert["price"]
        if alert["direction"] == "below_ma5":
            average = moving_average(daily_by_code.get(alert["code"]), 5)
            if average is None:
                continue
            threshold_price = float(average)
            triggered = current_price <= threshold_price
            direction_text = "低于MA5"
        elif alert["direction"] == "above":
            triggered = current_price >= threshold_price
            direction_text = "高于"
        else:
            triggered = current_price <= threshold_price
            direction_text = "低于"
        name = str(quote.get("name") or alert["code"])
        message = alert.get("message") or "价格提醒触发"
        status_text = "已触发" if triggered else "未触发"
        detail = (
            f"{name} {alert['code']}\n"
            f"状态：{status_text}\n"
            f"当前价：{current_price:.3f}\n"
            f"条件：{direction_text} {threshold_price:.3f}\n"
            f"提示：{message}"
        )
        triggered_by_code.setdefault(alert["code"], []).append({
            "triggered": triggered,
            "direction": alert["direction"],
            "price": threshold_price,
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


def _normalize_time_text(value, default="23:00"):
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})", text)
    if not match:
        return default
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return f"{hour:02d}:{minute:02d}"


def normalize_strategy_position(position):
    if not isinstance(position, dict):
        position = {}
    code = normalize_code_or_none(position.get("code"))
    if not code:
        return None
    position_rules = position.get("rules") if isinstance(position.get("rules"), dict) else None
    return {
        "code": code,
        "strategy_id": str(position.get("strategy_id") or position.get("profile_id") or "").strip(),
        "cost_price": _bounded_float(position.get("cost_price"), 0.0, 0.0, 99999.999),
        "buy_date": str(position.get("buy_date") or "").strip(),
        "position_pct": _bounded_float(position.get("position_pct"), 0.0, 0.0, 100.0),
        "peak_profit_pct": _bounded_float(position.get("peak_profit_pct"), 0.0, -100.0, 10000.0),
        "locked_profit_pct": _bounded_float(position.get("locked_profit_pct"), 0.0, 0.0, 10000.0),
        "lock_raised": bool(position.get("lock_raised", False)),
        "last_stop_price": _bounded_float(position.get("last_stop_price"), 0.0, 0.0, 999999.9999),
        "stop_line_changed": bool(position.get("stop_line_changed", False)),
        "stop_line_previous_price": _bounded_float(position.get("stop_line_previous_price"), 0.0, 0.0, 999999.9999),
        "note": str(position.get("note") or "").strip(),
        "rules": dict(position_rules) if position_rules is not None else {},
    }


def _normalize_strategy_rules(source_rules, fallback=None):
    default_rules = fallback or DEFAULT_STRATEGY_ALERT_CONFIG["rules"]
    source_rules = source_rules if isinstance(source_rules, dict) else {}
    source_tiers = source_rules.get("trailing_tiers")
    if not isinstance(source_tiers, list):
        source_tiers = default_rules.get("trailing_tiers", [])
    tiers = []
    for tier in source_tiers:
        if not isinstance(tier, dict):
            continue
        tiers.append({
            "profit_pct": _bounded_float(tier.get("profit_pct"), 0.0, 0.0, 1000.0),
            "lock_pct": _bounded_float(tier.get("lock_pct"), 0.0, 0.0, 1000.0),
        })
    if not tiers:
        tiers = list(default_rules.get("trailing_tiers", []))
    return {
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
    }


def _action_rule_parameter_from_condition(condition):
    condition = condition if isinstance(condition, dict) else {}
    threshold = condition.get("threshold") if isinstance(condition.get("threshold"), dict) else {}
    threshold_type = str(threshold.get("type") or "")
    if threshold_type == "percent":
        return {"value": float(threshold.get("value", 0.0)), "unit": "percent"}
    if threshold_type == "days":
        return {"value": int(threshold.get("value", 0)), "unit": "days"}
    if threshold_type == "moving_average":
        return {"value": int(threshold.get("period", 0)), "unit": "ma_days"}
    if threshold_type == "donchian_high":
        return {"value": int(threshold.get("period", 0)), "unit": "day_high"}
    if threshold_type == "donchian_low":
        return {"value": int(threshold.get("period", 0)), "unit": "day_low"}
    if threshold_type == "atr_offset":
        return {"value": float(threshold.get("multiple", 0.0)), "unit": "atr"}
    if threshold_type == "trend":
        return {"value": int(threshold.get("period", 0)), "unit": "trend"}
    return {"value": 0.0, "unit": threshold_type or "price"}


def _condition_from_action_parameter(metric, operator, parameter, old_condition=None):
    old_condition = old_condition if isinstance(old_condition, dict) else {}
    old_threshold = old_condition.get("threshold") if isinstance(old_condition.get("threshold"), dict) else {}
    unit = str((parameter or {}).get("unit") or "").strip()
    value = (parameter or {}).get("value", 0.0)
    if unit == "percent":
        threshold = {"type": "percent", "value": float(value)}
    elif unit == "days":
        threshold = {"type": "days", "value": int(value)}
    elif unit == "ma_days":
        threshold = {"type": "moving_average", "scope": old_threshold.get("scope", "stock"), "period": int(value)}
    elif unit == "day_high":
        threshold = {"type": "donchian_high", "period": int(value)}
    elif unit == "day_low":
        threshold = {"type": "donchian_low", "period": int(value)}
    elif unit == "atr":
        threshold = {
            "type": "atr_offset",
            "basis": old_threshold.get("basis", "entry_price"),
            "multiple": float(value),
            "direction": old_threshold.get("direction", "down"),
        }
    elif unit == "trend":
        threshold = {"type": "trend", "scope": old_threshold.get("scope", "index"), "period": int(value), "value": old_threshold.get("value", "down")}
    else:
        threshold = {"type": "price", "value": float(value)}
    return {"metric": metric or old_condition.get("metric", "stock_price"), "operator": operator or old_condition.get("operator", ">="), "threshold": threshold}


def normalize_strategy_action_rule(rule):
    rule = rule if isinstance(rule, dict) else {}
    condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else {}
    action = rule.get("action") if isinstance(rule.get("action"), dict) else {}
    parameter = rule.get("parameter") if isinstance(rule.get("parameter"), dict) else _action_rule_parameter_from_condition(condition)
    unit = str(parameter.get("unit") or "").strip()
    if unit not in ACTION_RULE_UNITS:
        unit = _action_rule_parameter_from_condition(condition).get("unit", "price")
    try:
        value = float(parameter.get("value", 0.0))
    except Exception:
        value = 0.0
    if unit in ("day_high", "day_low", "ma_days", "days", "trend"):
        value = int(max(1, round(value)))
    normalized_parameter = {"value": value, "unit": unit}
    normalized_condition = _condition_from_action_parameter(
        condition.get("metric", "stock_price"),
        condition.get("operator", ">="),
        normalized_parameter,
        condition,
    )
    return {
        "id": str(rule.get("id") or "custom_rule").strip(),
        "schema_version": STRATEGY_ACTION_RULE_SCHEMA_VERSION,
        "source": str(rule.get("source") or "custom"),
        "name": str(rule.get("name") or rule.get("id") or "动作规则"),
        "enabled": bool(rule.get("enabled", True)),
        "condition": normalized_condition,
        "parameter": normalized_parameter,
        "action": dict(action),
    }


def _action_rule(rule_id, name, enabled, condition, action, source="legacy"):
    parameter = _action_rule_parameter_from_condition(condition)
    return {
        "id": rule_id,
        "schema_version": STRATEGY_ACTION_RULE_SCHEMA_VERSION,
        "source": source,
        "name": name,
        "enabled": bool(enabled),
        "condition": condition,
        "parameter": parameter,
        "action": action,
    }


def strategy_action_rules_from_rules(rules, source="legacy"):
    """Convert current strategy settings into stable action-rule records.

    This is a compatibility layer: existing evaluation still uses legacy fields,
    while new strategy types can be added as action rules without changing the
    saved position/profile model again.
    """
    rules = _normalize_strategy_rules(rules)
    return [
        _action_rule(
            "max_loss",
            "浮亏清仓",
            rules.get("max_loss_enabled"),
            {
                "metric": "profit_pct",
                "operator": "<=",
                "threshold": {"type": "percent", "value": -float(rules.get("max_loss_pct", 0.0))},
            },
            {"type": "clear_position", "reason": "max_loss"},
            source,
        ),
        _action_rule(
            "stock_ma5_break",
            "个股5日线清仓",
            rules.get("stock_ma5_break_enabled"),
            {
                "metric": "stock_price",
                "operator": "<",
                "threshold": {"type": "moving_average", "scope": "stock", "period": 5},
            },
            {"type": "clear_position", "reason": "stock_ma_break"},
            source,
        ),
        _action_rule(
            "index_ma5_break",
            "大盘5日线清仓",
            rules.get("index_ma5_break_enabled"),
            {
                "metric": "index_price",
                "operator": "<",
                "threshold": {"type": "moving_average", "scope": "index", "period": 5},
            },
            {"type": "clear_position", "reason": "index_ma_break"},
            source,
        ),
        _action_rule(
            "index_ma10_break",
            "大盘10日线清仓",
            rules.get("index_ma10_break_enabled"),
            {
                "metric": "index_price",
                "operator": "<",
                "threshold": {"type": "moving_average", "scope": "index", "period": 10},
            },
            {"type": "clear_position", "reason": "index_ma_break"},
            source,
        ),
        _action_rule(
            "trailing_profit",
            "阶梯移动止盈",
            rules.get("trailing_profit_enabled"),
            {
                "metric": "peak_profit_pct",
                "operator": ">=",
                "threshold": {
                    "type": "tiered_percent",
                    "tiers": [
                        {
                            "trigger_pct": float(tier.get("profit_pct", 0.0)),
                            "lock_pct": float(tier.get("lock_pct", 0.0)),
                        }
                        for tier in rules.get("trailing_tiers", [])
                    ],
                    "skip_raise_on_volume_drop": bool(rules.get("skip_raise_on_volume_drop")),
                },
            },
            {"type": "update_stop_line", "line": "take_profit"},
            source,
        ),
        _action_rule(
            "reduce_half",
            "盈利减半仓",
            rules.get("reduce_half_enabled"),
            {
                "metric": "profit_pct",
                "operator": ">=",
                "threshold": {"type": "percent", "value": float(rules.get("reduce_half_profit_pct", 0.0))},
            },
            {"type": "reduce_position", "ratio": 0.5, "reason": "profit_target"},
            source,
        ),
        _action_rule(
            "position_cap",
            "单票仓位上限",
            True,
            {
                "metric": "position_pct",
                "operator": "<=",
                "threshold": {"type": "percent", "value": float(rules.get("max_position_pct", 0.0))},
            },
            {"type": "limit_position", "reason": "position_cap"},
            source,
        ),
        _action_rule(
            "block_heavy_on_index_ma5_down",
            "大盘5日线向下禁开重仓",
            rules.get("block_heavy_position_on_index_ma5_down"),
            {
                "metric": "index_ma_trend",
                "operator": "is",
                "threshold": {"type": "trend", "scope": "index", "period": 5, "value": "down"},
            },
            {"type": "block_open", "reason": "index_ma_down"},
            source,
        ),
        _action_rule(
            "stale_position",
            "持仓天数清仓",
            rules.get("stale_position_enabled"),
            {
                "metric": "holding_days",
                "operator": ">=",
                "threshold": {"type": "days", "value": int(rules.get("stale_position_days", 0))},
            },
            {"type": "clear_position", "reason": "stale_position"},
            source,
        ),
    ]


def strategy_action_rules_for_position(config, position):
    config = normalize_strategy_alert_config(config)
    strategy_id = str((position or {}).get("strategy_id") or "").strip()
    for profile in config.get("strategy_profiles", []):
        if profile.get("id") != strategy_id:
            continue
        action_rules = profile.get("action_rules") if isinstance(profile.get("action_rules"), list) else []
        if action_rules:
            resolved = []
            for rule in action_rules:
                if not isinstance(rule, dict):
                    continue
                item = normalize_strategy_action_rule(rule)
                item["source"] = "resolved"
                resolved.append(item)
            return resolved
    return strategy_action_rules_from_rules(strategy_rules_for_position(config, position), "resolved")


def strategy_rules_for_position(config, position):
    config = normalize_strategy_alert_config(config)
    base_rules = config["rules"]
    strategy_id = str((position or {}).get("strategy_id") or "").strip()
    profile_rules = None
    for profile in config.get("strategy_profiles", []):
        if profile.get("id") == strategy_id:
            profile_rules = profile.get("rules")
            break
    rules = dict(base_rules)
    rules.update(profile_rules or {})
    # Legacy per-position rules remain as a migration override.
    rules.update((position or {}).get("rules") or {})
    return _normalize_strategy_rules(rules, base_rules)


def normalize_strategy_alert_config(config):
    if not isinstance(config, dict):
        config = {}
    default_rules = DEFAULT_STRATEGY_ALERT_CONFIG["rules"]
    default_notifications = DEFAULT_STRATEGY_ALERT_CONFIG["notifications"]
    source_rules = config.get("rules") if isinstance(config.get("rules"), dict) else {}
    source_notifications = config.get("notifications") if isinstance(config.get("notifications"), dict) else {}
    normalized_rules = _normalize_strategy_rules(source_rules, default_rules)
    positions = []
    seen_codes = set()
    raw_positions = config.get("positions", []) if isinstance(config.get("positions"), list) else []
    for item in raw_positions:
        position = normalize_strategy_position(item)
        if not position or position["code"] in seen_codes:
            continue
        seen_codes.add(position["code"])
        positions.append(position)
    # Do not silently erase user data when an older/unknown position format is encountered.
    if raw_positions and not positions:
        positions = [dict(item) for item in raw_positions if isinstance(item, dict)]

    profiles = []
    raw_profiles = config.get("strategy_profiles")
    if isinstance(raw_profiles, dict):
        raw_profiles = [dict(value, id=key) for key, value in raw_profiles.items() if isinstance(value, dict)]
    if not isinstance(raw_profiles, list):
        raw_profiles = []
    seen_profile_ids = set()
    for raw_profile in raw_profiles:
        if not isinstance(raw_profile, dict):
            continue
        profile_id = str(raw_profile.get("id") or raw_profile.get("name") or "").strip()
        if not profile_id or profile_id in seen_profile_ids:
            continue
        seen_profile_ids.add(profile_id)
        profile_action_rules = raw_profile.get("action_rules") if isinstance(raw_profile.get("action_rules"), list) else []
        strategy_type = str(raw_profile.get("strategy_type") or "legacy").strip() or "legacy"
        turtle_params = _normalize_turtle_params(raw_profile.get("turtle_params")) if strategy_type == "turtle" else {}
        if strategy_type == "turtle" and not profile_action_rules:
            profile_action_rules = default_turtle_action_rules(turtle_params)
        profiles.append({
            "id": profile_id,
            "name": str(raw_profile.get("name") or profile_id).strip(),
            "desc": str(raw_profile.get("desc") or "").strip(),
            "strategy_type": strategy_type,
            "turtle_params": turtle_params,
            "rules": _normalize_strategy_rules(raw_profile.get("rules"), normalized_rules),
            "action_rules": [normalize_strategy_action_rule(rule) for rule in profile_action_rules if isinstance(rule, dict)],
        })

    if not profiles:
        profiles.append({"id": "default", "name": "默认策略", "rules": dict(normalized_rules)})
    builtin_profiles = default_strategy_profiles(normalized_rules)
    profile_ids = {profile["id"] for profile in profiles}
    for builtin in builtin_profiles:
        if builtin["id"] not in profile_ids:
            profiles.append(builtin)
            profile_ids.add(builtin["id"])

    profile_ids = {profile["id"] for profile in profiles}
    migrated_positions = []
    for position in positions:
        item = dict(position)
        if not item.get("strategy_id"):
            if item.get("rules"):
                profile_id = f"stock:{item['code']}"
                if profile_id not in profile_ids:
                    profiles.append({
                        "id": profile_id,
                        "name": f"{item['code']} 专属策略",
                        "rules": _normalize_strategy_rules(item.get("rules"), normalized_rules),
                    })
                    profile_ids.add(profile_id)
                item["strategy_id"] = profile_id
            else:
                item["strategy_id"] = "default"
        migrated_positions.append(item)

    return {
        "enabled": bool(config.get("enabled", DEFAULT_STRATEGY_ALERT_CONFIG["enabled"])),
        "rule_schema_version": STRATEGY_ACTION_RULE_SCHEMA_VERSION,
        "action_rules": strategy_action_rules_from_rules(normalized_rules),
        "positions": migrated_positions,
        "strategy_profiles": profiles,
        "notifications": {
            "desktop_popup": bool(source_notifications.get("desktop_popup", default_notifications["desktop_popup"])),
            "panel_highlight": bool(source_notifications.get("panel_highlight", default_notifications["panel_highlight"])),
            "remote_push": bool(source_notifications.get("remote_push", default_notifications["remote_push"])),
            "remote_channel": source_notifications.get("remote_channel") if source_notifications.get("remote_channel") in ("wecom", "custom") else default_notifications["remote_channel"],
            "webhook_url": str(source_notifications.get("webhook_url") or "").strip(),
            "daily_summary_time": _normalize_time_text(source_notifications.get("daily_summary_time"), default_notifications["daily_summary_time"]),
            "push_cooldown_minutes": _bounded_int(source_notifications.get("push_cooldown_minutes"), default_notifications["push_cooldown_minutes"], 1, 1440),
        },
        "rules": normalized_rules,
    }


def strategy_request_codes(config):
    config = normalize_strategy_alert_config(config)
    return normalize_codes(position.get("code") for position in config.get("positions", []))


def strategy_daily_request_codes(config):
    config = normalize_strategy_alert_config(config)
    codes = strategy_request_codes(config)
    rules_list = [config.get("rules", {})]
    for position in config.get("positions", []):
        rules_list.append(strategy_rules_for_position(config, position))
    if any(
        rules.get("index_ma5_break_enabled")
        or rules.get("index_ma10_break_enabled")
        or rules.get("block_heavy_position_on_index_ma5_down")
        for rules in rules_list
    ):
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


def strategy_stop_price(cost, rules, locked_profit_pct):
    try:
        cost = float(cost)
    except Exception:
        cost = 0.0
    if cost <= 0:
        return None

    stop_prices = []
    try:
        locked_profit_pct = float(locked_profit_pct)
    except Exception:
        locked_profit_pct = 0.0
    if locked_profit_pct > 0:
        stop_prices.append(cost * (1.0 + locked_profit_pct / 100.0))
    if (rules or {}).get("max_loss_enabled"):
        try:
            max_loss_pct = float((rules or {}).get("max_loss_pct", 0.0))
        except Exception:
            max_loss_pct = 0.0
        if max_loss_pct > 0:
            stop_prices.append(cost * (1.0 - max_loss_pct / 100.0))
    if not stop_prices:
        return None
    return round(max(stop_prices), 4)


def strategy_loss_price(cost, rules):
    try:
        cost = float(cost)
    except Exception:
        cost = 0.0
    if cost <= 0 or not (rules or {}).get("max_loss_enabled"):
        return None
    try:
        max_loss_pct = float((rules or {}).get("max_loss_pct", 0.0))
    except Exception:
        max_loss_pct = 0.0
    if max_loss_pct <= 0:
        return None
    return round(cost * (1.0 - max_loss_pct / 100.0), 4)


def strategy_take_profit_price(cost, locked_profit_pct):
    try:
        cost = float(cost)
        locked_profit_pct = float(locked_profit_pct)
    except Exception:
        return None
    if cost <= 0 or locked_profit_pct <= 0:
        return None
    return round(cost * (1.0 + locked_profit_pct / 100.0), 4)


def strategy_enabled_rule_labels(rules):
    rules = rules or {}
    labels = []
    if rules.get("max_loss_enabled"):
        labels.append("止损")
    if rules.get("stock_ma5_break_enabled"):
        labels.append("个股MA5")
    if rules.get("index_ma5_break_enabled"):
        labels.append("大盘MA5")
    if rules.get("index_ma10_break_enabled"):
        labels.append("大盘MA10")
    if rules.get("trailing_profit_enabled"):
        labels.append("移动止盈")
    if rules.get("reduce_half_enabled"):
        labels.append("减半仓")
    if rules.get("block_heavy_position_on_index_ma5_down"):
        labels.append("限重仓")
    if rules.get("stale_position_enabled"):
        labels.append("持仓天数")
    return labels


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


def daily_meta(daily_rows):
    if not isinstance(daily_rows, list) or not daily_rows:
        return "", False
    for row in reversed(daily_rows):
        if not isinstance(row, dict):
            continue
        date_text = str(row.get("date") or "").strip()
        if date_text:
            return date_text, bool(row.get("realtime"))
    return "", False


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
        item["lock_raised"] = False
        item["stop_line_changed"] = False
        item["stop_line_previous_price"] = 0.0
        position_rules = strategy_rules_for_position(config, item)
        quote = (quotes or {}).get(item["code"]) or {}
        cost = float(item.get("cost_price", 0.0))
        try:
            price = float(quote.get("price", 0.0))
        except Exception:
            price = 0.0
        if cost > 0 and price > 0:
            profit_pct = round((price / cost - 1.0) * 100.0, 4)
            peak_pct = max(float(item.get("peak_profit_pct", 0.0)), profit_pct)
            lock_pct = max(float(item.get("locked_profit_pct", 0.0)), trailing_lock_pct(position_rules, peak_pct))
            if abs(peak_pct - float(item.get("peak_profit_pct", 0.0))) > 0.0001:
                item["peak_profit_pct"] = round(peak_pct, 4)
                changed = True
            if abs(lock_pct - float(item.get("locked_profit_pct", 0.0))) > 0.0001:
                item["locked_profit_pct"] = round(lock_pct, 4)
                item["lock_raised"] = True
                changed = True
            stop_price = strategy_stop_price(cost, position_rules, item.get("locked_profit_pct", 0.0))
            previous_stop_price = float(item.get("last_stop_price", 0.0))
            if stop_price is not None:
                if previous_stop_price > 0 and abs(stop_price - previous_stop_price) > 0.0001:
                    item["stop_line_changed"] = True
                    item["stop_line_previous_price"] = round(previous_stop_price, 4)
                    changed = True
                if abs(stop_price - previous_stop_price) > 0.0001:
                    item["last_stop_price"] = round(stop_price, 4)
                    changed = True
        positions.append(item)
    config["positions"] = positions
    return config, changed


def _strategy_index_status(rules, quotes, daily_by_code):
    breaks = []
    errors = []
    for enabled, days in ((rules.get("index_ma5_break_enabled"), 5), (rules.get("index_ma10_break_enabled"), 10)):
        if not enabled:
            continue
        for index_code, label in (("sh000001", "上证"), ("sz399001", "深成")):
            error_text = daily_error_text(daily_by_code.get(index_code))
            if error_text:
                item = f"{label}{error_text}"
                if item not in errors:
                    errors.append(item)
                continue
            index_quote = (quotes or {}).get(index_code) or {}
            try:
                index_price = float(index_quote.get("price", 0.0))
            except Exception:
                index_price = 0.0
            average = moving_average(daily_by_code.get(index_code), days)
            if index_price > 0 and average and index_price < average:
                breaks.append(f"{label}破{days}日线")
    return breaks, errors


def _strategy_action(rule, position, stock_name, action_type=None, severity="warning", message="", details=None):
    return {
        "rule_id": rule.get("id", ""),
        "rule_name": rule.get("name", ""),
        "action_type": action_type or (rule.get("action") or {}).get("type", ""),
        "severity": severity,
        "stock_code": position.get("code", ""),
        "stock_name": stock_name,
        "message": message,
        "details": details or {},
    }


def _strategy_rule_by_id(config, position):
    return {rule.get("id"): rule for rule in strategy_action_rules_for_position(config, position)}


def evaluate_strategy_actions(config, position, quote, daily_by_code=None, context=None):
    config = normalize_strategy_alert_config(config)
    if not config.get("enabled") or not isinstance(position, dict):
        return []
    rules = strategy_rules_for_position(config, position)
    action_rules = _strategy_rule_by_id(config, position)
    daily_by_code = daily_by_code or {}
    context = context or {}
    stock_name = str((quote or {}).get("name") or position.get("code") or "")
    try:
        cost = float(position.get("cost_price", 0.0))
        price = float((quote or {}).get("price", 0.0))
    except Exception:
        cost = 0.0
        price = 0.0
    if cost <= 0 or price <= 0:
        return []

    actions = []
    profit_pct = round((price / cost - 1.0) * 100.0, 4)
    lock_pct = float(position.get("locked_profit_pct", 0.0))

    max_loss_rule = action_rules.get("max_loss")
    if max_loss_rule and max_loss_rule.get("enabled") and profit_pct <= -float(rules.get("max_loss_pct", 0.0)):
        actions.append(_strategy_action(
            max_loss_rule,
            position,
            stock_name,
            severity="danger",
            message="触发浮亏清仓",
            details={
                "profit_pct": profit_pct,
                "threshold_pct": -float(rules.get("max_loss_pct", 0.0)),
                "stop_loss_price": strategy_loss_price(cost, rules),
            },
        ))

    trailing_rule = action_rules.get("trailing_profit")
    if trailing_rule and trailing_rule.get("enabled") and lock_pct > 0:
        stop_price = strategy_stop_price(cost, rules, lock_pct)
        if (position.get("lock_raised") or position.get("stop_line_changed")) and stop_price is not None:
            actions.append(_strategy_action(
                trailing_rule,
                position,
                stock_name,
                action_type="update_stop_line",
                severity="warning",
                message="止盈线变化",
                details={
                    "locked_profit_pct": lock_pct,
                    "stop_price": stop_price,
                    "previous_stop_price": float(position.get("stop_line_previous_price", 0.0)),
                    "lock_raised": bool(position.get("lock_raised", False)),
                },
            ))
        if profit_pct <= lock_pct:
            actions.append(_strategy_action(
                trailing_rule,
                position,
                stock_name,
                action_type="clear_position",
                severity="danger",
                message="触发锁盈清仓",
                details={
                    "profit_pct": profit_pct,
                    "locked_profit_pct": lock_pct,
                    "take_profit_price": strategy_take_profit_price(cost, lock_pct),
                    "stop_price": stop_price,
                },
            ))

    reduce_rule = action_rules.get("reduce_half")
    if reduce_rule and reduce_rule.get("enabled") and profit_pct >= float(rules.get("reduce_half_profit_pct", 0.0)):
        actions.append(_strategy_action(
            reduce_rule,
            position,
            stock_name,
            severity="warning",
            message="盈利达到减半仓阈值",
            details={
                "profit_pct": profit_pct,
                "threshold_pct": float(rules.get("reduce_half_profit_pct", 0.0)),
            },
        ))

    stock_ma_rule = action_rules.get("stock_ma5_break")
    if stock_ma_rule and stock_ma_rule.get("enabled"):
        stock_ma5 = moving_average(daily_by_code.get(position.get("code")), 5)
        if stock_ma5 is not None and price < stock_ma5:
            actions.append(_strategy_action(
                stock_ma_rule,
                position,
                stock_name,
                severity="danger",
                message="个股跌破5日线",
                details={"price": price, "ma": round(stock_ma5, 4), "period": 5},
            ))

    for rule_id, period in (("index_ma5_break", 5), ("index_ma10_break", 10)):
        index_rule = action_rules.get(rule_id)
        if not index_rule or not index_rule.get("enabled"):
            continue
        for index_code in ("sh000001", "sz399001"):
            index_quote = (context.get("quotes") or {}).get(index_code) or {}
            try:
                index_price = float(index_quote.get("price", 0.0))
            except Exception:
                index_price = 0.0
            index_ma = moving_average(daily_by_code.get(index_code), period)
            if index_price > 0 and index_ma and index_price < index_ma:
                actions.append(_strategy_action(
                    index_rule,
                    position,
                    stock_name,
                    severity="danger",
                    message=f"大盘跌破{period}日线",
                    details={
                        "index_code": index_code,
                        "index_price": index_price,
                        "ma": round(index_ma, 4),
                        "period": period,
                    },
                ))

    block_rule = action_rules.get("block_heavy_on_index_ma5_down")
    if block_rule and block_rule.get("enabled") and bool(context.get("index_ma5_down")):
        actions.append(_strategy_action(
            block_rule,
            position,
            stock_name,
            action_type="block_open",
            severity="warning",
            message="大盘5日线向下，禁止新开重仓",
            details={"period": 5},
        ))

    return actions


def evaluate_strategy_alerts(config, quotes, daily_by_code=None):
    config = normalize_strategy_alert_config(config)
    if not config.get("enabled"):
        return []
    rules = config["rules"]
    daily_by_code = daily_by_code or {}
    index_ma5_down = any(ma_is_down(daily_by_code.get(code), 5) for code in ("sh000001", "sz399001"))

    states = []
    for position in config.get("positions", []):
        rules = strategy_rules_for_position(config, position)
        index_breaks, index_daily_errors = _strategy_index_status(rules, quotes, daily_by_code)
        quote = (quotes or {}).get(position["code"]) or {}
        name = str(quote.get("name") or position["code"])
        cost = float(position.get("cost_price", 0.0))
        try:
            price = float(quote.get("price", 0.0))
        except Exception:
            price = 0.0
        lock_pct = float(position.get("locked_profit_pct", 0.0))
        daily_rows = daily_by_code.get(position["code"])
        daily_date, daily_realtime = daily_meta(daily_rows)
        stock_ma5 = moving_average(daily_rows, 5)
        stock_ma10 = moving_average(daily_rows, 10)
        stock_ma20 = moving_average(daily_rows, 20)
        if cost <= 0 or price <= 0:
            states.append({
                "code": position["code"],
                "name": name,
                "profit_pct": None,
                "locked_profit_pct": lock_pct,
                "lock_raised": bool(position.get("lock_raised", False)),
                "stop_line_changed": bool(position.get("stop_line_changed", False)),
                "stop_line_previous_price": float(position.get("stop_line_previous_price", 0.0)),
                "stop_price": strategy_stop_price(cost, rules, lock_pct),
                "stop_loss_price": strategy_loss_price(cost, rules),
                "take_profit_price": strategy_take_profit_price(cost, lock_pct),
                "ma5": None if stock_ma5 is None else round(stock_ma5, 4),
                "ma10": None if stock_ma10 is None else round(stock_ma10, 4),
                "ma20": None if stock_ma20 is None else round(stock_ma20, 4),
                "daily_date": daily_date,
                "daily_realtime": daily_realtime,
                "enabled_rules": strategy_enabled_rule_labels(rules),
                "triggered_actions": [],
                "triggered": False,
                "severity": "neutral",
                "status": "等待价格",
            })
            continue

        profit_pct = round((price / cost - 1.0) * 100.0, 4)
        status_parts = []
        triggered = False
        severity = "neutral"
        if rules.get("max_loss_enabled") and profit_pct <= -float(rules.get("max_loss_pct", 0.0)):
            status_parts.append("触发止损")
            triggered = True
            severity = "danger"
        if lock_pct > 0:
            stop_price = strategy_stop_price(cost, rules, lock_pct)
            stop_line_changed = bool(position.get("stop_line_changed", False))
            if (position.get("lock_raised") or stop_line_changed) and stop_price is not None:
                if position.get("lock_raised"):
                    status_parts.append(f"上调止盈线至{stop_price:.2f}")
                else:
                    status_parts.append(f"止盈线变动至{stop_price:.2f}")
                triggered = True
                if severity != "danger":
                    severity = "warning"
            if profit_pct <= lock_pct:
                status_parts.append(f"触发锁盈{lock_pct:.0f}%（止盈价{stop_price:.2f}）" if stop_price is not None else f"触发锁盈{lock_pct:.0f}%")
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
            error_text = daily_error_text(daily_rows)
            if error_text:
                status_parts.append(error_text)
            elif stock_ma5 is None:
                status_parts.append("个股日线不足")
            elif price < stock_ma5:
                status_parts.append("个股破5日线清仓")
                triggered = True
                severity = "danger"
        if index_breaks:
            status_parts.append("大盘" + "/".join(index_breaks) + "清仓")
            triggered = True
            severity = "danger"
        elif index_daily_errors:
            status_parts.append("大盘" + "/".join(index_daily_errors))
        if rules.get("block_heavy_position_on_index_ma5_down") and index_ma5_down:
            status_parts.append("大盘5日线向下")
        if not status_parts:
            status_parts.append("未触发")

        triggered_actions = evaluate_strategy_actions(
            config,
            position,
            quote,
            daily_by_code,
            {"quotes": quotes or {}, "index_ma5_down": index_ma5_down},
        )

        states.append({
            "code": position["code"],
            "name": name,
            "profit_pct": profit_pct,
            "locked_profit_pct": lock_pct,
            "lock_raised": bool(position.get("lock_raised", False)),
            "stop_line_changed": bool(position.get("stop_line_changed", False)),
            "stop_line_previous_price": float(position.get("stop_line_previous_price", 0.0)),
            "stop_price": strategy_stop_price(cost, rules, lock_pct),
            "stop_loss_price": strategy_loss_price(cost, rules),
            "take_profit_price": strategy_take_profit_price(cost, lock_pct),
            "ma5": None if stock_ma5 is None else round(stock_ma5, 4),
            "ma10": None if stock_ma10 is None else round(stock_ma10, 4),
            "ma20": None if stock_ma20 is None else round(stock_ma20, 4),
            "daily_date": daily_date,
            "daily_realtime": daily_realtime,
            "enabled_rules": strategy_enabled_rule_labels(rules),
            "triggered_actions": triggered_actions,
            "triggered": triggered,
            "severity": severity,
            "status": "，".join(status_parts),
        })
    return states
