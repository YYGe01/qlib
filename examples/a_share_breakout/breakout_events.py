#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""A 股日线突破研究阶段 2：突破事件识别与真/假突破标注。"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

try:
    from .data_inventory import (
        ALLOWED_BOARDS,
        BOARD_CN,
        compute_one_word_limit_like,
        read_calendar,
        read_feature_slice,
        read_instruments,
        attach_calendar_bounds,
        provider_path,
    )
except ImportError:  # pragma: no cover - enables `python examples/.../breakout_events.py`
    from data_inventory import (  # type: ignore
        ALLOWED_BOARDS,
        BOARD_CN,
        compute_one_word_limit_like,
        read_calendar,
        read_feature_slice,
        read_instruments,
        attach_calendar_bounds,
        provider_path,
    )


DEFAULT_PROVIDER_URI = "~/.qlib/qlib_data/cn_data"
DEFAULT_MARKET = "all"
DEFAULT_START_TIME = "2021-01-01"
DEFAULT_OUTPUT_DIR = "examples/a_share_breakout/outputs"
DEFAULT_BREAKOUT_WINDOWS = (60, 120)


@dataclass(frozen=True)
class BreakoutParams:
    breakout_window: int
    atr_window: int = 14
    volume_window: int = 20
    amount_rank_window: int = 252
    retest_window: int = 5
    holding_window: int = 20
    first_days: int = 5
    min_history_days: int = 250
    breakout_atr_multiple: float = 0.5
    volume_ratio_threshold: float = 1.5
    amount_rank_threshold: float = 0.70
    retest_atr_multiple: float = 1.0
    true_breakout_return: float = 0.08
    weak_follow_return: float = 0.03
    false_breakout_drawdown: float = -0.06


EVENT_COLUMNS = [
    "event_date",
    "instrument",
    "board",
    "board_cn",
    "breakout_window",
    "breakout_level",
    "close_t",
    "atr_14",
    "atr_pct",
    "breakout_strength_atr",
    "vol_ratio_20",
    "vol_ratio_3d",
    "amount_rank_252",
    "amount_rank_source",
    "vol_ok",
    "amount_rank_ok",
    "retest_fail_5",
    "future_max_20",
    "future_min_20",
    "label",
    "special_event_flags",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-uri", default=DEFAULT_PROVIDER_URI, help="Qlib 日线数据根目录。")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="instruments/ 下的股票池文件名。")
    parser.add_argument("--start-time", default=DEFAULT_START_TIME, help="事件统计开始日期。")
    parser.add_argument("--end-time", default=None, help="事件统计结束日期；默认使用最新交易日。")
    parser.add_argument("--freq", default="day", choices=["day"], help="Qlib 二进制数据频率。")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="事件表输出目录。")
    parser.add_argument(
        "--breakout-windows",
        nargs="+",
        type=int,
        default=list(DEFAULT_BREAKOUT_WINDOWS),
        help="突破窗口列表，默认同时生成 60 和 120 日事件。",
    )
    parser.add_argument("--sample-size", type=int, default=20, help="每个窗口随机抽样核对的事件数量。")
    parser.add_argument("--random-state", type=int, default=20260517, help="随机抽样种子。")
    return parser.parse_args()


def rolling_past_max(values: np.ndarray, window: int) -> np.ndarray:
    return rolling_past_reduce(values, window, np.max)


def rolling_past_mean(values: np.ndarray, window: int) -> np.ndarray:
    return rolling_past_reduce(values, window, np.mean)


def rolling_current_mean(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, window)
    valid = np.isfinite(windows).all(axis=1)
    if valid.any():
        out[window - 1 :][valid] = windows[valid].mean(axis=1)
    return out


def rolling_past_reduce(values: np.ndarray, window: int, reducer) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) <= window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, window + 1)
    past = windows[:, :window]
    valid = np.isfinite(past).all(axis=1)
    if valid.any():
        out[window:][valid] = reducer(past[valid], axis=1)
    return out


def rolling_past_mean_before_current_block(values: np.ndarray, window: int, current_block: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    full_window = window + current_block
    if len(values) < full_window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, full_window)
    past = windows[:, :window]
    valid = np.isfinite(past).all(axis=1)
    if valid.any():
        out[full_window - 1 :][valid] = past[valid].mean(axis=1)
    return out


def rolling_past_percentile_rank(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) <= window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, window + 1)
    past = windows[:, :window]
    current = windows[:, window]
    valid = np.isfinite(past).all(axis=1) & np.isfinite(current)
    if valid.any():
        out[window:][valid] = (past[valid] <= current[valid, None]).mean(axis=1)
    return out


def future_window_extremes(values: np.ndarray, window: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    future_max = np.full(len(values), np.nan, dtype=np.float64)
    future_min = np.full(len(values), np.nan, dtype=np.float64)
    complete = np.zeros(len(values), dtype=bool)
    if len(values) <= window:
        return future_max, future_min, complete
    windows = np.lib.stride_tricks.sliding_window_view(values, window + 1)
    future = windows[:, 1:]
    valid = np.isfinite(future).all(axis=1)
    if valid.any():
        future_max[: len(windows)][valid] = future[valid].max(axis=1)
        future_min[: len(windows)][valid] = future[valid].min(axis=1)
        complete[: len(windows)][valid] = True
    return future_max, future_min, complete


def future_retest_fail(
    close: np.ndarray,
    breakout_level: np.ndarray,
    atr: np.ndarray,
    retest_window: int,
    atr_multiple: float,
) -> np.ndarray:
    out = np.zeros(len(close), dtype=bool)
    if len(close) <= retest_window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(close, retest_window + 1)
    future = windows[:, 1:]
    thresholds = breakout_level[: len(windows)] - atr_multiple * atr[: len(windows)]
    valid = np.isfinite(future).all(axis=1) & np.isfinite(thresholds)
    if valid.any():
        out[: len(windows)][valid] = (future[valid] < thresholds[valid, None]).any(axis=1)
    return out


def compute_true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    prev_close = np.r_[np.nan, close[:-1]]
    components = np.vstack([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    valid = np.isfinite(components).any(axis=0)
    out = np.full(len(close), np.nan, dtype=np.float64)
    if valid.any():
        out[valid] = np.nanmax(components[:, valid], axis=0)
    return out


def classify_breakout_labels(
    vol_ok: np.ndarray,
    amount_rank_ok: np.ndarray,
    retest_fail: np.ndarray,
    future_max_return: np.ndarray,
    future_min_return: np.ndarray,
    params: BreakoutParams,
) -> np.ndarray:
    labels = np.full(len(future_max_return), "ambiguous", dtype=object)
    false_mask = (
        retest_fail
        | (future_max_return < params.weak_follow_return)
        | (future_min_return <= params.false_breakout_drawdown)
    )
    true_mask = (
        (vol_ok | amount_rank_ok)
        & (future_max_return >= params.true_breakout_return)
        & (~retest_fail)
        & (~false_mask)
    )
    labels[false_mask] = "false_breakout"
    labels[true_mask] = "true_breakout"
    return labels


def build_stage1_masks(
    slices: Dict[str, np.ndarray],
    board: str,
    params: BreakoutParams,
) -> Tuple[np.ndarray, np.ndarray]:
    close = slices["close"]
    volume = slices["volume"]
    tradable_base = np.isfinite(close) & np.isfinite(volume) & (volume > 0)
    trading_age = np.cumsum(tradable_base.astype(np.int64))
    prev_tradable = np.r_[False, tradable_base[:-1]]

    required_missing = np.zeros(len(close), dtype=bool)
    for field in ("open", "high", "low", "close", "volume", "factor"):
        required_missing |= ~np.isfinite(slices[field])
    required_missing |= volume <= 0

    first_days = tradable_base & (trading_age > 0) & (trading_age <= params.first_days)
    listed_lt_min_history = (
        tradable_base & (trading_age > params.first_days) & (trading_age <= params.min_history_days)
    )
    resume_first_day = tradable_base & (~prev_tradable) & (trading_age > params.first_days)
    one_word_limit_like = compute_one_word_limit_like(
        open_=slices["open"],
        high=slices["high"],
        low=slices["low"],
        close=close,
        change=slices["change"],
        board=board,
    )
    special = required_missing | first_days | listed_lt_min_history | resume_first_day | one_word_limit_like
    return tradable_base, special


def read_instrument_slices(
    provider_uri: Path,
    instrument: str,
    start_idx: int,
    end_idx: int,
    freq: str,
) -> Dict[str, np.ndarray]:
    fields = ("open", "high", "low", "close", "volume", "amount", "factor", "change")
    return {
        field: read_feature_slice(provider_uri, instrument, field, start_idx, end_idx, freq=freq).values
        for field in fields
    }


def build_window_events_for_instrument(
    instrument: str,
    board: str,
    calendar: pd.DatetimeIndex,
    start_idx: int,
    analysis_start_idx: int,
    analysis_end_idx: int,
    slices: Dict[str, np.ndarray],
    params: BreakoutParams,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    close = slices["close"]
    high = slices["high"]
    low = slices["low"]
    volume = slices["volume"]
    amount = slices["amount"]

    _, special = build_stage1_masks(slices, board, params)
    breakout_level = rolling_past_max(close, params.breakout_window)
    atr = rolling_current_mean(compute_true_range(high, low, close), params.atr_window)
    vol_ratio_20 = volume / rolling_past_mean(volume, params.volume_window)
    vol_ratio_3d = rolling_current_mean(volume, 3) / rolling_past_mean_before_current_block(
        volume, params.volume_window, current_block=3
    )

    rank_source = "amount"
    rank_values = amount
    if not np.isfinite(amount).any():
        rank_source = "volume_proxy"
        rank_values = volume
    amount_rank = rolling_past_percentile_rank(rank_values, params.amount_rank_window)

    event_allowed = np.zeros(len(close), dtype=bool)
    lo = analysis_start_idx - start_idx
    hi = analysis_end_idx - start_idx
    event_allowed[lo : hi + 1] = True
    candidate = (
        event_allowed
        & (~special)
        & np.isfinite(close)
        & np.isfinite(breakout_level)
        & np.isfinite(atr)
        & (close > breakout_level)
        & (close >= breakout_level + params.breakout_atr_multiple * atr)
    )

    future_max_price, future_min_price, future_complete = future_window_extremes(close, params.holding_window)
    future_max_return = future_max_price / close - 1.0
    future_min_return = future_min_price / close - 1.0
    retest_fail = future_retest_fail(
        close=close,
        breakout_level=breakout_level,
        atr=atr,
        retest_window=params.retest_window,
        atr_multiple=params.retest_atr_multiple,
    )

    candidate_count = int(candidate.sum())
    labelable = candidate & future_complete
    insufficient = int((candidate & (~future_complete)).sum())
    if not labelable.any():
        return pd.DataFrame(columns=EVENT_COLUMNS), {
            "candidate_count": candidate_count,
            "insufficient_future_count": insufficient,
            "events_written": 0,
        }

    vol_ok = vol_ratio_20 >= params.volume_ratio_threshold
    amount_rank_ok = amount_rank >= params.amount_rank_threshold
    labels = classify_breakout_labels(vol_ok, amount_rank_ok, retest_fail, future_max_return, future_min_return, params)
    idx = np.flatnonzero(labelable)
    event_dates = calendar[start_idx + idx]
    rows = pd.DataFrame(
        {
            "event_date": event_dates,
            "instrument": instrument,
            "board": board,
            "board_cn": BOARD_CN.get(board, board),
            "breakout_window": params.breakout_window,
            "breakout_level": breakout_level[idx],
            "close_t": close[idx],
            "atr_14": atr[idx],
            "atr_pct": atr[idx] / close[idx],
            "breakout_strength_atr": (close[idx] - breakout_level[idx]) / atr[idx],
            "vol_ratio_20": vol_ratio_20[idx],
            "vol_ratio_3d": vol_ratio_3d[idx],
            "amount_rank_252": amount_rank[idx],
            "amount_rank_source": rank_source,
            "vol_ok": vol_ok[idx],
            "amount_rank_ok": amount_rank_ok[idx],
            "retest_fail_5": retest_fail[idx],
            "future_max_20": future_max_return[idx],
            "future_min_20": future_min_return[idx],
            "label": labels[idx],
            "special_event_flags": "none",
        },
        columns=EVENT_COLUMNS,
    )
    return rows, {
        "candidate_count": candidate_count,
        "insufficient_future_count": insufficient,
        "events_written": int(len(rows)),
    }


def generate_events(
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    active_instruments: pd.DataFrame,
    params: BreakoutParams,
    freq: str,
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    frames: List[pd.DataFrame] = []
    stats = {"candidate_count": 0, "insufficient_future_count": 0, "events_written": 0}
    for _, row in active_instruments.iterrows():
        board = row["board"]
        if board not in ALLOWED_BOARDS:
            continue
        instrument = row["instrument"]
        full_start = int(row["calendar_start_idx"])
        analysis_end = int(row["analysis_end_idx"])
        slices = read_instrument_slices(provider_uri, instrument, full_start, analysis_end, freq)
        events, instrument_stats = build_window_events_for_instrument(
            instrument=instrument,
            board=board,
            calendar=calendar,
            start_idx=full_start,
            analysis_start_idx=int(row["analysis_start_idx"]),
            analysis_end_idx=analysis_end,
            slices=slices,
            params=params,
        )
        for key in stats:
            stats[key] += instrument_stats[key]
        if not events.empty:
            frames.append(events)
    if not frames:
        return pd.DataFrame(columns=EVENT_COLUMNS), stats
    return pd.concat(frames, ignore_index=True).sort_values(["event_date", "instrument"]), stats


def build_manual_check_sample(
    events: pd.DataFrame,
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    freq: str,
    sample_size: int,
    random_state: int,
    pre_days: int = 5,
    post_days: int = 20,
) -> pd.DataFrame:
    if events.empty or sample_size <= 0:
        return pd.DataFrame()
    sample = events.sample(n=min(sample_size, len(events)), random_state=random_state)
    rows: List[Dict[str, object]] = []
    for _, event in sample.sort_values(["event_date", "instrument"]).iterrows():
        event_idx = int(calendar.get_loc(pd.Timestamp(event["event_date"])))
        start_idx = max(0, event_idx - pre_days)
        end_idx = min(len(calendar) - 1, event_idx + post_days)
        slices = {
            field: read_feature_slice(provider_uri, event["instrument"], field, start_idx, end_idx, freq=freq).values
            for field in ("open", "high", "low", "close", "volume")
        }
        for offset, date in enumerate(calendar[start_idx : end_idx + 1]):
            rows.append(
                {
                    "breakout_window": int(event["breakout_window"]),
                    "instrument": event["instrument"],
                    "event_date": pd.Timestamp(event["event_date"]).strftime("%Y-%m-%d"),
                    "label": event["label"],
                    "relative_day": int(start_idx + offset - event_idx),
                    "datetime": date.strftime("%Y-%m-%d"),
                    "open": slices["open"][offset],
                    "high": slices["high"][offset],
                    "low": slices["low"][offset],
                    "close": slices["close"][offset],
                    "volume": slices["volume"][offset],
                    "breakout_level": event["breakout_level"],
                    "atr_14": event["atr_14"],
                }
            )
    return pd.DataFrame(rows)


def summarize_events(events_by_window: Dict[int, pd.DataFrame], stats_by_window: Dict[int, Dict[str, int]]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for window, stats in stats_by_window.items():
        rows.append({"breakout_window": window, "section": "candidate", "name": "all_candidates", "count": stats["candidate_count"]})
        rows.append(
            {
                "breakout_window": window,
                "section": "candidate",
                "name": "insufficient_future_excluded",
                "count": stats["insufficient_future_count"],
            }
        )
        rows.append({"breakout_window": window, "section": "candidate", "name": "events_written", "count": stats["events_written"]})
        events = events_by_window[window]
        if events.empty:
            continue
        for label, count in events["label"].value_counts().sort_index().items():
            rows.append({"breakout_window": window, "section": "label", "name": label, "count": int(count)})
        board_counts = events.groupby(["board", "label"]).size().reset_index(name="count")
        for _, row in board_counts.iterrows():
            rows.append(
                {
                    "breakout_window": window,
                    "section": "board_label",
                    "name": f"{row['board']}:{row['label']}",
                    "count": int(row["count"]),
                }
            )
    return pd.DataFrame(rows)


def write_window_outputs(
    output_dir: Path,
    events_by_window: Dict[int, pd.DataFrame],
    stats_by_window: Dict[int, Dict[str, int]],
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    freq: str,
    sample_size: int,
    random_state: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for window, events in events_by_window.items():
        csv_path = output_dir / f"breakout_events_{window}d.csv"
        parquet_path = output_dir / f"breakout_events_{window}d.parquet"
        events.to_csv(csv_path, index=False)
        events.to_parquet(parquet_path, index=False)
        sample = build_manual_check_sample(
            events=events,
            provider_uri=provider_uri,
            calendar=calendar,
            freq=freq,
            sample_size=sample_size,
            random_state=random_state + window,
        )
        sample.to_csv(output_dir / f"breakout_events_{window}d_manual_check_ohlcv.csv", index=False)

    summarize_events(events_by_window, stats_by_window).to_csv(output_dir / "breakout_event_summary.csv", index=False)


def main() -> None:
    args = parse_args()
    provider_uri = provider_path(args.provider_uri)
    calendar = read_calendar(provider_uri, freq=args.freq)
    instruments = read_instruments(provider_uri, args.market)
    active_instruments, start_idx, end_idx = attach_calendar_bounds(
        instruments,
        calendar,
        start_time=args.start_time,
        end_time=args.end_time,
    )

    events_by_window: Dict[int, pd.DataFrame] = {}
    stats_by_window: Dict[int, Dict[str, int]] = {}
    for window in args.breakout_windows:
        params = BreakoutParams(breakout_window=int(window))
        events, stats = generate_events(provider_uri, calendar, active_instruments, params, args.freq)
        events_by_window[int(window)] = events
        stats_by_window[int(window)] = stats
        print(
            f"{window}日突破：候选={stats['candidate_count']}，"
            f"20日未来不足剔除={stats['insufficient_future_count']}，输出事件={stats['events_written']}"
        )

    output_dir = Path(args.output_dir)
    write_window_outputs(
        output_dir=output_dir,
        events_by_window=events_by_window,
        stats_by_window=stats_by_window,
        provider_uri=provider_uri,
        calendar=calendar,
        freq=args.freq,
        sample_size=args.sample_size,
        random_state=args.random_state,
    )

    print(f"数据路径={provider_uri}")
    print(f"事件窗口={calendar[start_idx].date()}..{calendar[end_idx].date()}")
    print(f"输出目录={output_dir.resolve()}")
    print(f"生成时间={dt.datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
