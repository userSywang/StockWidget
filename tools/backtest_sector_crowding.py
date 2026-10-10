# -*- coding: utf-8 -*-
"""Backtest a causal, price/volume-only sector crowding model.

This is an isolated research tool. It does not change StockWidget runtime
behaviour or strategy settings.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests


SECTORS = {
    "CPO（中证光通信）": ("csi", "931723"),
    "PCB（国证PCB）": ("cni", "980115"),
    "化工（中证细分化工）": ("csi", "000813"),
    "有色铜代理（中证工业有色）": ("csi", "H11059"),
}
BENCHMARK = ("上证指数", "csi", "000001")
HORIZONS = (20, 60, 120, 250)
FACTOR_WEIGHTS = {
    "price_percentile": 35.0,
    "momentum_percentile": 30.0,
    "volume_percentile": 20.0,
}
SIGNAL_VARIANTS = {
    "raw": "原始冰点",
    "crowding_rise_3": "拥挤度连续3日回升",
    "crowding_rise_5": "拥挤度连续5日回升",
    "ma20_reclaim": "重新站上MA20",
    "ma20_volume": "MA20与成交量确认",
    "daily_weekly": "MA20与周线MA10确认",
    "daily_weekly_market": "日周线与大盘趋势确认",
}


def _request_json(url: str, params: dict) -> dict:
    last_error = None
    for attempt in range(4):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            last_error = error
            if attempt == 3:
                raise
            time.sleep(1.0 + attempt)
    raise last_error


def _fetch_csi(code: str) -> list[dict]:
    payload = _request_json(
        "https://www.csindex.com.cn/csindex-home/perf/index-perf",
        {"indexCode": code, "startDate": "20000101", "endDate": "20500101"},
    )
    rows = []
    for item in payload.get("data") or []:
        close = item.get("close")
        if close is None:
            continue
        rows.append({
            "date": item.get("tradeDate"),
            "open": close,
            "close": close,
            "high": close,
            "low": close,
            "volume": item.get("tradingVol"),
            "amount": item.get("tradingValue"),
        })
    return rows


def _fetch_cni(code: str) -> list[dict]:
    payload = _request_json(
        "http://hq.cnindex.com.cn/market/market/getIndexDailyDataWithDataFormat",
        {
            "indexCode": code,
            "startDate": "2000-01-01",
            "endDate": "2050-01-01",
            "frequency": "day",
        },
    )
    raw_rows = (((payload.get("data") or {}).get("data")) or [])
    rows = []
    for item in raw_rows:
        if not isinstance(item, list) or len(item) < 10 or item[5] is None:
            continue
        close = item[5]
        rows.append({
            "date": str(item[0]).replace("-", ""),
            "open": item[3] if item[3] is not None else close,
            "close": close,
            "high": item[2] if item[2] is not None else close,
            "low": item[4] if item[4] is not None else close,
            "volume": item[9],
            "amount": item[8],
        })
    return rows


def fetch_daily(provider: str, code: str, cache_path: Path, refresh: bool = False) -> pd.DataFrame:
    if cache_path.exists() and not refresh:
        rows = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        rows = _fetch_csi(code) if provider == "csi" else _fetch_cni(code)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in ("open", "close", "high", "low", "volume", "amount"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["date", "open", "close", "low", "volume"])
    frame = frame[(frame["close"] > 0) & (frame["volume"] > 0)]
    frame = frame.sort_values("date").reset_index(drop=True)
    if len(frame) > 1 and (frame.at[1, "date"] - frame.at[0, "date"]).days > 365:
        frame = frame.iloc[1:].reset_index(drop=True)
    return frame


def rolling_percentile(series: pd.Series, window: int = 756, minimum: int = 252) -> pd.Series:
    def percentile(values: np.ndarray) -> float:
        current = values[-1]
        return float(np.count_nonzero(values <= current) * 100.0 / len(values))

    return series.rolling(window=window, min_periods=minimum).apply(percentile, raw=True)


def calculate_crowding(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    daily_return = result["close"].pct_change()
    return_20 = result["close"].pct_change(20)
    volatility_20 = daily_return.rolling(20).std() * math.sqrt(20)
    price_deviation = result["close"] / result["close"].rolling(60).mean() - 1.0
    risk_adjusted_momentum = return_20 / volatility_20.replace(0.0, np.nan)
    relative_volume = np.log(result["volume"] / result["volume"].rolling(20).mean())
    direction_adjusted_volume = np.sign(return_20) * relative_volume

    result["price_percentile"] = rolling_percentile(price_deviation)
    result["momentum_percentile"] = rolling_percentile(risk_adjusted_momentum)
    result["volume_percentile"] = rolling_percentile(direction_adjusted_volume)
    total_weight = sum(FACTOR_WEIGHTS.values())
    result["crowding"] = sum(
        result[column] * weight for column, weight in FACTOR_WEIGHTS.items()
    ) / total_weight
    return result


def select_signal_indices(frame: pd.DataFrame, threshold: float = 10.0, cooldown: int = 20) -> list[int]:
    below = frame["crowding"].lt(threshold)
    crossings = frame.index[below & ~below.shift(1, fill_value=False)].tolist()
    selected: list[int] = []
    for index in crossings:
        if not selected or index - selected[-1] >= cooldown:
            selected.append(int(index))
    return selected


def add_trend_features(frame: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add causal daily, completed-week and optional benchmark trend fields."""
    result = frame.copy()
    result["ma20"] = result["close"].rolling(20).mean()
    result["volume_ma20"] = (
        result["volume"].rolling(20).mean() if "volume" in result else np.nan
    )

    weekly = (
        result.set_index("date")["close"]
        .resample("W-FRI")
        .last()
        .dropna()
        .to_frame("weekly_close")
    )
    weekly["weekly_ma10"] = weekly["weekly_close"].rolling(10).mean()
    weekly["weekly_uptrend"] = (
        (weekly["weekly_close"] > weekly["weekly_ma10"])
        & (weekly["weekly_ma10"] > weekly["weekly_ma10"].shift(1))
    )
    for column in ("weekly_close", "weekly_ma10", "weekly_uptrend"):
        result[column] = weekly[column].reindex(result["date"], method="ffill").to_numpy()
    result["weekly_uptrend"] = result["weekly_uptrend"].fillna(False).astype(bool)

    result["market_uptrend"] = True
    if benchmark is not None:
        market = benchmark.set_index("date")["close"].sort_index()
        market_ma60 = market.rolling(60).mean()
        market_uptrend = (market > market_ma60) & (market_ma60 > market_ma60.shift(5))
        result["market_uptrend"] = (
            market_uptrend.reindex(result["date"], method="ffill").fillna(False).to_numpy()
        )
    return result


def select_confirmed_signal_indices(
    frame: pd.DataFrame,
    variant: str,
    threshold: float = 10.0,
    cooldown: int = 20,
    max_wait: int = 40,
) -> list[int]:
    """Confirm each ice event with information available on or before that day."""
    if variant not in SIGNAL_VARIANTS:
        raise ValueError(f"Unknown signal variant: {variant}")
    event_indices = select_signal_indices(frame, threshold=threshold, cooldown=cooldown)
    if variant == "raw":
        return event_indices

    crowding = frame["crowding"]
    selected: list[int] = []
    for start in event_indices:
        stop = min(len(frame) - 1, start + max_wait)
        confirmed = None
        for index in range(start, stop + 1):
            if variant == "crowding_rise_3":
                confirmed = index if (
                    index >= start + 3
                    and crowding.iloc[index] > crowding.iloc[index - 1]
                    and crowding.iloc[index - 1] > crowding.iloc[index - 2]
                    and crowding.iloc[index - 2] > crowding.iloc[index - 3]
                ) else None
            elif variant == "crowding_rise_5":
                confirmed = index if (
                    index >= start + 5
                    and all(
                        crowding.iloc[position] > crowding.iloc[position - 1]
                        for position in range(index - 4, index + 1)
                    )
                ) else None
            elif variant == "ma20_reclaim":
                confirmed = index if (
                    index > start
                    and pd.notna(frame.at[index, "ma20"])
                    and frame.at[index, "close"] > frame.at[index, "ma20"]
                    and frame.at[index - 1, "close"] <= frame.at[index - 1, "ma20"]
                ) else None
            elif variant == "ma20_volume":
                confirmed = index if (
                    index > start
                    and pd.notna(frame.at[index, "ma20"])
                    and pd.notna(frame.at[index, "volume_ma20"])
                    and frame.at[index, "close"] > frame.at[index, "ma20"]
                    and frame.at[index, "close"] > frame.at[index - 1, "close"]
                    and frame.at[index, "volume"] > frame.at[index, "volume_ma20"]
                ) else None
            elif variant in ("daily_weekly", "daily_weekly_market"):
                trend_ok = (
                    pd.notna(frame.at[index, "ma20"])
                    and frame.at[index, "close"] > frame.at[index, "ma20"]
                    and bool(frame.at[index, "weekly_uptrend"])
                )
                market_ok = variant == "daily_weekly" or bool(frame.at[index, "market_uptrend"])
                confirmed = index if trend_ok and market_ok else None
            if confirmed is not None:
                if not selected or confirmed - selected[-1] >= cooldown:
                    selected.append(int(confirmed))
                break
    return selected


def _rate(values: list[float], predicate) -> float | None:
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def evaluate(frame: pd.DataFrame, benchmark: pd.DataFrame, signal_indices: list[int]) -> dict:
    benchmark_by_date = benchmark.set_index("date")
    results = {}
    for horizon in HORIZONS:
        returns: list[float] = []
        excess_returns: list[float] = []
        adverse_excursions: list[float] = []
        dates: list[str] = []
        for index in signal_indices:
            entry_index = index + 1
            exit_index = index + horizon
            if exit_index >= len(frame):
                continue
            entry_date = frame.at[entry_index, "date"]
            exit_date = frame.at[exit_index, "date"]
            if entry_date not in benchmark_by_date.index or exit_date not in benchmark_by_date.index:
                continue
            entry = float(frame.at[entry_index, "close"])
            exit_price = float(frame.at[exit_index, "close"])
            sector_return = exit_price / entry - 1.0
            benchmark_entry = float(benchmark_by_date.at[entry_date, "close"])
            benchmark_exit = float(benchmark_by_date.at[exit_date, "close"])
            benchmark_return = benchmark_exit / benchmark_entry - 1.0
            minimum_low = float(frame.loc[entry_index:exit_index, "close"].min())
            returns.append(sector_return)
            excess_returns.append(sector_return - benchmark_return)
            adverse_excursions.append(minimum_low / entry - 1.0)
            dates.append(frame.at[index, "date"].strftime("%Y-%m-%d"))

        results[str(horizon)] = {
            "samples": len(returns),
            "positive_rate_pct": _rate(returns, lambda value: value > 0),
            "median_return_pct": None if not returns else 100.0 * _median(returns),
            "excess_positive_rate_pct": _rate(excess_returns, lambda value: value > 0),
            "median_excess_return_pct": None if not excess_returns else 100.0 * _median(excess_returns),
            "median_max_adverse_pct": None if not adverse_excursions else 100.0 * _median(adverse_excursions),
            "signal_dates": dates,
        }
    return results


def acceptance(result: dict) -> str:
    if any(result[horizon]["samples"] == 0 for horizon in ("120", "250")):
        return "无可评估样本"
    enough_samples = True
    metric_checks = []
    for horizon in ("120", "250"):
        item = result[horizon]
        if item["samples"] < 30:
            enough_samples = False
        metric_checks.append(
            item["positive_rate_pct"] >= 65.0
            and item["median_excess_return_pct"] > 0.0
        )
    metrics_pass = all(metric_checks)
    if enough_samples:
        return "达到" if metrics_pass else "未达到"
    return "暂未验收（样本不足）" if metrics_pass else "未达到（样本亦不足）"


def format_value(value, suffix="%") -> str:
    return "-" if value is None else f"{value:.1f}{suffix}"


def build_report(all_results: dict, generated_date: str) -> str:
    lines = [
        "# 板块拥挤度局部回测",
        "",
        f"数据更新至：{generated_date}",
        "",
        "## 固定口径",
        "",
        "- 数据：中证指数官网、国证指数官网的官方指数日线；基准为上证指数。",
        "- 因子：60日价格偏离、20日风险调整动量、方向调整成交量，原权重35/30/20后归一化。",
        "- 标准化：各因子只用当时及此前最多756个交易日计算滚动百分位，至少需要252日历史。",
        "- 冰点事件：拥挤度从不低于10进入低于10；相邻事件至少间隔20个交易日。",
        "- 确认窗口：除原始冰点外，各方案须在冰点事件后40个交易日内完成确认，否则放弃该次事件。",
        "- 周线确认：只使用已经结束的周线；周收盘高于10周均线，且10周均线较前一周上升。",
        "- 成交量确认：价格位于MA20上方、当日上涨，且成交量高于20日均量。",
        "- 大盘过滤：上证指数高于60日均线，且60日均线高于5个交易日前。",
        "- 执行：为统一官方数据口径，信号后下一交易日收盘进入，在第20/60/120/250个交易日收盘评估。",
        "- 验收：120日和250日正收益率均不低于65%，超额收益中位数为正，且各至少30个独立样本。",
        "",
        "## 方案对比",
        "",
        "| 板块 | 确认方案 | 信号 | 120日正收益 | 120日超额中位数 | 120日不利波动 | 250日正收益 | 250日超额中位数 | 验收 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in all_results.items():
        for variant_key, variant in item["variants"].items():
            h120, h250 = variant["horizons"]["120"], variant["horizons"]["250"]
            lines.append(
                f"| {name} | {SIGNAL_VARIANTS[variant_key]} | {variant['signals']} | "
                f"{format_value(h120['positive_rate_pct'])} ({h120['samples']}) | "
                f"{format_value(h120['median_excess_return_pct'])} | "
                f"{format_value(h120['median_max_adverse_pct'])} | "
                f"{format_value(h250['positive_rate_pct'])} ({h250['samples']}) | "
                f"{format_value(h250['median_excess_return_pct'])} | {variant['acceptance']} |"
            )

    lines.extend(["", "## 当前判读", ""])
    for name, item in all_results.items():
        metric_passes = []
        for variant_key, variant in item["variants"].items():
            h120, h250 = variant["horizons"]["120"], variant["horizons"]["250"]
            if all(
                horizon["positive_rate_pct"] is not None
                and horizon["positive_rate_pct"] >= 65.0
                and horizon["median_excess_return_pct"] > 0.0
                for horizon in (h120, h250)
            ):
                metric_passes.append(
                    f"{SIGNAL_VARIANTS[variant_key]}（120日样本{h120['samples']}个）"
                )
        if metric_passes:
            lines.append(f"- {name}：{', '.join(metric_passes)}满足收益指标，但均未达到30个样本。")
        else:
            lines.append(f"- {name}：没有方案同时满足120日和250日收益指标。")
    lines.append("- MA20与成交量确认若与单独MA20结果接近，说明当前成交量门槛没有带来独立筛选价值。")

    lines.extend([
        "",
        "## 数据区间",
        "",
    ])
    for name, item in all_results.items():
        lines.append(f"- {name}：{item['start']} 至 {item['end']}，共{item['rows']}个交易日。")
    lines.extend([
        "",
        "## 解释限制",
        "",
        "- 这是拥挤度子模型回测，不含ERP、全市场冰点板块数量和资金净流入，不能代表完整买入系统。",
        "- CPO使用中证光通信作为可回溯代理；有色铜使用覆盖铜、铝、铅锌、稀土的中证工业有色代理，不是纯铜指数。",
        "- 同时比较七种方案会产生多重检验偏差；不能只挑历史结果最好的一组直接用于实盘。",
        "- 趋势确认会推迟入场并减少样本；若胜率提高但超额收益或不利波动没有同步改善，不算有效优化。",
        "- 指数公司可能修订编制方案，历史回溯序列不等于当时可直接投资的产品净值。",
        "- 多个方案和持有周期大量共享同一批市场阶段，不能当作相互独立的证据。",
    ])
    return "\n".join(lines) + "\n"


def run(output_dir: Path, refresh: bool = False) -> dict:
    cache_dir = output_dir / "cache"
    benchmark = fetch_daily(BENCHMARK[1], BENCHMARK[2], cache_dir / "benchmark.json", refresh)
    targets = SECTORS
    all_results = {}
    for name, (provider, code) in targets.items():
        frame = fetch_daily(provider, code, cache_dir / f"{provider}_{code}.json", refresh)
        scored = add_trend_features(calculate_crowding(frame), benchmark)
        variants = {}
        for variant_key in SIGNAL_VARIANTS:
            signal_indices = select_confirmed_signal_indices(scored, variant_key)
            horizons = evaluate(scored, benchmark, signal_indices)
            variants[variant_key] = {
                "signals": len(signal_indices),
                "horizons": horizons,
                "acceptance": acceptance(horizons),
            }
        raw = variants["raw"]
        all_results[name] = {
            "provider": provider,
            "code": code,
            "start": frame["date"].min().strftime("%Y-%m-%d"),
            "end": frame["date"].max().strftime("%Y-%m-%d"),
            "rows": len(frame),
            "signals": raw["signals"],
            "horizons": raw["horizons"],
            "acceptance": raw["acceptance"],
            "variants": variants,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    latest_date = benchmark["date"].max().strftime("%Y-%m-%d")
    (output_dir / "sector_crowding_results.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "sector_crowding_report.md").write_text(
        build_report(all_results, latest_date), encoding="utf-8"
    )
    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the sector crowding model")
    parser.add_argument("--output-dir", default="backtests/sector_crowding")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    results = run(Path(args.output_dir), refresh=args.refresh)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
