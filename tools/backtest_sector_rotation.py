# -*- coding: utf-8 -*-
"""Compare short-term sector rotation confirmations after a low-crowding event."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from tools.backtest_sector_crowding import BENCHMARK, SECTORS, calculate_crowding, fetch_daily
except ModuleNotFoundError:
    from backtest_sector_crowding import BENCHMARK, SECTORS, calculate_crowding, fetch_daily


HORIZONS = (1, 3, 5, 10)
LAUNCH_THRESHOLDS = {1: 0.02, 3: 0.03, 5: 0.05, 10: 0.08}
ROTATION_VARIANTS = {
    "market_baseline": "普通时期基准",
    "low_entry": "进入相对低位",
    "relative_strength_1": "单日相对大盘转强",
    "relative_strength_3": "3日相对大盘转强",
    "breakout_5": "突破前5日高点",
    "volume_reversal": "放量上涨反转",
    "balanced": "突破与相对强度组合",
}


def add_rotation_features(frame: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    benchmark_close = benchmark.set_index("date")["close"].sort_index()
    aligned_benchmark = benchmark_close.reindex(result["date"], method="ffill").to_numpy()
    benchmark_series = pd.Series(aligned_benchmark, index=result.index)

    result["ma5"] = result["close"].rolling(5).mean()
    result["previous_high_5"] = result["close"].shift(1).rolling(5).max()
    result["volume_ratio_20"] = result["volume"] / result["volume"].rolling(20).mean()
    result["daily_return"] = result["close"].pct_change()
    result["benchmark_daily_return"] = benchmark_series.pct_change()
    result["relative_strength_1"] = result["daily_return"] - result["benchmark_daily_return"]
    result["relative_strength_3"] = (
        result["close"].pct_change(3) - benchmark_series.pct_change(3)
    )
    result["recent_low"] = (
        result["crowding"].rolling(10, min_periods=1).min().le(20.0)
        & result["crowding"].notna()
    )
    return result


def _low_event_indices(frame: pd.DataFrame, threshold: float = 20.0, cooldown: int = 10) -> list[int]:
    low = frame["crowding"].le(threshold)
    crossings = frame.index[low & ~low.shift(1, fill_value=False)].tolist()
    selected: list[int] = []
    for index in crossings:
        if not selected or index - selected[-1] >= cooldown:
            selected.append(int(index))
    return selected


def select_rotation_signals(
    frame: pd.DataFrame,
    variant: str,
    max_wait: int = 10,
    cooldown: int = 10,
) -> list[int]:
    if variant not in ROTATION_VARIANTS:
        raise ValueError(f"Unknown rotation variant: {variant}")
    if variant == "market_baseline":
        valid = frame.index[frame["crowding"].notna()].tolist()
        selected = []
        for index in valid:
            if not selected or index - selected[-1] >= cooldown:
                selected.append(int(index))
        return selected
    events = _low_event_indices(frame, cooldown=cooldown)
    if variant == "low_entry":
        return events

    selected: list[int] = []
    for start in events:
        stop = min(len(frame) - 1, start + max_wait)
        for index in range(start, stop + 1):
            if not bool(frame.at[index, "recent_low"]):
                continue
            above_ma5 = pd.notna(frame.at[index, "ma5"]) and frame.at[index, "close"] > frame.at[index, "ma5"]
            if variant == "relative_strength_1":
                confirmed = above_ma5 and frame.at[index, "relative_strength_1"] >= 0.01
            elif variant == "relative_strength_3":
                confirmed = above_ma5 and frame.at[index, "relative_strength_3"] >= 0.02
            elif variant == "breakout_5":
                confirmed = (
                    pd.notna(frame.at[index, "previous_high_5"])
                    and frame.at[index, "close"] > frame.at[index, "previous_high_5"]
                )
            elif variant == "volume_reversal":
                confirmed = (
                    above_ma5
                    and frame.at[index, "daily_return"] >= 0.02
                    and frame.at[index, "volume_ratio_20"] >= 1.20
                )
            else:
                confirmed = (
                    pd.notna(frame.at[index, "previous_high_5"])
                    and frame.at[index, "close"] > frame.at[index, "previous_high_5"]
                    and frame.at[index, "relative_strength_3"] > 0.0
                    and frame.at[index, "volume_ratio_20"] >= 1.0
                )
            if confirmed:
                if not selected or index - selected[-1] >= cooldown:
                    selected.append(int(index))
                break
    return selected


def _rate(values: list[float], predicate) -> float | None:
    if not values:
        return None
    return 100.0 * sum(1 for value in values if predicate(value)) / len(values)


def _median(values: list[float]) -> float | None:
    return float(np.median(values)) if values else None


def evaluate_short_term(
    frame: pd.DataFrame,
    benchmark: pd.DataFrame,
    signal_indices: list[int],
    horizons: tuple[int, ...] = HORIZONS,
) -> dict:
    benchmark_by_date = benchmark.set_index("date")["close"]
    results = {}
    for horizon in horizons:
        end_returns: list[float] = []
        excess_returns: list[float] = []
        max_gains: list[float] = []
        adverse_moves: list[float] = []
        for index in signal_indices:
            end_index = index + horizon
            if end_index >= len(frame):
                continue
            signal_date = frame.at[index, "date"]
            end_date = frame.at[end_index, "date"]
            if signal_date not in benchmark_by_date.index or end_date not in benchmark_by_date.index:
                continue
            reference = float(frame.at[index, "close"])
            future = frame.loc[index + 1:end_index, "close"]
            end_return = float(frame.at[end_index, "close"]) / reference - 1.0
            benchmark_return = (
                float(benchmark_by_date.at[end_date]) / float(benchmark_by_date.at[signal_date]) - 1.0
            )
            end_returns.append(end_return)
            excess_returns.append(end_return - benchmark_return)
            max_gains.append(float(future.max()) / reference - 1.0)
            adverse_moves.append(float(future.min()) / reference - 1.0)

        threshold = LAUNCH_THRESHOLDS.get(horizon, 0.0)
        results[str(horizon)] = {
            "samples": len(end_returns),
            "positive_end_rate_pct": _rate(end_returns, lambda value: value > 0.0),
            "median_end_return_pct": None if not end_returns else 100.0 * _median(end_returns),
            "median_excess_return_pct": None if not excess_returns else 100.0 * _median(excess_returns),
            "launch_threshold_pct": 100.0 * threshold,
            "launch_rate_pct": _rate(max_gains, lambda value: value >= threshold),
            "median_max_gain_pct": None if not max_gains else 100.0 * _median(max_gains),
            "median_max_adverse_pct": None if not adverse_moves else 100.0 * _median(adverse_moves),
        }
    return results


def _format(value) -> str:
    return "-" if value is None else f"{value:.1f}%"


def build_report(all_results: dict, generated_date: str) -> str:
    lines = [
        "# 板块低位后短期启动回测",
        "",
        f"数据更新至：{generated_date}",
        "",
        "## 统一口径",
        "",
        "- 数据：中证与国证官方指数日线；未使用同花顺。",
        "- 候选：拥挤度首次进入0-20区间，随后最多等待10个交易日确认启动。",
        "- 去重：同一方案的实际确认信号至少间隔10个交易日。",
        "- 统计：以确认日收盘为基准，观察之后1/3/5/10日，不把信号当天涨幅算入结果。",
        "- 启动：未来1/3/5/10日内最高收盘分别达到+2%/+3%/+5%/+8%。",
        "- 用途：衡量日线信号的后续启动概率，不等同于可成交的盘中策略收益。",
        "",
        "## 3日与5日对比",
        "",
        "| 板块 | 条件 | 信号 | 3日启动率 | 3日超额中位数 | 3日不利波动 | 5日启动率 | 5日超额中位数 |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in all_results.items():
        for key, variant in item["variants"].items():
            h3, h5 = variant["horizons"]["3"], variant["horizons"]["5"]
            lines.append(
                f"| {name} | {ROTATION_VARIANTS[key]} | {variant['signals']} | "
                f"{_format(h3['launch_rate_pct'])} ({h3['samples']}) | "
                f"{_format(h3['median_excess_return_pct'])} | {_format(h3['median_max_adverse_pct'])} | "
                f"{_format(h5['launch_rate_pct'])} ({h5['samples']}) | "
                f"{_format(h5['median_excess_return_pct'])} |"
            )
    lines.extend(["", "## 当前判读", ""])
    for name, item in all_results.items():
        variants = item["variants"]
        baseline_3 = variants["market_baseline"]["horizons"]["3"]
        baseline_5 = variants["market_baseline"]["horizons"]["5"]
        low_3 = variants["low_entry"]["horizons"]["3"]
        low_5 = variants["low_entry"]["horizons"]["5"]
        delta_3 = low_3["launch_rate_pct"] - baseline_3["launch_rate_pct"]
        delta_5 = low_5["launch_rate_pct"] - baseline_5["launch_rate_pct"]
        candidates = []
        baseline_excess = baseline_3["median_excess_return_pct"]
        for key, variant in variants.items():
            if key in ("market_baseline", "low_entry"):
                continue
            h3 = variant["horizons"]["3"]
            if (
                h3["samples"] >= 20
                and h3["median_excess_return_pct"] is not None
                and h3["median_excess_return_pct"] > 0.0
                and h3["median_excess_return_pct"] >= baseline_excess + 0.2
            ):
                candidates.append(
                    f"{ROTATION_VARIANTS[key]}（3日超额中位数{h3['median_excess_return_pct']:.1f}%）"
                )
        candidate_text = "；可继续验证：" + "、".join(candidates) if candidates else "；暂无可靠的3日确认条件"
        lines.append(
            f"- {name}：低位相对普通时期的3日启动率变化{delta_3:+.1f}个百分点，"
            f"5日变化{delta_5:+.1f}个百分点{candidate_text}。"
        )
    lines.extend([
        "",
        "## 判断限制",
        "",
        "- 只有四个板块，无法可靠计算全市场前20%涨速或上涨家数，这两项需要更完整的板块池和分钟数据。",
        "- 日线只能验证低位后是否较快启动，无法证明盘中哪个时刻适合买入。",
        "- 各方案共享大量相同市场阶段，结果不能视为完全独立样本。",
        "- 化工和有色仍需商品价格、库存或价差等周期变量；价格确认只能作为辅助。",
    ])
    return "\n".join(lines) + "\n"


def run(output_dir: Path, cache_dir: Path) -> dict:
    benchmark = fetch_daily(BENCHMARK[1], BENCHMARK[2], cache_dir / "benchmark.json")
    all_results = {}
    for name, (provider, code) in SECTORS.items():
        frame = fetch_daily(provider, code, cache_dir / f"{provider}_{code}.json")
        scored = add_rotation_features(calculate_crowding(frame), benchmark)
        variants = {}
        for key in ROTATION_VARIANTS:
            signals = select_rotation_signals(scored, key)
            variants[key] = {
                "signals": len(signals),
                "signal_dates": [scored.at[index, "date"].strftime("%Y-%m-%d") for index in signals],
                "horizons": evaluate_short_term(scored, benchmark, signals),
            }
        all_results[name] = {
            "provider": provider,
            "code": code,
            "start": frame["date"].min().strftime("%Y-%m-%d"),
            "end": frame["date"].max().strftime("%Y-%m-%d"),
            "rows": len(frame),
            "variants": variants,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "sector_rotation_results.json").write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    latest_date = benchmark["date"].max().strftime("%Y-%m-%d")
    (output_dir / "sector_rotation_report.md").write_text(
        build_report(all_results, latest_date), encoding="utf-8"
    )
    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest short-term sector rotation confirmations")
    parser.add_argument("--output-dir", default="backtests/sector_rotation")
    parser.add_argument("--cache-dir", default="backtests/sector_crowding/cache")
    args = parser.parse_args()
    print(json.dumps(run(Path(args.output_dir), Path(args.cache_dir)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
