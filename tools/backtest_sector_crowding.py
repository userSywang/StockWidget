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
        "- 信号：拥挤度从不低于10进入低于10；相邻信号至少间隔20个交易日。",
        "- 执行：为统一官方数据口径，信号后下一交易日收盘进入，在第20/60/120/250个交易日收盘评估。",
        "- 验收：120日和250日正收益率均不低于65%，超额收益中位数为正，且各至少30个独立样本。",
        "",
        "## 结果",
        "",
        "| 板块 | 数据区间 | 冰点事件 | 120日正收益 | 120日超额中位数 | 250日正收益 | 250日超额中位数 | 验收 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in all_results.items():
        h120, h250 = item["horizons"]["120"], item["horizons"]["250"]
        lines.append(
            f"| {name} | {item['start']} 至 {item['end']} | {item['signals']} | "
            f"{format_value(h120['positive_rate_pct'])} ({h120['samples']}) | "
            f"{format_value(h120['median_excess_return_pct'])} | "
            f"{format_value(h250['positive_rate_pct'])} ({h250['samples']}) | "
            f"{format_value(h250['median_excess_return_pct'])} | {item['acceptance']} |"
        )

    lines.extend(["", "## 各周期明细", ""])
    for name, item in all_results.items():
        lines.extend([
            f"### {name}",
            "",
            "| 周期 | 样本 | 正收益率 | 收益中位数 | 跑赢上证比例 | 超额中位数 | 最大不利波动中位数 |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for horizon in HORIZONS:
            result = item["horizons"][str(horizon)]
            lines.append(
                f"| {horizon}日 | {result['samples']} | {format_value(result['positive_rate_pct'])} | "
                f"{format_value(result['median_return_pct'])} | {format_value(result['excess_positive_rate_pct'])} | "
                f"{format_value(result['median_excess_return_pct'])} | {format_value(result['median_max_adverse_pct'])} |"
            )
        dates = item["horizons"]["20"]["signal_dates"]
        lines.extend(["", f"信号日期：{', '.join(dates) if dates else '无'}", ""])

    lines.extend([
        "## 解释限制",
        "",
        "- 这是拥挤度子模型回测，不含ERP、全市场冰点板块数量和资金净流入，不能代表完整买入系统。",
        "- CPO使用中证光通信作为可回溯代理；有色铜使用覆盖铜、铝、铅锌、稀土的中证工业有色代理，不是纯铜指数。",
        "- 指数公司可能修订编制方案，历史回溯序列不等于当时可直接投资的产品净值。",
        "- 多个持有周期来自同一批信号，不能把它们当作相互独立的四组证据。",
    ])
    return "\n".join(lines) + "\n"


def run(output_dir: Path, refresh: bool = False) -> dict:
    cache_dir = output_dir / "cache"
    benchmark = fetch_daily(BENCHMARK[1], BENCHMARK[2], cache_dir / "benchmark.json", refresh)
    targets = SECTORS
    all_results = {}
    for name, (provider, code) in targets.items():
        frame = fetch_daily(provider, code, cache_dir / f"{provider}_{code}.json", refresh)
        scored = calculate_crowding(frame)
        signal_indices = select_signal_indices(scored)
        horizons = evaluate(scored, benchmark, signal_indices)
        all_results[name] = {
            "provider": provider,
            "code": code,
            "start": frame["date"].min().strftime("%Y-%m-%d"),
            "end": frame["date"].max().strftime("%Y-%m-%d"),
            "rows": len(frame),
            "signals": len(signal_indices),
            "horizons": horizons,
            "acceptance": acceptance(horizons),
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
