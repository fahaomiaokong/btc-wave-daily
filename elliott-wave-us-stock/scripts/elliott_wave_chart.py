#!/usr/bin/env python3
"""Generate a conditional Elliott Wave chart, Chinese post, and JSON record."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yfinance as yf


DISCLAIMER = "只分析，不建议交易"
METHOD_VERSION = "0.1.0"


@dataclass
class Pivot:
    index: int
    time: str
    price: float
    kind: str


@dataclass
class MainUpswing:
    start_index: int
    start_time: str
    start_price: float
    high_index: int
    high_time: str
    high_price: float


@dataclass
class MainImpulse:
    direction: str
    points: list[Pivot]
    rule_checks: dict[str, bool]


@dataclass
class CorrectionStructure:
    kind: str
    points: list[Pivot]
    labels: list[str]
    rule_checks: dict[str, bool]


@dataclass
class WaveLevels:
    start: float
    monitor: float
    target: float
    invalidation: float
    fib_0236: float
    fib_0382: float
    fib_0500: float
    fib_0618: float
    key_high: float
    key_low: float


@dataclass
class ImpulseAnalysis:
    direction: str
    points: list[Pivot]
    target_equal_1_5: float
    rule_checks: dict[str, bool]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", help="Yahoo Finance ticker, e.g. NVDA, PLTR, SPY, BTC-USD")
    parser.add_argument(
        "--horizon",
        choices=["auto", "short", "long", "listing"],
        default="auto",
        help="Analysis horizon: short≈1y, long≈3y for stocks/max for crypto, listing=max visible from IPO, default: auto",
    )
    parser.add_argument("--period", default=None, help="Explicit yfinance period. Overrides --horizon.")
    parser.add_argument("--interval", default="1d", help="yfinance interval, default: 1d")
    parser.add_argument("--sensitivity", type=float, default=0.06, help="ZigZag reversal threshold, default: 0.06")
    parser.add_argument("--out", default="reports", help="Output root directory")
    parser.add_argument("--name", default="", help="Optional Chinese display name")
    parser.add_argument(
        "--start-date",
        default=None,
        help="Optional visible chart start date, YYYY-MM-DD. Keeps full fetched data for wave detection.",
    )
    return parser.parse_args()


def resolve_period(symbol: str, explicit_period: str | None, horizon: str) -> str:
    if explicit_period:
        return explicit_period
    if horizon == "short":
        return "1y"
    if horizon == "long":
        return "max" if prefers_cycle_low(symbol) else "3y"
    if horizon == "listing":
        return "max"
    return "2y"


def setup_fonts() -> None:
    candidates = [
        "PingFang SC",
        "Hiragino Sans GB",
        "Songti SC",
        "Heiti SC",
        "Arial Unicode MS",
        "Noto Sans CJK SC",
        "SimHei",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            break
    plt.rcParams["axes.unicode_minus"] = False


def fetch_bars(symbol: str, period: str, interval: str) -> pd.DataFrame:
    data = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)
    if data.empty:
        raise SystemExit(f"No data returned for {symbol}. Check symbol, period, or interval.")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.dropna(subset=["High", "Low", "Close"]).copy()
    data.index = pd.to_datetime(data.index)
    return data


def detect_pivots(data: pd.DataFrame, threshold: float) -> list[Pivot]:
    highs = data["High"].to_numpy(dtype=float)
    lows = data["Low"].to_numpy(dtype=float)
    close = data["Close"].to_numpy(dtype=float)
    if len(close) < 5:
        return []

    pivots: list[Pivot] = [Pivot(0, data.index[0].isoformat(), float(lows[0]), "low")]
    mode = "seeking_high"
    candidate_idx = 0
    candidate_price = float(highs[0])

    for i in range(1, len(close)):
        if mode == "seeking_high":
            if highs[i] >= candidate_price:
                candidate_idx = i
                candidate_price = float(highs[i])
            elif candidate_price > 0 and (candidate_price - lows[i]) / candidate_price >= threshold:
                pivots.append(Pivot(candidate_idx, data.index[candidate_idx].isoformat(), candidate_price, "high"))
                mode = "seeking_low"
                candidate_idx = i
                candidate_price = float(lows[i])
        else:
            if lows[i] <= candidate_price:
                candidate_idx = i
                candidate_price = float(lows[i])
            elif candidate_price > 0 and (highs[i] - candidate_price) / candidate_price >= threshold:
                pivots.append(Pivot(candidate_idx, data.index[candidate_idx].isoformat(), candidate_price, "low"))
                mode = "seeking_high"
                candidate_idx = i
                candidate_price = float(highs[i])

    if candidate_idx != pivots[-1].index:
        last_kind = "high" if mode == "seeking_high" else "low"
        pivots.append(Pivot(candidate_idx, data.index[candidate_idx].isoformat(), candidate_price, last_kind))
    return dedupe_pivots(pivots)


def dedupe_pivots(pivots: Iterable[Pivot]) -> list[Pivot]:
    result: list[Pivot] = []
    for pivot in pivots:
        if result and pivot.index == result[-1].index:
            result[-1] = pivot
        elif result and pivot.kind == result[-1].kind:
            keep_new = pivot.price > result[-1].price if pivot.kind == "high" else pivot.price < result[-1].price
            if keep_new:
                result[-1] = pivot
        else:
            result.append(pivot)
    return result


def fmt_price(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.2f}"
    return f"{value:.2f}"


def fmt_round(value: float, step: int = 100) -> str:
    rounded = round(value / step) * step
    return f"{rounded:,.0f}"


def fmt_floor(value: float, step: int = 100) -> str:
    floored = math.floor(value / step) * step
    return f"{floored:,.0f}"


def fmt_ceil(value: float, step: int = 100) -> str:
    ceiled = math.ceil(value / step) * step
    return f"{ceiled:,.0f}"


def validate_bearish_impulse(points: list[Pivot]) -> ImpulseAnalysis | None:
    if len(points) != 6:
        return None
    if [p.kind for p in points] != ["high", "low", "high", "low", "high", "low"]:
        return None
    p0, p1, p2, p3, p4, p5 = points
    wave1 = p0.price - p1.price
    wave3 = p2.price - p3.price
    wave5 = p4.price - p5.price
    if min(wave1, wave3, wave5) <= 0:
        return None
    checks = {
        "wave2_not_beyond_wave1_start": p2.price < p0.price,
        "wave3_not_shortest": wave3 >= min(wave1, wave5),
        "wave4_no_overlap_wave1": p4.price < p1.price,
        "wave3_makes_new_low": p3.price < p1.price,
    }
    if not all(checks.values()):
        return None
    target_equal = p4.price - wave1
    return ImpulseAnalysis("bearish", points, target_equal, checks)


def validate_bullish_main_impulse(points: list[Pivot]) -> MainImpulse | None:
    if len(points) != 6:
        return None
    if [p.kind for p in points] != ["low", "high", "low", "high", "low", "high"]:
        return None
    p0, p1, p2, p3, p4, p5 = points
    wave1 = p1.price - p0.price
    wave3 = p3.price - p2.price
    wave5 = p5.price - p4.price
    if min(wave1, wave3, wave5) <= 0:
        return None
    checks = {
        "wave2_not_beyond_wave1_start": p2.price > p0.price,
        "wave3_not_shortest": wave3 >= min(wave1, wave5),
        "wave4_no_overlap_wave1": p4.price > p1.price,
        "wave3_makes_new_high": p3.price > p1.price,
        "wave5_makes_new_high": p5.price > p3.price,
    }
    if not all(checks.values()):
        return None
    return MainImpulse("bullish", points, checks)


def impulse_fit_score(points: list[Pivot]) -> float:
    p0, p1, p2, p3, p4, p5 = points
    wave1 = p1.price - p0.price
    wave3 = p3.price - p2.price
    wave5 = p5.price - p4.price
    wave2_retrace = (p1.price - p2.price) / wave1 if wave1 else 9
    wave4_retrace = (p3.price - p4.price) / wave3 if wave3 else 9
    wave3_extension = wave3 / wave1 if wave1 else 0
    wave5_relation = wave5 / wave1 if wave1 else 0

    score = 0.0
    score += abs(wave2_retrace - 0.618)
    score += abs(wave4_retrace - 0.382)
    score += abs(wave3_extension - 1.618) * 0.35
    score += abs(wave5_relation - 1.0) * 0.25
    score += 0 if 0.382 <= wave2_retrace <= 0.786 else 2.0
    score += 0 if 0.236 <= wave4_retrace <= 0.5 else 2.0
    return score


def find_main_bullish_impulse(pivots: list[Pivot], main_upswing: MainUpswing | None) -> MainImpulse | None:
    if main_upswing is None:
        return None
    p0_matches = [p for p in pivots if p.index == main_upswing.start_index and p.kind == "low"]
    p5_matches = [p for p in pivots if p.index == main_upswing.high_index and p.kind == "high"]
    if not p0_matches or not p5_matches:
        return None
    p0 = p0_matches[0]
    p5 = p5_matches[0]
    between = [p for p in pivots if p0.index < p.index < p5.index]
    highs = [p for p in between if p.kind == "high"]
    lows = [p for p in between if p.kind == "low"]

    best: tuple[float, MainImpulse] | None = None
    for p1 in highs:
        for p2 in lows:
            if not (p1.index < p2.index):
                continue
            for p3 in highs:
                if not (p2.index < p3.index):
                    continue
                for p4 in lows:
                    if not (p3.index < p4.index):
                        continue
                    candidate = [p0, p1, p2, p3, p4, p5]
                    analysis = validate_bullish_main_impulse(candidate)
                    if analysis is None:
                        continue
                    score = impulse_fit_score(candidate)
                    if best is None or score < best[0]:
                        best = (score, analysis)
    return best[1] if best else None


def find_post_high_correction(pivots: list[Pivot], main_impulse: MainImpulse | None) -> CorrectionStructure | None:
    if main_impulse is None:
        return None
    p0 = main_impulse.points[-1]
    after = [p for p in pivots if p.index > p0.index]
    lows = [p for p in after if p.kind == "low"]
    if len(lows) < 2:
        return None

    best: tuple[float, CorrectionStructure] | None = None
    for w in lows[:-1]:
        x_candidates = [p for p in after if p.kind == "high" and w.index < p.index]
        for x_pivot in x_candidates:
            lows_before_x = [p for p in lows if p.index < x_pivot.index]
            if lows_before_x and w.index != min(lows_before_x, key=lambda p: p.price).index:
                continue
            y_candidates = [p for p in lows if p.index > x_pivot.index and p.price < w.price]
            if not y_candidates:
                continue
            y = min(y_candidates, key=lambda p: p.price)
            decline = p0.price - w.price
            if decline <= 0:
                continue
            x_retrace = (x_pivot.price - w.price) / decline
            checks = {
                "w_declines_from_completed_wave5": w.price < p0.price,
                "x_is_partial_retracement": 0.236 <= x_retrace <= 0.618,
                "y_breaks_below_w": y.price < w.price,
                "sequence_is_high_low_high_low": p0.index < w.index < x_pivot.index < y.index,
            }
            if not all(checks.values()):
                continue
            y_extension = (w.price - y.price) / decline
            score = abs(x_retrace - 0.382) + abs(y_extension - 0.618) * 0.45
            structure = CorrectionStructure(
                kind="wxy_combination",
                points=[p0, w, x_pivot, y],
                labels=["(5)", "W", "X", "Y?"],
                rule_checks=checks,
            )
            if best is None or score < best[0]:
                best = (score, structure)
    return best[1] if best else None


def find_bearish_impulse(pivots: list[Pivot]) -> ImpulseAnalysis | None:
    recent = pivots[-18:]
    best: ImpulseAnalysis | None = None
    for start in range(0, max(0, len(recent) - 5)):
        candidate = recent[start : start + 6]
        analysis = validate_bearish_impulse(candidate)
        if analysis is not None:
            best = analysis
    return best


def choose_levels(pivots: list[Pivot], current: float) -> tuple[WaveLevels | None, str, str]:
    if len(pivots) < 4:
        return None, "unclear", "high-quality wave structure is unclear"

    recent = pivots[-10:]
    highs = [p for p in recent[:-1] if p.kind == "high"]
    lows = [p for p in recent[:-1] if p.kind == "low"]
    last = recent[-1]

    if last.kind == "low" or (lows and current <= max(p.price for p in lows) * 1.08):
        key_low = last.price if last.kind == "low" else min(lows, key=lambda p: abs(p.index - last.index)).price
        prior_highs = [p for p in recent[:-1] if p.kind == "high"]
        if not prior_highs:
            return None, "unclear", "high-quality wave structure is unclear"
        key_high_pivot = max(prior_highs, key=lambda p: p.price)
        key_high = key_high_pivot.price
        later_highs = [p for p in recent[:-1] if p.kind == "high" and p.index > key_high_pivot.index]
        monitor = later_highs[-1].price if later_highs else key_high
        wave_range = max(key_high - key_low, current * 0.03)
        fib_0236 = key_low + wave_range * 0.236
        fib_0382 = key_low + wave_range * 0.382
        fib_0500 = key_low + wave_range * 0.5
        fib_0618 = key_low + wave_range * 0.618
        target = fib_0618 if monitor <= fib_0500 * 1.02 else key_high
        invalidation = key_low - max(wave_range * 0.236, current * 0.03)
        return (
            WaveLevels(key_low, monitor, target, invalidation, fib_0236, fib_0382, fib_0500, fib_0618, key_high, key_low),
            "possible_abc_or_complex_correction",
            "rebound_from_candidate_c",
        )

    if last.kind == "high":
        key_high = last.price
        key_low = min((p.price for p in lows), default=current * 0.94)
        monitor = key_low
        wave_range = max(key_high - key_low, current * 0.03)
        invalidation = key_high + max(wave_range * 0.236, current * 0.03)
        target = key_low - wave_range * 0.618
        fib_0236 = key_high - wave_range * 0.236
        fib_0382 = key_high - wave_range * 0.382
        fib_0500 = key_high - wave_range * 0.5
        fib_0618 = key_high - wave_range * 0.618
        return (
            WaveLevels(key_high, monitor, target, invalidation, fib_0236, fib_0382, fib_0500, fib_0618, key_high, key_low),
            "possible_wave_5_complete",
            "pullback_or_correction",
        )

    low = min(lows, key=lambda p: p.price) if lows else recent[0]
    high = max(highs, key=lambda p: p.price) if highs else recent[-1]
    target = current + (high.price - low.price) * 0.382
    fib_0236 = high.price - (high.price - low.price) * 0.236
    fib_0382 = high.price - (high.price - low.price) * 0.382
    fib_0500 = high.price - (high.price - low.price) * 0.5
    fib_0618 = high.price - (high.price - low.price) * 0.618
    return WaveLevels(low.price, high.price, target, low.price, fib_0236, fib_0382, fib_0500, fib_0618, high.price, low.price), "ambiguous", "monitor_key_levels"


def levels_from_impulse(impulse: ImpulseAnalysis) -> WaveLevels:
    p0, p1, p2, p3, p4, p5 = impulse.points
    key_high = p0.price
    key_low = p5.price
    wave_range = max(p4.price - key_low, abs(p0.price - p1.price))
    fib_0236 = key_low + wave_range * 0.236
    fib_0382 = key_low + wave_range * 0.382
    fib_0500 = key_low + wave_range * 0.5
    fib_0618 = key_low + wave_range * 0.618
    return WaveLevels(
        start=key_low,
        monitor=p4.price,
        target=impulse.target_equal_1_5,
        invalidation=p4.price,
        fib_0236=fib_0236,
        fib_0382=fib_0382,
        fib_0500=fib_0500,
        fib_0618=fib_0618,
        key_high=key_high,
        key_low=key_low,
    )


def fib_text(levels: WaveLevels) -> str:
    return f"斐波那契观察区间：从 {fmt_price(levels.key_low)} 到 {fmt_price(levels.key_high)}。"


def retracement_levels(low: float, high: float) -> dict[str, float]:
    wave_range = high - low
    return {
        "0.382": high - wave_range * 0.382,
        "0.5": high - wave_range * 0.5,
        "0.618": high - wave_range * 0.618,
        "0.786": high - wave_range * 0.786,
    }


def wrap_cjk_lines(lines: list[str], width: int = 24) -> str:
    def tokenize(line: str) -> list[str]:
        tokens: list[str] = []
        i = 0
        while i < len(line):
            ch = line[i]
            if ch.isascii() and (ch.isalnum() or ch in "$-_,.()/"):
                start = i
                while i < len(line) and line[i].isascii() and (line[i].isalnum() or line[i] in "$-_,.()/"):
                    i += 1
                tokens.append(line[start:i])
            else:
                tokens.append(ch)
                i += 1
        return tokens

    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        current = ""
        for token in tokenize(line):
            if current and len(current) + len(token) > width:
                if token in "，。；：、！？,.":  # keep punctuation attached to the previous visual line.
                    current += token
                    wrapped.append(current)
                    current = ""
                else:
                    wrapped.append(current)
                    current = token
            else:
                current += token
        if current:
            wrapped.append(current)
    return "\n".join(wrapped)


def prefers_cycle_low(symbol: str) -> bool:
    return symbol.upper().endswith("-USD") or symbol.upper() in {"BTC", "ETH"}


def prior_upswing_start(
    pivots: list[Pivot] | None,
    key_high: float,
    current_low: float | None = None,
    prefer_cycle_low: bool = False,
) -> Pivot | None:
    if not pivots:
        return None
    high_candidates = [p for p in pivots if p.kind == "high" and abs(p.price - key_high) < 0.05]
    if not high_candidates:
        return None
    key_high_pivot = high_candidates[-1]
    prior_lows = [p for p in pivots if p.kind == "low" and p.index < key_high_pivot.index]
    if not prior_lows:
        return None
    if prefer_cycle_low:
        key_high_time = pd.Timestamp(key_high_pivot.time)
        cycle_start_time = key_high_time - pd.DateOffset(years=4)
        cycle_lows = [p for p in prior_lows if pd.Timestamp(p.time) >= cycle_start_time]
        if cycle_lows:
            return min(cycle_lows, key=lambda p: p.price)
        return min(prior_lows, key=lambda p: p.price)

    candidate = prior_lows[-2] if len(prior_lows) >= 2 else prior_lows[-1]
    if current_low is None or current_low > candidate.price:
        return candidate

    unbroken_lows = [p for p in prior_lows if p.price < current_low]
    if unbroken_lows:
        return unbroken_lows[-1]
    return min(prior_lows, key=lambda p: p.price)


def main_upswing_range(symbol: str, pivots: list[Pivot] | None, levels: WaveLevels | None) -> MainUpswing | None:
    if not pivots or levels is None:
        return None

    if prefers_cycle_low(symbol):
        high_pivot = max((p for p in pivots if p.kind == "high"), key=lambda p: p.price, default=None)
        if high_pivot is None:
            return None
        high_time = pd.Timestamp(high_pivot.time)
        cycle_start_time = high_time - pd.DateOffset(years=4)
        cycle_lows = [
            p
            for p in pivots
            if p.kind == "low" and p.index < high_pivot.index and pd.Timestamp(p.time) >= cycle_start_time
        ]
        if not cycle_lows:
            cycle_lows = [p for p in pivots if p.kind == "low" and p.index < high_pivot.index]
        if not cycle_lows:
            return None
        start_pivot = min(cycle_lows, key=lambda p: p.price)
        return MainUpswing(
            start_pivot.index,
            start_pivot.time,
            start_pivot.price,
            high_pivot.index,
            high_pivot.time,
            high_pivot.price,
        )

    high_pivot = max((p for p in pivots if p.kind == "high"), key=lambda p: p.price, default=None)
    if high_pivot is None:
        return None
    prior_lows = [p for p in pivots if p.kind == "low" and p.index < high_pivot.index]
    if not prior_lows:
        return None
    start_pivot = min(prior_lows, key=lambda p: p.price)
    return MainUpswing(
        start_pivot.index,
        start_pivot.time,
        start_pivot.price,
        high_pivot.index,
        high_pivot.time,
        high_pivot.price,
    )


def build_post(
    symbol: str,
    levels: WaveLevels | None,
    major: str,
    minor: str,
    as_of: str,
    current_price: float | None = None,
    impulse: ImpulseAnalysis | None = None,
    pivots: list[Pivot] | None = None,
    main_upswing: MainUpswing | None = None,
    main_impulse: MainImpulse | None = None,
    correction: CorrectionStructure | None = None,
) -> str:
    if levels is None:
        return (
            f"${symbol} {as_of}波浪结构观察：\n\n"
            "当前高质量波浪结构不明显，只标注关键监测点。\n"
            "暂不强行给出主计数，等待更清晰的突破或回撤结构。\n\n"
            f"{DISCLAIMER}。"
        )

    if major == "abc_with_bearish_c_impulse" and impulse is not None:
        p0, p1, p2, p3, p4, p5 = impulse.points
        wave4_reclaimed = current_price is not None and current_price > p4.price
        rebound_0786 = p5.price + (p0.price - p5.price) * 0.786
        core_low = min(rebound_0786, p2.price)
        core_high = max(rebound_0786, p2.price)
        support_floor = p4.price - (p4.price - p5.price) * 0.27
        confirm_floor = math.floor(p2.price / 500) * 500
        confirm_ceiling = math.ceil((core_high * 1.005) / 100) * 100
        fifth_wave_status = (
            f"最新价约 {fmt_price(current_price)}，已经重新站上(4)浪高点 {fmt_price(p4.price)}，"
            "原先5浪继续延伸的判断需要降级，暂按(5)浪低点已经出现来观察反弹结构。\n"
            if wave4_reclaimed
            else f"5浪起点在 {fmt_price(p4.price)}，当前反弹不超过这里仍有下跌动力。\n"
        )
        follow_up = (
            f"反弹目标先看 {fmt_price(p1.price)}，核心压力区看 {fmt_price(core_low)}-{fmt_price(core_high)}，这是当前较高概率目标。"
            f"若继续站上 {fmt_price(core_high)}，再看 {fmt_price(p0.price)} 附近；若跌破 {fmt_price(p5.price)}，反弹失败，下跌延伸重开。\n"
            if wave4_reclaimed
            else "5浪结束以后，再观察反弹是否开始。\n"
        )
        if wave4_reclaimed:
            if prefers_cycle_low(symbol):
                support_label = f"{fmt_floor(support_floor, 1000)}-{fmt_round(p4.price, 100)}"
                first_target_label = fmt_round(p1.price, 100)
                core_label = f"{confirm_floor:,.0f}-{confirm_ceiling:,.0f}"
                confirm_break_label = f"{confirm_ceiling:,.0f}"
                failure_watch_label = fmt_floor(support_floor, 1000)
                failure_low_label = fmt_round(p5.price, 100)
            else:
                support_label = f"{fmt_price(support_floor)}-{fmt_price(p4.price)}"
                first_target_label = fmt_price(p1.price)
                core_label = f"{fmt_price(core_low)}-{fmt_price(core_high)}"
                confirm_break_label = fmt_price(core_high)
                failure_watch_label = fmt_price(support_floor)
                failure_low_label = fmt_price(p5.price)
            first_target_reclaimed = current_price is not None and current_price >= p1.price
            rebound_sentence = (
                f"当前约 {fmt_round(current_price, 100) if prefers_cycle_low(symbol) else fmt_price(current_price)}，"
                f"已收复 {first_target_label} 第一反弹目标；只要回踩不重新跌破 {first_target_label}，"
                f"短线继续观察 {core_label} 核心确认区。\n"
                if first_target_reclaimed
                else f"上方先看 {first_target_label}，核心确认区看 {core_label}。\n"
            )
            body_detail = (
                "当前短期已从下跌五浪转入反弹验证，紫线为C浪内部(1)-(5)。\n\n"
                f"只要不跌破 {support_label}，反弹仍可继续观察；"
                f"{rebound_sentence}"
                f"突破 {confirm_break_label}，这组下跌大概率结束，进入更大级别反弹；"
                f"跌破 {failure_watch_label} 警惕再探低点，跌破 {failure_low_label} 则反弹失败。\n\n"
            )
        else:
            body_detail = (
                "按大级别A-B-C调整观察，紫线是C浪内部下跌推动，当前可标为(1)-(5)。\n\n"
                f"C浪起点约 {fmt_price(p0.price)}，(1) {fmt_price(p1.price)}，(2) {fmt_price(p2.price)}，"
                f"(3) {fmt_price(p3.price)}，(4) {fmt_price(p4.price)}，当前(5)低点约 {fmt_price(p5.price)}。\n"
                f"{fifth_wave_status}{follow_up}\n"
            )
        body = (
            f"${symbol} {as_of}波浪结构观察：\n\n"
            f"{body_detail}"
            f"{DISCLAIMER}。"
        )
    elif major == "possible_wave_5_complete":
        if main_upswing is not None:
            up_retracements = retracement_levels(main_upswing.start_price, main_upswing.high_price)
            validation_text = "按照推动浪规则，五浪已验证。" if main_impulse is not None else "暂看上一段上升浪末端/候选5浪高点。"
            body = (
                f"${symbol} {as_of}波浪结构观察：\n\n"
                f"此前主升浪从 {fmt_price(main_upswing.start_price)} 上涨到 {fmt_price(main_upswing.high_price)}，{validation_text}\n"
                f"主升浪回撤位：0.382约{fmt_price(up_retracements['0.382'])}，"
                f"0.5约{fmt_price(up_retracements['0.5'])}，"
                f"0.618约{fmt_price(up_retracements['0.618'])}，"
                f"0.786约{fmt_price(up_retracements['0.786'])}。\n"
                f"当前高位回撤观察，0.618约{fmt_price(up_retracements['0.618'])}为较高概率观察区；"
                f"跌破0.786约{fmt_price(up_retracements['0.786'])}，回撤级别扩大。\n"
                f"重新突破主升高点 {fmt_price(main_upswing.high_price)}，才开始观察新的上涨；"
                f"反向确认点 {fmt_price(levels.invalidation)}，站回该位置附近需要重评。\n\n"
                f"{DISCLAIMER}。"
            )
        else:
            body = (
                f"${symbol} {as_of}波浪结构观察：\n\n"
                "红线是主级别浪，黑线是小级别路径。\n"
                f"当前从 {fmt_price(levels.start)} 附近的高点开始回撤观察。\n\n"
                f"情景A：跌破 {fmt_price(levels.monitor)}，回撤级别扩大，下一步按A浪/调整浪观察 {fmt_price(levels.target)} 附近。\n"
                f"情景B：{fmt_price(levels.monitor)} 附近守住，则仍可能是高位震荡或5浪末端延伸。\n\n"
                f"{fib_text(levels)}\n"
                f"反向失效点 {fmt_price(levels.invalidation)}。\n"
                "重新站回该位置附近，则当前回撤路径失效，需要重新评估。\n\n"
                f"{DISCLAIMER}。"
            )
    else:
        if major == "possible_abc_or_complex_correction":
            up_start_price = main_upswing.start_price if main_upswing else None
            up_high_price = main_upswing.high_price if main_upswing else levels.key_high
            up_retracements = retracement_levels(up_start_price, up_high_price) if up_start_price else None
            up_retracement_text = (
                "这段上升浪回撤位："
                f"0.382约{fmt_price(up_retracements['0.382'])}，"
                f"0.5约{fmt_price(up_retracements['0.5'])}，"
                f"0.618约{fmt_price(up_retracements['0.618'])}，"
                f"0.786约{fmt_price(up_retracements['0.786'])}。"
                f"当前更高概率观察0.618约{fmt_price(up_retracements['0.618'])}，"
                f"若跌破再看0.786约{fmt_price(up_retracements['0.786'])}。"
                if up_retracements
                else ""
            )
            if main_impulse is not None:
                main_points = main_impulse.points
                stock_pullback = False
                pullback_support = levels.key_low
                pullback_upside_target = levels.target
                up_context = (
                    f"此前主升浪从 {fmt_price(main_points[0].price)} 上涨到 {fmt_price(main_points[5].price)}，"
                    "按照推动浪规则，五浪已经结束。"
                )
                impulse_context = (
                    f"主升浪标记：(1){fmt_price(main_points[1].price)}，"
                    f"(2){fmt_price(main_points[2].price)}，"
                    f"(3){fmt_price(main_points[3].price)}，"
                    f"(4){fmt_price(main_points[4].price)}，"
                    f"(5){fmt_price(main_points[5].price)}。"
                )
                if correction is not None and correction.kind == "wxy_combination":
                    _, w, x_pivot, y = correction.points
                    if prefers_cycle_low(symbol):
                        correction_summary = (
                            f"{fmt_price(up_high_price)}高点后按组合调整W-X-Y划分："
                            f"W到 {fmt_price(w.price)}，X反弹到 {fmt_price(x_pivot.price)}，"
                            f"当前Y?下探到 {fmt_price(y.price)}。"
                        )
                        short_conclusion = (
                            f"结论：{fmt_price(y.price)}附近有反弹条件；不过 {fmt_price(x_pivot.price)}，"
                            f"仍按Y浪内部反弹。下方跌破 {fmt_price(levels.invalidation)} 看延伸。"
                        )
                    else:
                        stock_pullback = True
                        pullback_support = y.price
                        pullback_upside_target = y.price + (up_high_price - y.price) * 1.272
                        correction_summary = (
                            f"{fmt_price(up_high_price)}高点后按a-b-c回撤观察："
                            f"a到 {fmt_price(w.price)}，b反弹到 {fmt_price(x_pivot.price)}，"
                            f"c暂到 {fmt_price(y.price)}。"
                        )
                        short_conclusion = (
                            f"结论：如果不跌破 {fmt_price(y.price)}，仍可视为上一段上涨后的回撤，"
                            f"突破 {fmt_price(x_pivot.price)} 后观察下一段上涨；"
                            f"如果跌破 {fmt_price(y.price)}，则认为从 {fmt_price(up_high_price)} 开始的调整扩大。"
                        )
                else:
                    correction_summary = f"{fmt_price(up_high_price)}高点后先按调整浪观察，红/黑线从最高点往下划分。"
                    short_conclusion = (
                        f"结论：{fmt_price(levels.key_low)}附近先看反弹；"
                        f"不过{fmt_price(levels.monitor)}仍在调整，跌破{fmt_price(levels.invalidation)}看延伸。"
                    )
            else:
                stock_pullback = False
                pullback_support = levels.key_low
                pullback_upside_target = levels.target
                up_context = (
                    f"此前一段从 {fmt_price(up_start_price)} 上涨到 {fmt_price(up_high_price)}，"
                    "暂看上一段上升浪末端/候选5浪高点。"
                    if up_start_price
                    else f"{fmt_price(up_high_price)} 暂看上一段上升浪末端/候选5浪高点。"
                )
                impulse_context = "因内部没有完整通过推动浪验证，前一段不强行拆成1-5。"
                correction_summary = "红线先按复杂调整W-X-Y观察，不强行标推动浪。"
                short_conclusion = (
                    f"结论：{fmt_price(levels.key_low)}附近先看反弹；"
                    f"不过{fmt_price(levels.monitor)}仍在调整，跌破{fmt_price(levels.invalidation)}看延伸。"
                )
            if main_upswing and abs(up_high_price - levels.key_high) > max(up_high_price * 0.001, 1):
                correction_context = (
                    f"大级别从 {fmt_price(up_high_price)} 后进入调整；"
                    f"当前局部从 {fmt_price(levels.key_high)} 开始，前半段可视为W浪内部A-B-C调整，"
                )
            else:
                correction_context = (
                    f"从 {fmt_price(up_high_price)} 开始，前半段可视为W浪内部A-B-C调整，"
                )
            if stock_pullback:
                body = (
                    f"${symbol} {as_of}波浪结构观察：\n\n"
                    f"{up_context}\n"
                    f"{up_retracement_text}\n"
                    f"{impulse_context}\n"
                    f"{correction_summary}\n"
                    f"{short_conclusion}\n\n"
                    f"情景A：不跌破 {fmt_price(pullback_support)}，仍按5-2/回撤观察；"
                    f"突破 {fmt_price(levels.monitor)} 后，下一步观察 {fmt_price(pullback_upside_target)}。\n"
                    f"情景B：跌破 {fmt_price(pullback_support)}，说明从 {fmt_price(up_high_price)} 开始的回撤扩大，"
                    f"再按更大级别A-B-C或组合调整重画。\n\n"
                    f"{DISCLAIMER}。"
                )
            else:
                body = (
                    f"${symbol} {as_of}波浪结构观察：\n\n"
                    f"{up_context}\n"
                    f"{up_retracement_text}\n"
                    f"{impulse_context}\n"
                    f"{correction_summary}\n"
                    f"{short_conclusion}\n"
                    f"{correction_context}"
                    f"随后反弹到 {fmt_price(levels.monitor)} 附近标为X浪。\n"
                    f"当前从 {fmt_price(levels.monitor)} 回落到 {fmt_price(levels.key_low)}，"
                    "观察是否进入Y浪下跌段。\n\n"
                    f"情景A：重新站上 {fmt_price(levels.monitor)}，说明Y浪可能失败，"
                    f"从 {fmt_price(levels.key_low)} 附近反弹级别扩大，下一步看 {fmt_price(levels.target)}。\n"
                    f"情景B：跌破 {fmt_price(levels.invalidation)}，说明Y浪继续延伸，"
                    "后面再按更低一级A-B-C拆分。\n"
                    f"如果 {fmt_price(levels.monitor)} 过不去，则仍优先当作调整浪内部反弹。\n\n"
                    f"{DISCLAIMER}。"
                )
        else:
            body = (
                f"${symbol} {as_of}波浪结构观察：\n\n"
                "红线是主级别浪，黑线是小级别路径。\n"
                f"当前从 {fmt_price(levels.start)} 附近开始小级别反弹。\n\n"
                f"情景A：突破 {fmt_price(levels.monitor)}，反弹级别扩大，下一步观察 {fmt_price(levels.target)}。\n"
                f"情景B：跌破 {fmt_price(levels.invalidation)}，反弹路径失效，下一步按C浪/更大级别调整观察。\n"
                f"如果 {fmt_price(levels.monitor)} 过不去，则仍在调整内。\n\n"
                f"{fib_text(levels)}\n\n"
                f"{DISCLAIMER}。"
            )
    return body


FUTURE_TRADING_DAYS = 63


def future_paths(levels: WaveLevels, major: str, n: int) -> list[dict[str, object]]:
    xs = [n - 1, n + 15, n + 35, n + FUTURE_TRADING_DAYS]
    if major == "possible_wave_5_complete":
        return [
            {
                "label": "情景A：破位回撤",
                "xs": xs,
                "ys": [levels.start, (levels.start + levels.monitor) / 2, levels.monitor, levels.target],
                "linestyle": "-",
            },
            {
                "label": "情景B：守住延伸",
                "xs": xs,
                "ys": [levels.start, levels.monitor, (levels.monitor + levels.start) / 2, levels.start * 1.015],
                "linestyle": (0, (4, 4)),
            },
        ]
    else:
        pullback = levels.key_low + (levels.monitor - levels.key_low) * 0.45
        return [
            {
                "label": "情景A：反弹扩大",
                "xs": xs,
                "ys": [levels.key_low, levels.monitor, pullback, levels.target],
                "linestyle": "-",
            },
            {
                "label": "情景B：破低延伸",
                "xs": xs,
                "ys": [levels.key_low, pullback, levels.invalidation, levels.invalidation * 0.985],
                "linestyle": (0, (4, 4)),
            },
    ]


def corrective_labels(pivots: list[Pivot], major: str, key_high: float | None = None) -> dict[int, str]:
    if major != "possible_abc_or_complex_correction" or len(pivots) < 4:
        return {}
    labels: dict[int, str] = {}
    recent = pivots[-6:]
    if key_high is not None:
        key_high_matches = [i for i, p in enumerate(pivots) if p.kind == "high" and abs(p.price - key_high) < 0.05]
        if key_high_matches:
            recent = pivots[key_high_matches[-1] :]
    if len(recent) >= 6 and [p.kind for p in recent[:6]] == ["high", "low", "high", "low", "high", "low"]:
        wave_points = recent[:6]
        labels = {
            wave_points[0].index: "W起点",
            wave_points[1].index: "A",
            wave_points[2].index: "B",
            wave_points[3].index: "C/W",
            wave_points[4].index: "X",
            wave_points[5].index: "Y?",
        }
    elif len(recent) >= 4 and [p.kind for p in recent[:4]] == ["high", "low", "high", "low"]:
        wave_points = recent[:4]
        labels = {
            wave_points[0].index: "W起点",
            wave_points[1].index: "C/W",
            wave_points[2].index: "X",
            wave_points[3].index: "Y?",
        }
    return labels


def x_to_date_label(index_value: int, dates: pd.DatetimeIndex) -> str:
    if index_value < len(dates):
        return pd.Timestamp(dates[index_value]).strftime("%Y-%m-%d")
    extra_days = index_value - (len(dates) - 1)
    future_date = pd.Timestamp(dates[-1]) + pd.offsets.BDay(extra_days)
    return future_date.strftime("%Y-%m-%d")


def plot_candles(ax: plt.Axes, data: pd.DataFrame, visible_start: int, visible_end: int) -> None:
    end = min(len(data) - 1, visible_end)
    start = max(0, visible_start)
    candle_width = 0.62
    for i in range(start, end + 1):
        row = data.iloc[i]
        open_price = float(row["Open"])
        high = float(row["High"])
        low = float(row["Low"])
        close_price = float(row["Close"])
        up = close_price >= open_price
        color = "#2f9e44" if up else "#d84a4a"
        body_low = min(open_price, close_price)
        body_height = abs(close_price - open_price)
        ax.vlines(i, low, high, color=color, linewidth=0.8, alpha=0.9, zorder=1)
        if body_height <= max(close_price * 0.0008, 1):
            ax.hlines(close_price, i - candle_width / 2, i + candle_width / 2, color=color, linewidth=1.1, zorder=2)
        else:
            ax.add_patch(
                plt.Rectangle(
                    (i - candle_width / 2, body_low),
                    candle_width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.6,
                    alpha=0.82,
                    zorder=2,
                )
            )


def add_candidate_swing_labels(labels: dict[int, str], pivots: list[Pivot], key_high: float | None) -> dict[int, str]:
    result = dict(labels)
    sequence = ["a", "b", "c"]
    before_count = 0
    after_count = 0
    key_high_index = None
    if key_high is not None:
        matches = [p.index for p in pivots if p.kind == "high" and abs(p.price - key_high) < 0.05]
        key_high_index = matches[-1] if matches else None

    for p in pivots:
        if p.index in result:
            continue
        if key_high_index is None or p.index < key_high_index:
            label = f"{sequence[before_count % 3]}{before_count // 3 + 1}"
            before_count += 1
        else:
            label = f"{sequence[after_count % 3]}{after_count // 3 + 1}"
            after_count += 1
        result[p.index] = label
    return result


def plot_background_wave_path(
    ax: plt.Axes,
    pivots: list[Pivot],
    visible_start: int,
    active_start: int | None,
) -> None:
    if active_start is None:
        return
    background = [p for p in pivots if visible_start <= p.index <= active_start]
    if len(background) < 2:
        return
    ax.plot(
        [p.index for p in background],
        [p.price for p in background],
        color="#d84a4a",
        linewidth=1.55,
        alpha=0.58,
        zorder=3,
    )
    if len(background) <= 16:
        label_points = background
    else:
        step = max(2, len(background) // 10)
        label_points = background[::step]
        if background[-1] not in label_points:
            label_points.append(background[-1])
    sequence = ["a", "b", "c"]
    for i, p in enumerate(label_points):
        va = "bottom" if p.kind == "high" else "top"
        ax.text(
            p.index,
            p.price,
            f"{sequence[i % 3]}{i // 3 + 1}",
            color="#9b2c45",
            fontsize=7.5,
            ha="center",
            va=va,
            alpha=0.72,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.42, "pad": 0.4},
            zorder=4,
        )


def make_chart(
    data: pd.DataFrame,
    pivots: list[Pivot],
    symbol: str,
    display_name: str,
    levels: WaveLevels | None,
    post: str,
    major: str,
    as_of: str,
    out_path: Path,
    impulse: ImpulseAnalysis | None = None,
    main_upswing: MainUpswing | None = None,
    main_impulse: MainImpulse | None = None,
    correction: CorrectionStructure | None = None,
    horizon: str = "auto",
    start_date: str | None = None,
) -> None:
    setup_fonts()
    close = data["Close"]
    x = np.arange(len(close))
    visible_start = 0
    visible_end = len(close) + FUTURE_TRADING_DAYS
    plotted_levels: list[float] = []
    plotted_future_ys: list[float] = []

    fig, (text_ax, ax) = plt.subplots(
        1,
        2,
        figsize=(16.8, 8.6),
        dpi=140,
        gridspec_kw={"width_ratios": [0.40, 0.60], "wspace": 0.02},
    )
    text_ax.axis("off")
    full_window = horizon == "listing" or (horizon == "long" and not prefers_cycle_low(symbol))
    if full_window:
        visible_start = 0
    elif main_upswing is not None:
        visible_start = max(0, main_upswing.start_index - 20)
    if start_date:
        start_ts = pd.Timestamp(start_date)
        start_idx = int(np.searchsorted(close.index, start_ts, side="left"))
        visible_start = min(max(0, start_idx), max(0, len(close) - 1))

    recent_pivots = pivots[-10:]
    active_start_for_background = None
    if full_window and recent_pivots:
        active_start_for_background = main_upswing.start_index if main_upswing is not None else recent_pivots[0].index
        plot_background_wave_path(ax, pivots, visible_start, active_start_for_background)
    if main_impulse is not None and impulse is None:
        main_points = main_impulse.points
        ax.plot(
            [p.index for p in main_points],
            [p.price for p in main_points],
            color="#d84a4a",
            linewidth=2.9,
            zorder=3,
        )
        for label, p in zip(["主升起点", "(1)", "(2)", "(3)", "(4)", "(5)"], main_points):
            va = "bottom" if p.kind == "high" else "top"
            ax.scatter([p.index], [p.price], color="#d84a4a", s=26, zorder=6)
            ax.text(
                p.index,
                p.price,
                label,
                color="#9b2c45",
                fontsize=11 if label != "主升起点" else 9,
                fontweight="bold",
                ha="center",
                va=va,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.62, "pad": 0.8},
                zorder=6,
            )

        if correction is not None:
            correction_points = correction.points
            correction_labels = correction.labels
            correction_color = "black"
            if not prefers_cycle_low(symbol) and correction.kind == "wxy_combination":
                correction_labels = ["(5)", "a", "b", "c/5-2?"]
                correction_color = "#2f9e44"
            ax.plot(
                [p.index for p in correction_points],
                [p.price for p in correction_points],
                color=correction_color,
                linewidth=2.85,
                zorder=5,
            )
            label_offsets = {"W": (-22, 12), "X": (16, 16), "Y?": (22, 12)}
            for label, p in zip(correction_labels, correction_points):
                if label == "(5)":
                    continue
                va = "bottom"
                ax.scatter([p.index], [p.price], color=correction_color, s=22, zorder=6)
                ax.annotate(
                    label,
                    xy=(p.index, p.price),
                    xytext=label_offsets.get(label, (0, 0)),
                    textcoords="offset points",
                    color=correction_color,
                    fontsize=12,
                    fontweight="bold",
                    ha="center",
                    va=va,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.58, "pad": 0.6},
                    zorder=6,
                )

    if impulse is not None:
        impulse_points = impulse.points
        p0 = impulse_points[0]
        all_pre_points = [p for p in pivots if p.index <= p0.index]
        visible_candidates = [p.index for p in all_pre_points[-7:]] + [p.index for p in impulse_points]
        if visible_candidates:
            if not full_window:
                visible_start = max(0, min(visible_candidates) - 8)
            visible_end = max(visible_end, len(close) + FUTURE_TRADING_DAYS)
        if len(all_pre_points) >= 5:
            a_points = all_pre_points[1:5]
            ax.plot([p.index for p in a_points], [p.price for p in a_points], color="#2f9e44", linewidth=2.2)
            for label, p in zip(["(A)", "(B)", "(C)"], a_points[1:4]):
                ax.text(
                    p.index,
                    p.price,
                    label,
                    color="#2f9e44",
                    fontsize=8,
                    ha="center",
                    va="bottom" if p.kind == "high" else "top",
                    clip_on=True,
                )

        pre_points = all_pre_points[-6:]
        if len(pre_points) >= 2:
            ax.plot([p.index for p in pre_points], [p.price for p in pre_points], color="#d84a4a", linewidth=2.2)
            wx_labels = ["(W)", "(X)", "(Y)", "(X)", "(Z)"]
            for label, p in zip(wx_labels[-len(pre_points) :], pre_points):
                ax.text(
                    p.index,
                    p.price,
                    label,
                    color="#bd4057",
                    fontsize=8,
                    ha="center",
                    va="bottom" if p.kind == "high" else "top",
                    clip_on=True,
                )

        impulse_color = "#5b3bbd"
        ax.plot([p.index for p in impulse_points], [p.price for p in impulse_points], color=impulse_color, linewidth=2.9)
        ax.text(p0.index, p0.price, "C浪起点", color="black", fontsize=8, ha="center", va="bottom")
        for label, p in zip(["(1)", "(2)", "(3)", "(4)", "(5)"], impulse_points[1:]):
            va = "bottom" if p.kind == "high" else "top"
            ax.scatter([p.index], [p.price], color=impulse_color, s=22, zorder=5)
            ax.text(p.index, p.price, label, color=impulse_color, fontsize=10, ha="center", va=va, fontweight="bold")
    elif len(recent_pivots) >= 2 and main_impulse is None:
        if not full_window:
            visible_start = min(visible_start, max(0, recent_pivots[0].index - 8))
        visible_end = max(visible_end, len(close) + FUTURE_TRADING_DAYS)
        px = [p.index for p in recent_pivots]
        py = [p.price for p in recent_pivots]
        labels_by_index = corrective_labels(recent_pivots, major, levels.key_high if levels is not None else None)
        labels_by_index = add_candidate_swing_labels(labels_by_index, recent_pivots, levels.key_high if levels is not None else None)
        ax.plot(px, py, color="#d84a4a", linewidth=2.2, zorder=4)
        max_recent_high = max((p.price for p in recent_pivots if p.kind == "high"), default=None)
        min_recent_low = min((p.price for p in recent_pivots if p.kind == "low"), default=None)
        for p in recent_pivots:
            if p.index in labels_by_index:
                label = labels_by_index[p.index]
            elif p.kind == "high" and max_recent_high is not None and abs(p.price - max_recent_high) < 0.01:
                label = "关键前高"
            elif p.kind == "low" and min_recent_low is not None and abs(p.price - min_recent_low) < 0.01:
                label = "当前低点" if p.index == recent_pivots[-1].index else "前升浪起点"
            else:
                label = "高点" if p.kind == "high" else "低点"
            va = "bottom" if p.kind == "high" else "top"
            ax.scatter([p.index], [p.price], color="#d84a4a", s=18, zorder=4)
            is_wave_label = p.index in labels_by_index
            label_color = "#9b2c45" if label in {"W起点", "C/W", "X", "Y?", "A", "B"} else "#111111"
            ax.text(
                p.index,
                p.price,
                label,
                color=label_color,
                fontsize=11 if is_wave_label else 8,
                fontweight="bold" if is_wave_label else "normal",
                ha="center",
                va=va,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.55, "pad": 0.6} if is_wave_label else None,
            )

    if main_upswing is not None and levels is not None and major in {
        "possible_abc_or_complex_correction",
        "possible_wave_5_complete",
    }:
        prior_retracements = retracement_levels(main_upswing.start_price, main_upswing.high_price)
        prior_label_x = visible_start + (visible_end - visible_start) * 0.18
        prior_offsets = {"0.382": 0.65, "0.5": -0.65, "0.618": 0.75, "0.786": -0.75}
        if main_impulse is None:
            ax.scatter([main_upswing.start_index], [main_upswing.start_price], color="#1c7ed6", s=34, zorder=6)
            ax.text(
                main_upswing.start_index,
                main_upswing.start_price,
                "主升浪起点",
                color="#1c7ed6",
                fontsize=9,
                ha="center",
                va="top",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.62, "pad": 0.8},
                zorder=6,
            )
            ax.scatter([main_upswing.high_index], [main_upswing.high_price], color="#9b2c45", s=34, zorder=6)
            ax.text(
                main_upswing.high_index,
                main_upswing.high_price,
                "主升浪高点",
                color="#9b2c45",
                fontsize=9,
                ha="center",
                va="bottom",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.62, "pad": 0.8},
                zorder=6,
            )
        for label, value in prior_retracements.items():
            plotted_levels.append(float(value))
            ax.axhline(value, color="#4dabf7", linestyle=(0, (4, 5)), linewidth=1.05, alpha=0.65)
            suffix = " 高概率" if label == "0.618" else (" 跌破看延伸" if label == "0.786" else "")
            ax.text(
                prior_label_x,
                value + prior_offsets.get(label, 0),
                f"前升浪回撤{label} {fmt_price(value)}{suffix}",
                color="#1c7ed6",
                fontsize=10.5,
                va="center",
                ha="left",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.8},
            )

    if levels is not None:
        if impulse is None:
            for path in future_paths(levels, major, len(close)):
                fx = path["xs"]
                fy = path["ys"]
                plotted_future_ys.extend(float(y) for y in fy)
                ax.plot(fx, fy, color="black", linewidth=2.65, linestyle=path["linestyle"])
                ax.text(fx[-1], fy[-1], str(path["label"]), color="black", fontsize=8, ha="left", va="center")

        if major == "possible_wave_5_complete":
            level_specs = [
                ("当前价", float(close.iloc[-1]), "#2f9e44"),
                ("监测", levels.monitor, "#c92a2a"),
                ("失效", levels.invalidation, "#1c7ed6"),
                ("回撤位0.236", levels.fib_0236, "#868e96"),
                ("回撤位0.382", levels.fib_0382, "#868e96"),
                ("回撤位0.5", levels.fib_0500, "#868e96"),
                ("回撤位0.618 高概率", levels.fib_0618, "#f08c00"),
            ]
        else:
            level_specs = [
                ("当前价", float(close.iloc[-1]), "#2f9e44"),
                ("监测", levels.monitor, "#c92a2a"),
                ("失效", levels.invalidation, "#1c7ed6"),
                ("反弹目标位0.236", levels.fib_0236, "#868e96"),
                ("反弹目标位0.382", levels.fib_0382, "#868e96"),
                ("反弹目标位0.5", levels.fib_0500, "#868e96"),
                ("反弹目标位0.618 高概率", levels.fib_0618, "#f08c00"),
            ]
        if impulse is not None:
            level_specs = [
                ("当前价", float(close.iloc[-1]), "#2f9e44"),
                ("黑1=黑5", impulse.target_equal_1_5, "#f08c00"),
                ("(4)失效", impulse.points[4].price, "#1c7ed6"),
                ("0.382", levels.fib_0382, "#868e96"),
                ("0.5", levels.fib_0500, "#868e96"),
                ("0.618", levels.fib_0618, "#868e96"),
            ]
        seen_level_buckets: dict[int, int] = {}
        for label, value, color in level_specs:
            plotted_levels.append(float(value))
            ax.axhline(value, color=color, linestyle=(0, (2, 4)), linewidth=1.0, alpha=0.85)
            bucket = round(value, 2)
            seen_count = seen_level_buckets.get(bucket, 0)
            seen_level_buckets[bucket] = seen_count + 1
            ax.annotate(
                f"{label} {fmt_price(value)}",
                xy=(len(close) + 2, value),
                xytext=(0, seen_count * 11),
                textcoords="offset points",
                color=color,
                fontsize=9,
                va="center",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.68, "pad": 1.2},
            )

    plot_candles(ax, data, visible_start, visible_end)

    title_name = f" {display_name}" if display_name else ""
    chart_text = post.replace(f"${symbol} {as_of}波浪结构观察：\n\n", "")
    chart_text = chart_text.replace("。", "。\n")
    chart_lines = [line for line in chart_text.splitlines() if line.strip()]
    disclaimer_lines = [line for line in chart_lines if DISCLAIMER in line]
    body_lines = [
        line
        for line in chart_lines
        if DISCLAIMER not in line
        and not line.startswith("这段上升浪回撤位")
        and not line.startswith("当前更高概率")
        and not line.startswith("因内部")
        and not line.startswith("红线")
        and not line.startswith("从 ")
        and not line.startswith("大级别")
        and not line.startswith("当前从")
        and not line.startswith("情景")
        and not line.startswith("如果")
    ]
    body_text = wrap_cjk_lines(body_lines[:6], width=24)
    disclaimer_text = disclaimer_lines[0] if disclaimer_lines else DISCLAIMER
    text_ax.text(
        0.10,
        0.98,
        f"{symbol}{title_name} {as_of}",
        transform=text_ax.transAxes,
        fontsize=18,
        color="#b02a37",
        va="top",
        ha="left",
    )
    text_ax.text(
        0.10,
        0.86,
        body_text,
        transform=text_ax.transAxes,
        fontsize=13.0,
        color="#263c96",
        va="top",
        ha="left",
        linespacing=1.4,
    )
    ax.text(
        0.98,
        0.095,
        "波浪画线图",
        transform=ax.transAxes,
        fontsize=14,
        color="#263c96",
        ha="right",
        va="bottom",
        alpha=0.92,
    )
    ax.text(
        0.98,
        0.035,
        disclaimer_text,
        transform=ax.transAxes,
        fontsize=13.5,
        color="#b02a37",
        ha="right",
        va="bottom",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 1.8},
    )

    tick_count = 7
    tick_idx = np.linspace(visible_start, visible_end, tick_count, dtype=int)
    labels = [x_to_date_label(i, close.index) for i in tick_idx]
    ax.set_xticks(tick_idx)
    ax.set_xticklabels(labels, rotation=0, fontsize=8)

    ax.yaxis.tick_right()
    ax.grid(True, color="#e9ecef", linewidth=0.7)
    for spine in ["top", "left"]:
        ax.spines[spine].set_visible(False)
    ax.set_xlim(visible_start, visible_end)
    visible_stop = min(len(close), max(visible_start + 1, visible_end + 1))
    y_values = list(close.iloc[visible_start:visible_stop].to_numpy(dtype=float))
    y_values.extend(plotted_levels)
    y_values.extend(plotted_future_ys)
    if y_values:
        ymin = min(y_values)
        ymax = max(y_values)
        if math.isfinite(ymin) and math.isfinite(ymax) and ymax > ymin:
            pad = (ymax - ymin) * 0.12
            ax.set_ylim(ymin - pad, ymax + pad)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def write_outputs(
    symbol: str,
    out_root: Path,
    data: pd.DataFrame,
    pivots: list[Pivot],
    name: str,
    horizon: str,
    period: str,
    start_date: str | None = None,
) -> dict[str, str]:
    current = float(data["Close"].iloc[-1])
    as_of = pd.Timestamp(data.index[-1]).strftime("%Y年%-m月%-d日")
    file_date = pd.Timestamp(data.index[-1]).strftime("%Y-%m-%d")
    impulse = find_bearish_impulse(pivots)
    if impulse is not None:
        levels = levels_from_impulse(impulse)
        major = "abc_with_bearish_c_impulse"
        minor = "bearish_c_wave_impulse_1_to_5"
    else:
        levels, major, minor = choose_levels(pivots, current)
    main_upswing = main_upswing_range(symbol, pivots, levels)
    main_impulse = find_main_bullish_impulse(pivots, main_upswing)
    correction = find_post_high_correction(pivots, main_impulse)
    if (
        levels is not None
        and major == "possible_abc_or_complex_correction"
        and main_upswing is not None
        and main_impulse is not None
        and correction is not None
        and correction.kind == "wxy_combination"
        and not prefers_cycle_low(symbol)
    ):
        pullback_low = correction.points[-1].price
        levels.target = pullback_low + (main_upswing.high_price - pullback_low) * 1.272
    post = build_post(
        symbol,
        levels,
        major,
        minor,
        as_of,
        current,
        impulse,
        pivots,
        main_upswing,
        main_impulse,
        correction,
    )

    chart_dir = out_root / "charts"
    post_dir = out_root / "posts"
    data_dir = out_root / "data"
    for directory in [chart_dir, post_dir, data_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    chart_path = chart_dir / f"{symbol}_{file_date}_wave.png"
    post_path = post_dir / f"{symbol}_{file_date}_wave.md"
    json_path = data_dir / f"{symbol}_{file_date}_wave.json"

    make_chart(
        data,
        pivots,
        symbol,
        name,
        levels,
        post,
        major,
        as_of,
        chart_path,
        impulse,
        main_upswing,
        main_impulse,
        correction,
        horizon,
        start_date,
    )
    post_path.write_text(post + "\n", encoding="utf-8")

    payload = {
        "symbol": symbol,
        "as_of": file_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "yfinance",
        "method_version": METHOD_VERSION,
        "horizon": horizon,
        "period": period,
        "start_date": start_date,
        "current_price": current,
        "structure": {"major": major, "minor": minor},
        "levels": asdict(levels) if levels else None,
        "main_upswing": asdict(main_upswing) if main_upswing else None,
        "main_impulse": asdict(main_impulse) if main_impulse else None,
        "correction": asdict(correction) if correction else None,
        "fibonacci": (
            {
                "retracement_0_236": levels.fib_0236,
                "retracement_0_382": levels.fib_0382,
                "retracement_0_500": levels.fib_0500,
            }
            if levels
            else None
        ),
        "scenarios": build_scenarios(levels, major),
        "impulse": asdict(impulse) if impulse else None,
        "pivots": [asdict(p) for p in pivots[-12:]],
        "rule_checks": {
            "wave2_not_breach_wave1_start": impulse.rule_checks["wave2_not_beyond_wave1_start"] if impulse else None,
            "wave3_not_shortest": impulse.rule_checks["wave3_not_shortest"] if impulse else None,
            "wave4_no_overlap": impulse.rule_checks["wave4_no_overlap_wave1"] if impulse else None,
            "main_wave2_not_breach_wave1_start": (
                main_impulse.rule_checks["wave2_not_beyond_wave1_start"] if main_impulse else None
            ),
            "main_wave3_not_shortest": main_impulse.rule_checks["wave3_not_shortest"] if main_impulse else None,
            "main_wave4_no_overlap": main_impulse.rule_checks["wave4_no_overlap_wave1"] if main_impulse else None,
            "has_invalidation_level": levels is not None,
        },
        "disclaimer": DISCLAIMER,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"chart": str(chart_path), "post": str(post_path), "json": str(json_path)}


def build_scenarios(levels: WaveLevels | None, major: str) -> list[dict[str, object]]:
    if levels is None:
        return [{"condition": "wait_for_clearer_pivots", "meaning": "当前高质量波浪结构不明显"}]
    if major == "abc_with_bearish_c_impulse":
        return [
            {"condition": "black_5_reaches_equal_1_5", "level": levels.target, "meaning": "按黑1=黑5测算的C浪(5)目标"},
            {"condition": "rebound_above_wave_4", "level": levels.invalidation, "meaning": "重新站上(4)附近，黑5延伸判断需要重评"},
        ]
    if major == "possible_wave_5_complete":
        return [
            {"condition": "break_below_monitor", "level": levels.monitor, "meaning": "回撤级别扩大", "target": levels.target},
            {"condition": "hold_above_monitor", "level": levels.monitor, "meaning": "仍可能是高位震荡或5浪末端延伸"},
            {"condition": "break_above_invalidation", "level": levels.invalidation, "meaning": "当前回撤路径失效"},
        ]
    if major == "possible_abc_or_complex_correction":
        return [
            {"condition": "break_above_monitor", "level": levels.monitor, "meaning": "低点反弹级别扩大，先看斐波那契反弹位", "target": levels.target},
            {"condition": "reject_below_monitor", "level": levels.monitor, "meaning": "仍在A-B-C/复杂调整内"},
            {"condition": "break_below_invalidation", "level": levels.invalidation, "meaning": "C浪/调整段延伸，观察更低一级目标"},
        ]
    return [
        {"condition": "break_above_monitor", "level": levels.monitor, "meaning": "反弹级别扩大，按小3浪/反弹延伸观察", "target": levels.target},
        {"condition": "reject_below_monitor", "level": levels.monitor, "meaning": "仍在调整内"},
        {"condition": "break_below_invalidation", "level": levels.invalidation, "meaning": "当前反弹路径失效，按C浪/更大级别调整观察"},
    ]


def main() -> None:
    args = parse_args()
    symbol = args.symbol.upper()
    period = resolve_period(symbol, args.period, args.horizon)
    data = fetch_bars(symbol, period, args.interval)
    pivots = detect_pivots(data, args.sensitivity)
    outputs = write_outputs(symbol, Path(args.out), data, pivots, args.name, args.horizon, period, args.start_date)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
