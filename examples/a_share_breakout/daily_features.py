#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""A 股日线突破研究阶段 3：规则指标库与日线失真评分。"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

try:
    from .breakout_events import (
        BreakoutParams,
        build_stage1_masks,
        compute_true_range,
        read_instrument_slices,
        rolling_current_mean,
        rolling_past_max,
        rolling_past_mean,
        rolling_past_mean_before_current_block,
        rolling_past_percentile_rank,
    )
    from .data_inventory import (
        ALLOWED_BOARDS,
        BOARD_LIMITS,
        attach_calendar_bounds,
        compute_one_word_limit_like,
        provider_path,
        read_calendar,
        read_feature_slice,
        read_instruments,
    )
except ImportError:  # pragma: no cover - enables `python examples/.../daily_features.py`
    from breakout_events import (  # type: ignore
        BreakoutParams,
        build_stage1_masks,
        compute_true_range,
        read_instrument_slices,
        rolling_current_mean,
        rolling_past_max,
        rolling_past_mean,
        rolling_past_mean_before_current_block,
        rolling_past_percentile_rank,
    )
    from data_inventory import (  # type: ignore
        ALLOWED_BOARDS,
        BOARD_LIMITS,
        attach_calendar_bounds,
        compute_one_word_limit_like,
        provider_path,
        read_calendar,
        read_feature_slice,
        read_instruments,
    )


DEFAULT_PROVIDER_URI = "~/.qlib/qlib_data/cn_data"
DEFAULT_MARKET = "all"
DEFAULT_START_TIME = "2021-01-01"
DEFAULT_OUTPUT_DIR = "examples/a_share_breakout/outputs"
DEFAULT_BREAKOUT_WINDOWS = (60, 120)
DEFAULT_BENCHMARK = "SH000300"


@dataclass(frozen=True)
class FeatureParams:
    atr_window: int = 14
    volume_window: int = 20
    amount_rank_window: int = 252
    ma_fast_window: int = 20
    ma_slow_window: int = 60
    ma_slope_window: int = 20
    bb_window: int = 20
    return_window: int = 20
    first_days: int = 5
    min_history_days: int = 250
    breakout_atr_multiple: float = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-uri", default=DEFAULT_PROVIDER_URI, help="Qlib 日线数据根目录。")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="instruments/ 下的股票池文件名。")
    parser.add_argument("--start-time", default=DEFAULT_START_TIME, help="特征统计开始日期。")
    parser.add_argument("--end-time", default=None, help="特征统计结束日期；默认使用最新交易日。")
    parser.add_argument("--freq", default="day", choices=["day"], help="Qlib 二进制数据频率。")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="特征矩阵输出目录。")
    parser.add_argument(
        "--breakout-windows",
        nargs="+",
        type=int,
        default=list(DEFAULT_BREAKOUT_WINDOWS),
        help="突破窗口列表，默认同时生成 60 和 120 日特征。",
    )
    parser.add_argument("--benchmark-instrument", default=DEFAULT_BENCHMARK, help="相对强弱基准指数代码。")
    parser.add_argument("--write-parquet", action="store_true", help="除 CSV 外额外输出 Parquet。")
    return parser.parse_args()


def safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    out = np.full_like(numerator, np.nan, dtype=np.float64)
    mask = np.isfinite(numerator) & np.isfinite(denominator) & (np.abs(denominator) > 1e-12)
    out[mask] = numerator[mask] / denominator[mask]
    return out


def sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def shift_past(values: np.ndarray, periods: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    if periods <= 0:
        raise ValueError("periods must be positive")
    if len(values) > periods:
        out[periods:] = values[:-periods]
    return out


def shift_future(values: np.ndarray, periods: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    if periods <= 0:
        raise ValueError("periods must be positive")
    if len(values) > periods:
        out[:-periods] = values[periods:]
    return out


def rolling_current_std(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window:
        return out
    windows = np.lib.stride_tricks.sliding_window_view(values, window)
    valid = np.isfinite(windows).all(axis=1)
    if valid.any():
        out[window - 1 :][valid] = windows[valid].std(axis=1, ddof=0)
    return out


def window_return(values: np.ndarray, window: int) -> np.ndarray:
    return safe_divide(values, shift_past(values, window)) - 1.0


def fill_change_with_close_return(change: np.ndarray, close: np.ndarray) -> np.ndarray:
    close_return = window_return(close, 1)
    return np.where(np.isfinite(change), change, close_return)


def bounded_unit_interval(values: np.ndarray) -> np.ndarray:
    return np.clip(values, 0.0, 1.0)


def values_at_calendar_positions(values: np.ndarray, base_idx: int, positions: np.ndarray) -> np.ndarray:
    out = np.full(len(positions), np.nan, dtype=np.float64)
    local = positions - base_idx
    valid = (local >= 0) & (local < len(values))
    out[valid] = values[local[valid]]
    return out


def read_benchmark_return(
    provider_uri: Path,
    benchmark: str,
    start_idx: int,
    end_idx: int,
    return_window: int,
    freq: str,
) -> Tuple[np.ndarray, int, str]:
    base_idx = max(0, start_idx - return_window)
    close = read_feature_slice(provider_uri, benchmark, "close", base_idx, end_idx, freq=freq)
    if not close.exists or not np.isfinite(close.values).any():
        return np.full(end_idx - base_idx + 1, np.nan, dtype=np.float64), base_idx, "missing"
    return window_return(close.values, return_window), base_idx, benchmark


def build_breakout_params(params: FeatureParams, breakout_window: int) -> BreakoutParams:
    return BreakoutParams(
        breakout_window=breakout_window,
        atr_window=params.atr_window,
        volume_window=params.volume_window,
        amount_rank_window=params.amount_rank_window,
        first_days=params.first_days,
        min_history_days=params.min_history_days,
        breakout_atr_multiple=params.breakout_atr_multiple,
    )


def build_feature_frame_for_instrument(
    instrument: str,
    board: str,
    calendar: pd.DatetimeIndex,
    start_idx: int,
    analysis_start_idx: int,
    analysis_end_idx: int,
    slices: Dict[str, np.ndarray],
    params: FeatureParams,
    breakout_windows: Iterable[int],
    benchmark_return: np.ndarray,
    benchmark_base_idx: int,
) -> pd.DataFrame:
    close = slices["close"]
    high = slices["high"]
    low = slices["low"]
    open_ = slices["open"]
    volume = slices["volume"]
    amount = slices["amount"]
    change = fill_change_with_close_return(slices["change"], close)

    _, special = build_stage1_masks(slices, board, build_breakout_params(params, max(breakout_windows)))
    event_allowed = np.zeros(len(close), dtype=bool)
    lo = analysis_start_idx - start_idx
    hi = analysis_end_idx - start_idx
    event_allowed[lo : hi + 1] = True
    eligible = event_allowed & (~special)
    if not eligible.any():
        return pd.DataFrame()

    true_range = compute_true_range(high, low, close)
    atr_14 = rolling_current_mean(true_range, params.atr_window)
    atr_pct = safe_divide(atr_14, close)
    atr_noise_rank_252 = rolling_past_percentile_rank(atr_pct, params.amount_rank_window)

    ma20 = rolling_current_mean(close, params.ma_fast_window)
    ma60 = rolling_current_mean(close, params.ma_slow_window)
    ma20_slope_20 = safe_divide(ma20 - shift_past(ma20, params.ma_slope_window), shift_past(ma20, params.ma_slope_window))
    bb_mean = rolling_current_mean(close, params.bb_window)
    bb_std = rolling_current_std(close, params.bb_window)
    bb_width_20 = safe_divide(4.0 * bb_std, bb_mean)
    bb_width_rank_252 = rolling_past_percentile_rank(bb_width_20, params.amount_rank_window)

    vol_ratio_20 = safe_divide(volume, rolling_past_mean(volume, params.volume_window))
    vol_ratio_3d = safe_divide(
        rolling_current_mean(volume, 3),
        rolling_past_mean_before_current_block(volume, params.volume_window, current_block=3),
    )
    volume_spike_no_persistence = np.where(
        vol_ratio_20 > 1.0,
        bounded_unit_interval(safe_divide(vol_ratio_20 - vol_ratio_3d, vol_ratio_20)),
        0.0,
    )

    rank_source = "amount"
    rank_values = amount
    if not np.isfinite(amount).any():
        rank_source = "volume_proxy"
        rank_values = volume
    amount_rank_252 = rolling_past_percentile_rank(rank_values, params.amount_rank_window)

    stock_return_20d = window_return(close, params.return_window)
    calendar_positions = np.arange(start_idx, start_idx + len(close))
    benchmark_return_20d = values_at_calendar_positions(benchmark_return, benchmark_base_idx, calendar_positions)
    relative_strength_20d = stock_return_20d - benchmark_return_20d

    board_limit = BOARD_LIMITS.get(board, np.nan)
    limit_dependency_score = bounded_unit_interval(np.maximum(change, 0.0) / (board_limit * 0.98))
    one_word_limit_like = compute_one_word_limit_like(open_, high, low, close, change, board)
    next_open_return = safe_divide(shift_future(open_, 1), close) - 1.0
    next_open_reversal_score = bounded_unit_interval(np.maximum(-next_open_return, 0.0) / board_limit)

    idx = np.flatnonzero(eligible)
    data: Dict[str, object] = {
        "datetime": calendar[start_idx + idx],
        "instrument": instrument,
        "board": board,
        "open": open_[idx],
        "high": high[idx],
        "low": low[idx],
        "close": close[idx],
        "volume": volume[idx],
        "amount": amount[idx],
        "atr_14": atr_14[idx],
        "atr_pct": atr_pct[idx],
        "atr_noise_rank_252": atr_noise_rank_252[idx],
        "ma20": ma20[idx],
        "ma60": ma60[idx],
        "ma20_gt_ma60": ma20[idx] > ma60[idx],
        "ma20_slope_20": ma20_slope_20[idx],
        "bb_width_20": bb_width_20[idx],
        "bb_width_rank_252": bb_width_rank_252[idx],
        "vol_ratio_20": vol_ratio_20[idx],
        "vol_ratio_3d": vol_ratio_3d[idx],
        "volume_spike_no_persistence": volume_spike_no_persistence[idx],
        "amount_rank_252": amount_rank_252[idx],
        "amount_rank_source": rank_source,
        "stock_return_20d": stock_return_20d[idx],
        "benchmark_return_20d": benchmark_return_20d[idx],
        "relative_strength_20d": relative_strength_20d[idx],
        "limit_dependency_score": limit_dependency_score[idx],
        "one_word_limit_like": one_word_limit_like[idx],
        "next_open_return_research": next_open_return[idx],
        "next_open_reversal_score_research": next_open_reversal_score[idx],
    }

    for window in breakout_windows:
        breakout_level = rolling_past_max(close, int(window))
        strength = safe_divide(close - breakout_level, atr_14)
        candidate = (
            eligible
            & np.isfinite(breakout_level)
            & np.isfinite(atr_14)
            & (close > breakout_level)
            & (close >= breakout_level + params.breakout_atr_multiple * atr_14)
        )
        barely_breakout_score = np.where(strength > 0.0, bounded_unit_interval(1.0 - strength), np.nan)
        fake_base = (
            0.25 * volume_spike_no_persistence
            + 0.20 * limit_dependency_score
            + 0.15 * atr_noise_rank_252
            + 0.10 * barely_breakout_score
        )
        fake_prob_t = np.where(strength > 0.0, sigmoid(fake_base), np.nan)
        fake_prob_research = np.where(
            strength > 0.0,
            sigmoid(0.30 * next_open_reversal_score + fake_base),
            np.nan,
        )
        data[f"breakout_level_{window}d"] = breakout_level[idx]
        data[f"breakout_strength_{window}d_atr"] = strength[idx]
        data[f"candidate_{window}d"] = candidate[idx]
        data[f"barely_breakout_score_{window}d"] = barely_breakout_score[idx]
        data[f"fake_prob_daily_t_{window}d"] = fake_prob_t[idx]
        data[f"fake_prob_daily_research_{window}d"] = fake_prob_research[idx]

    return pd.DataFrame(data)


def generate_feature_matrix(
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    active_instruments: pd.DataFrame,
    params: FeatureParams,
    breakout_windows: Iterable[int],
    benchmark_return: np.ndarray,
    benchmark_base_idx: int,
    freq: str,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    windows = tuple(int(window) for window in breakout_windows)
    for _, row in active_instruments.iterrows():
        board = row["board"]
        if board not in ALLOWED_BOARDS:
            continue
        full_start = int(row["calendar_start_idx"])
        analysis_end = int(row["analysis_end_idx"])
        slices = read_instrument_slices(provider_uri, row["instrument"], full_start, analysis_end, freq)
        frame = build_feature_frame_for_instrument(
            instrument=row["instrument"],
            board=board,
            calendar=calendar,
            start_idx=full_start,
            analysis_start_idx=int(row["analysis_start_idx"]),
            analysis_end_idx=analysis_end,
            slices=slices,
            params=params,
            breakout_windows=windows,
            benchmark_return=benchmark_return,
            benchmark_base_idx=benchmark_base_idx,
        )
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["datetime", "instrument"])


def build_feature_dictionary(breakout_windows: Iterable[int], benchmark_status: str) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

    def add(name: str, definition: str, visible_time: str, usable: bool, status: str, reason: str = "", source: str = ""):
        rows.append(
            {
                "feature_name": name,
                "definition": definition,
                "visible_time": visible_time,
                "usable_for_trade_signal": usable,
                "implementation_status": status,
                "missing_data_reason": reason,
                "future_data_source": source,
            }
        )

    add("atr_14", "Mean(TrueRange, 14)", "T close", True, "implemented")
    add("atr_pct", "atr_14 / close", "T close", True, "implemented")
    add("atr_noise_rank_252", "atr_pct 在过去 252 日中的历史分位", "T close", True, "implemented")
    add("ma20_gt_ma60", "Mean(close,20) > Mean(close,60)", "T close", True, "implemented")
    add("ma20_slope_20", "(MA20[t] - MA20[t-20]) / MA20[t-20]", "T close", True, "implemented")
    add("bb_width_20", "4 * Std(close,20) / Mean(close,20)", "T close", True, "implemented")
    add("bb_width_rank_252", "bb_width_20 在过去 252 日中的历史分位", "T close", True, "implemented")
    add("vol_ratio_20", "volume[t] / Mean(volume[t-20:t-1])", "T close", True, "implemented")
    add("vol_ratio_3d", "Mean(volume[t-2:t]) / Mean(volume[t-22:t-3])", "T close", True, "implemented")
    add("amount_rank_252", "成交额在过去 252 日中的历史分位；缺 amount 时回落到 volume", "T close", True, "proxy")
    add(
        "relative_strength_20d",
        f"stock_return_20d - {benchmark_status}_return_20d",
        "T close",
        benchmark_status != "missing",
        "implemented" if benchmark_status != "missing" else "not_available",
        "" if benchmark_status != "missing" else "本地数据中未找到可用基准指数 close 字段。",
        "" if benchmark_status != "missing" else "补充指数行情或改用可用 benchmark_instrument。",
    )
    add("limit_dependency_score", "max(change,0) / board涨停阈值，截断到 [0,1]", "T close", True, "proxy")
    add("one_word_limit_like", "OHLC 近似相等且涨幅接近板块涨停阈值", "T close", True, "proxy")
    add("next_open_return_research", "open[t+1] / close[t] - 1", "T+1 open", False, "research_only")
    add("next_open_reversal_score_research", "max(-(open[t+1]/close[t]-1),0) / board涨停阈值", "T+1 open", False, "research_only")

    for window in breakout_windows:
        add(f"breakout_level_{window}d", f"Max(close[t-{window}:t-1])", "T close", True, "implemented")
        add(
            f"breakout_strength_{window}d_atr",
            f"(close[t] - breakout_level_{window}d) / atr_14",
            "T close",
            True,
            "implemented",
        )
        add(
            f"candidate_{window}d",
            f"close 突破过去 {window} 日高点且至少超过 0.5 ATR，并通过阶段 1 样本过滤",
            "T close",
            True,
            "implemented",
        )
        add(f"barely_breakout_score_{window}d", "1 - breakout_strength_atr，截断到 [0,1]", "T close", True, "proxy")
        add(
            f"fake_prob_daily_t_{window}d",
            "sigmoid(0.25*量能突刺不持续 + 0.20*涨停依赖 + 0.15*ATR噪声分位 + 0.10*刚好越过突破位)",
            "T close",
            True,
            "daily_proxy",
        )
        add(
            f"fake_prob_daily_research_{window}d",
            "在 fake_prob_daily_t 基础上加入 0.30*T+1开盘回吐，仅用于事后归因",
            "T+1 open",
            False,
            "research_only",
        )

    missing = [
        ("turnover_pct", "需要流通股本或换手率字段", "流通股本/换手率日频数据"),
        ("high_limit_low_limit", "本地日线包没有精确涨跌停价字段", "交易所涨跌停价或供应商 limit 字段"),
        ("tail_30m_volume_share", "需要分钟成交量", "1min 数据"),
        ("close_vs_30m_vwap", "需要尾盘 30 分钟 VWAP", "1min 数据"),
        ("order_book_imbalance_decay", "需要盘口快照或 Level-2", "Level-2 数据"),
        ("cancel_rate_or_order_trade_ratio", "需要逐笔委托与成交", "逐笔委托/成交数据"),
        ("main_fund_flow_consistency", "需要供应商资金流口径", "资金流数据"),
        ("industry_relative_strength", "需要行业分类与行业指数", "行业分类/行业指数数据"),
        ("standard_adx_dmi", "本阶段暂未自算 ADX/DMI", "pandas/talib 自算或自定义算子"),
    ]
    for name, reason, source in missing:
        add(name, "阶段 3 未生成", "unknown", False, "not_implemented", reason, source)

    return pd.DataFrame(rows)


def summarize_feature_matrix(feature_matrix: pd.DataFrame, breakout_windows: Iterable[int]) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    if feature_matrix.empty:
        return pd.DataFrame(rows)
    rows.append({"section": "matrix", "name": "rows_written", "value": int(len(feature_matrix))})
    rows.append({"section": "matrix", "name": "instrument_count", "value": int(feature_matrix["instrument"].nunique())})
    rows.append({"section": "matrix", "name": "first_date", "value": feature_matrix["datetime"].min().strftime("%Y-%m-%d")})
    rows.append({"section": "matrix", "name": "last_date", "value": feature_matrix["datetime"].max().strftime("%Y-%m-%d")})

    for board, count in feature_matrix["board"].value_counts().sort_index().items():
        rows.append({"section": "board_rows", "name": board, "value": int(count)})
    for window in breakout_windows:
        col = f"candidate_{window}d"
        rows.append({"section": "candidate", "name": col, "value": int(feature_matrix[col].sum())})
    for column in feature_matrix.columns:
        if column in {"datetime", "instrument", "board", "amount_rank_source"}:
            continue
        value = int(feature_matrix[column].notna().sum())
        rows.append({"section": "nonnull", "name": column, "value": value})
    return pd.DataFrame(rows)


def write_outputs(
    output_dir: Path,
    feature_matrix: pd.DataFrame,
    feature_dictionary: pd.DataFrame,
    breakout_windows: Iterable[int],
    write_parquet: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_matrix.to_csv(output_dir / "feature_matrix_daily.csv", index=False)
    if write_parquet:
        feature_matrix.to_parquet(output_dir / "feature_matrix_daily.parquet", index=False)
    feature_dictionary.to_csv(output_dir / "feature_dictionary_daily.csv", index=False)
    summarize_feature_matrix(feature_matrix, breakout_windows).to_csv(output_dir / "feature_matrix_summary.csv", index=False)


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

    params = FeatureParams()
    benchmark_return, benchmark_base_idx, benchmark_status = read_benchmark_return(
        provider_uri=provider_uri,
        benchmark=args.benchmark_instrument,
        start_idx=start_idx,
        end_idx=end_idx,
        return_window=params.return_window,
        freq=args.freq,
    )
    windows = tuple(int(window) for window in args.breakout_windows)
    feature_matrix = generate_feature_matrix(
        provider_uri=provider_uri,
        calendar=calendar,
        active_instruments=active_instruments,
        params=params,
        breakout_windows=windows,
        benchmark_return=benchmark_return,
        benchmark_base_idx=benchmark_base_idx,
        freq=args.freq,
    )
    feature_dictionary = build_feature_dictionary(windows, benchmark_status=benchmark_status)
    output_dir = Path(args.output_dir)
    write_outputs(
        output_dir=output_dir,
        feature_matrix=feature_matrix,
        feature_dictionary=feature_dictionary,
        breakout_windows=windows,
        write_parquet=args.write_parquet,
    )

    print(f"数据路径={provider_uri}")
    print(f"特征窗口={calendar[start_idx].date()}..{calendar[end_idx].date()}")
    print(f"输出目录={output_dir.resolve()}")
    print(f"输出行数={len(feature_matrix)}")
    print(f"基准指数={benchmark_status}")
    print(f"生成时间={dt.datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
