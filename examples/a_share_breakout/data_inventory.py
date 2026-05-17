#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""A 股日线突破研究阶段 1：数据盘点与样本过滤审计。

脚本直接读取本地 Qlib 日线二进制数据，不生成突破事件或交易信号，只负责在事件研究前
冻结可复现的数据基础。
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


DEFAULT_PROVIDER_URI = "~/.qlib/qlib_data/cn_data"
DEFAULT_START_TIME = "2021-01-01"
DEFAULT_MARKET = "all"
DEFAULT_OUTPUT_DIR = "examples/a_share_breakout/outputs"

CORE_FIELDS = ("open", "high", "low", "close", "volume", "amount", "vwap", "factor", "change")
REQUIRED_FIELDS = ("open", "high", "low", "close", "volume", "factor")
ALLOWED_BOARDS = {"main_board", "chinext", "star_market", "beijing"}
BOARD_LIMITS = {
    "main_board": 0.10,
    "chinext": 0.20,
    "star_market": 0.20,
    "beijing": 0.30,
}
BOARD_CN = {
    "main_board": "主板",
    "chinext": "创业板",
    "star_market": "科创板",
    "beijing": "北交所",
    "b_share": "B股",
    "index_or_fund_or_other": "指数/基金/其他",
    "unknown": "未知",
}


@dataclass(frozen=True)
class FeatureSlice:
    values: np.ndarray
    exists: bool
    storage_start_idx: Optional[int]
    storage_end_idx: Optional[int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-uri", default=DEFAULT_PROVIDER_URI, help="Qlib 日线数据根目录。")
    parser.add_argument("--market", default=DEFAULT_MARKET, help="instruments/ 下的股票池文件名。")
    parser.add_argument("--start-time", default=DEFAULT_START_TIME, help="统计开始日期。")
    parser.add_argument("--end-time", default=None, help="统计结束日期；默认使用最新交易日。")
    parser.add_argument("--freq", default="day", choices=["day"], help="Qlib 二进制数据频率。")
    parser.add_argument("--min-history-days", type=int, default=250, help="最小交易年龄过滤阈值。")
    parser.add_argument("--first-days", type=int, default=5, help="新股上市前 N 个交易日过滤阈值。")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="CSV 输出目录。")
    return parser.parse_args()


def provider_path(provider_uri: str) -> Path:
    return Path(provider_uri).expanduser().resolve()


def read_calendar(provider_uri: Path, freq: str = "day") -> pd.DatetimeIndex:
    path = provider_uri / "calendars" / f"{freq}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Calendar file not found: {path}")
    values = pd.read_csv(path, header=None, names=["datetime"])["datetime"]
    return pd.DatetimeIndex(pd.to_datetime(values), name="datetime")


def read_instruments(provider_uri: Path, market: str) -> pd.DataFrame:
    path = provider_uri / "instruments" / f"{market.lower()}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Instrument file not found: {path}")
    df = pd.read_csv(path, sep=r"\s+", header=None, names=["instrument", "start_time", "end_time"])
    df["instrument"] = df["instrument"].str.upper()
    df["start_time"] = pd.to_datetime(df["start_time"])
    df["end_time"] = pd.to_datetime(df["end_time"])
    df["board"] = df["instrument"].map(classify_board)
    return df


def classify_board(instrument: str) -> str:
    code = instrument.upper()
    if len(code) < 4:
        return "unknown"
    prefix = code[:2]
    digits = code[2:]
    if prefix == "BJ" and digits.isdigit():
        return "beijing"
    if prefix == "SH" and digits.isdigit():
        if digits.startswith("900"):
            return "b_share"
        if digits.startswith("68"):
            return "star_market"
        if digits.startswith("60"):
            return "main_board"
        return "index_or_fund_or_other"
    if prefix == "SZ" and digits.isdigit():
        if digits.startswith("200"):
            return "b_share"
        if digits.startswith(("300", "301", "302")):
            return "chinext"
        if digits.startswith(("000", "001", "002", "003")):
            return "main_board"
        return "index_or_fund_or_other"
    return "unknown"


def calendar_pos(calendar: pd.DatetimeIndex, value: pd.Timestamp, side: str) -> int:
    return int(calendar.searchsorted(pd.Timestamp(value), side=side))


def attach_calendar_bounds(
    instruments: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    start_time: str,
    end_time: Optional[str],
) -> Tuple[pd.DataFrame, int, int]:
    start = pd.Timestamp(start_time)
    end = pd.Timestamp(end_time) if end_time else calendar[-1]
    start_idx = calendar_pos(calendar, start, "left")
    end_idx = calendar_pos(calendar, end, "right") - 1
    if start_idx > end_idx:
        raise ValueError(f"No calendar days in requested window: {start_time} - {end_time}")

    df = instruments.copy()
    df["calendar_start_idx"] = [calendar_pos(calendar, value, "left") for value in df["start_time"]]
    df["calendar_end_idx"] = [calendar_pos(calendar, value, "right") - 1 for value in df["end_time"]]
    df["analysis_start_idx"] = df["calendar_start_idx"].clip(lower=start_idx)
    df["analysis_end_idx"] = df["calendar_end_idx"].clip(upper=end_idx)
    df = df[df["analysis_start_idx"] <= df["analysis_end_idx"]].copy()
    df["active_row_count"] = df["analysis_end_idx"] - df["analysis_start_idx"] + 1
    df["analysis_start_time"] = calendar[df["analysis_start_idx"].to_numpy()]
    df["analysis_end_time"] = calendar[df["analysis_end_idx"].to_numpy()]
    return df, start_idx, end_idx


def feature_file(provider_uri: Path, instrument: str, field: str, freq: str = "day") -> Path:
    return provider_uri / "features" / instrument.lower() / f"{field.lower()}.{freq.lower()}.bin"


def read_feature_slice(
    provider_uri: Path,
    instrument: str,
    field: str,
    start_idx: int,
    end_idx: int,
    freq: str = "day",
) -> FeatureSlice:
    values = np.full(end_idx - start_idx + 1, np.nan, dtype=np.float64)
    path = feature_file(provider_uri, instrument, field, freq=freq)
    if not path.exists():
        return FeatureSlice(values=values, exists=False, storage_start_idx=None, storage_end_idx=None)

    raw = np.fromfile(path, dtype="<f")
    if raw.size <= 1:
        return FeatureSlice(values=values, exists=True, storage_start_idx=None, storage_end_idx=None)

    storage_start = int(raw[0])
    data = raw[1:].astype(np.float64, copy=False)
    storage_end = storage_start + len(data) - 1
    copy_start = max(start_idx, storage_start)
    copy_end = min(end_idx, storage_end)
    if copy_start <= copy_end:
        target_start = copy_start - start_idx
        target_end = copy_end - start_idx + 1
        source_start = copy_start - storage_start
        source_end = copy_end - storage_start + 1
        values[target_start:target_end] = data[source_start:source_end]
    return FeatureSlice(values=values, exists=True, storage_start_idx=storage_start, storage_end_idx=storage_end)


def discover_field_file_counts(provider_uri: Path, freq: str) -> Dict[str, int]:
    feature_root = provider_uri / "features"
    counts: Dict[str, int] = {}
    if not feature_root.exists():
        return counts
    suffix = f".{freq}.bin"
    for inst_dir in feature_root.iterdir():
        if not inst_dir.is_dir():
            continue
        for file in inst_dir.glob(f"*{suffix}"):
            field = file.name[: -len(suffix)].lower()
            counts[field] = counts.get(field, 0) + 1
    return counts


def empty_field_stats(fields: Iterable[str]) -> Dict[str, Dict[str, object]]:
    return {
        field: {
            "file_instruments": 0,
            "nonnull_instruments": 0,
            "nonnull_rows": 0,
            "latest_idx": None,
        }
        for field in fields
    }


def pct(value: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(value / denominator, 6)


def count_instruments(mask: pd.Series) -> int:
    return int(mask.sum())


def add_summary_row(
    rows: List[Dict[str, object]],
    rule_id: str,
    rule_name: str,
    implementation: str,
    uses_proxy: bool,
    matched_rows: int,
    removed_rows: int,
    matched_instruments: int,
    scope: str,
    notes: str,
):
    rows.append(
        {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "implementation": implementation,
            "uses_proxy": uses_proxy,
            "matched_rows_before_any_filter": int(matched_rows),
            "removed_rows_sequential": int(removed_rows),
            "matched_instruments": int(matched_instruments),
            "scope": scope,
            "notes": notes,
        }
    )


def process_filters(
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    instruments: pd.DataFrame,
    freq: str,
    first_days: int,
    min_history_days: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Dict[str, object]]]:
    field_stats = empty_field_stats(CORE_FIELDS)
    filter_totals: Dict[str, Dict[str, int]] = {
        "missing_required": {"matched_rows": 0, "removed_rows": 0, "matched_instruments": 0},
        "first_days": {"matched_rows": 0, "removed_rows": 0, "matched_instruments": 0},
        "listed_lt_min_history": {"matched_rows": 0, "removed_rows": 0, "matched_instruments": 0},
        "resume_first_day_proxy": {"matched_rows": 0, "removed_rows": 0, "matched_instruments": 0},
        "one_word_limit_like_proxy": {"matched_rows": 0, "removed_rows": 0, "matched_instruments": 0},
    }
    board_rows: Dict[str, Dict[str, object]] = {}

    for _, row in instruments.iterrows():
        board = row["board"]
        board_entry = board_rows.setdefault(
            board,
            {
                "board": board,
                "instrument_count": 0,
                "active_instrument_count": 0,
                "stock_like": board in ALLOWED_BOARDS,
                "active_rows": 0,
                "tradable_rows": 0,
                "stage1_remaining_rows": 0,
                "first_trade_date": None,
                "last_trade_date": None,
                "first_instrument_start": None,
                "last_instrument_end": None,
            },
        )
        board_entry["instrument_count"] = int(board_entry["instrument_count"]) + 1
        board_entry["active_instrument_count"] = int(board_entry["active_instrument_count"]) + 1
        board_entry["active_rows"] = int(board_entry["active_rows"]) + int(row["active_row_count"])
        board_entry["first_instrument_start"] = min_timestamp(board_entry["first_instrument_start"], row["start_time"])
        board_entry["last_instrument_end"] = max_timestamp(board_entry["last_instrument_end"], row["end_time"])

        if board not in ALLOWED_BOARDS:
            continue

        instrument = row["instrument"]
        active_start = int(row["analysis_start_idx"])
        active_end = int(row["analysis_end_idx"])
        full_start = int(row["calendar_start_idx"])
        full_end = active_end
        active_len = active_end - active_start + 1

        full_close = read_feature_slice(provider_uri, instrument, "close", full_start, full_end, freq=freq)
        full_volume = read_feature_slice(provider_uri, instrument, "volume", full_start, full_end, freq=freq)
        full_tradable = np.isfinite(full_close.values) & np.isfinite(full_volume.values) & (full_volume.values > 0)
        age_full = np.cumsum(full_tradable.astype(np.int64))
        offset = active_start - full_start
        tradable = full_tradable[offset : offset + active_len]
        trading_age = age_full[offset : offset + active_len]
        prev_tradable = np.r_[False, full_tradable[:-1]][offset : offset + active_len]

        board_entry["tradable_rows"] = int(board_entry["tradable_rows"]) + int(tradable.sum())
        if tradable.any():
            local_dates = calendar[active_start : active_end + 1][tradable]
            board_entry["first_trade_date"] = min_timestamp(board_entry["first_trade_date"], local_dates[0])
            board_entry["last_trade_date"] = max_timestamp(board_entry["last_trade_date"], local_dates[-1])

        slices: Dict[str, FeatureSlice] = {
            "close": FeatureSlice(
                values=full_close.values[offset : offset + active_len],
                exists=full_close.exists,
                storage_start_idx=active_start,
                storage_end_idx=active_end,
            ),
            "volume": FeatureSlice(
                values=full_volume.values[offset : offset + active_len],
                exists=full_volume.exists,
                storage_start_idx=active_start,
                storage_end_idx=active_end,
            ),
        }
        for field in CORE_FIELDS:
            if field in slices:
                continue
            slices[field] = read_feature_slice(provider_uri, instrument, field, active_start, active_end, freq=freq)

        for field, data in slices.items():
            update_field_stats_with_base(stats=field_stats, field=field, data=data, base_idx=active_start)

        required_missing = np.zeros(active_len, dtype=bool)
        for field in REQUIRED_FIELDS:
            values = slices[field].values
            required_missing |= ~np.isfinite(values)
        required_missing |= slices["volume"].values <= 0

        first_days_mask = tradable & (trading_age > 0) & (trading_age <= first_days)
        listed_lt_min_history = tradable & (trading_age > first_days) & (trading_age <= min_history_days)
        resume_first_day = tradable & (~prev_tradable) & (trading_age > first_days)
        one_word_limit_like = compute_one_word_limit_like(
            open_=slices["open"].values,
            high=slices["high"].values,
            low=slices["low"].values,
            close=slices["close"].values,
            change=slices["change"].values,
            board=board,
        )

        remaining = np.ones(active_len, dtype=bool)
        for rule_key, mask in (
            ("missing_required", required_missing),
            ("first_days", first_days_mask),
            ("listed_lt_min_history", listed_lt_min_history),
            ("resume_first_day_proxy", resume_first_day),
            ("one_word_limit_like_proxy", one_word_limit_like),
        ):
            matched = int(mask.sum())
            removed = int((remaining & mask).sum())
            filter_totals[rule_key]["matched_rows"] += matched
            filter_totals[rule_key]["removed_rows"] += removed
            if matched > 0:
                filter_totals[rule_key]["matched_instruments"] += 1
            remaining &= ~mask
        board_entry["stage1_remaining_rows"] = int(board_entry["stage1_remaining_rows"]) + int(remaining.sum())

    universe_by_board = pd.DataFrame(board_rows.values())
    for col in ("first_trade_date", "last_trade_date", "first_instrument_start", "last_instrument_end"):
        if col in universe_by_board:
            universe_by_board[col] = pd.to_datetime(universe_by_board[col]).dt.strftime("%Y-%m-%d")

    rows = build_filter_summary_rows(instruments, filter_totals)
    return pd.DataFrame(rows), universe_by_board.sort_values("board"), field_stats


def update_field_stats_with_base(
    stats: Dict[str, Dict[str, object]],
    field: str,
    data: FeatureSlice,
    base_idx: int,
):
    if field not in stats:
        return
    if data.exists:
        stats[field]["file_instruments"] = int(stats[field]["file_instruments"]) + 1
    valid = np.isfinite(data.values)
    if valid.any():
        stats[field]["nonnull_instruments"] = int(stats[field]["nonnull_instruments"]) + 1
        stats[field]["nonnull_rows"] = int(stats[field]["nonnull_rows"]) + int(valid.sum())
        latest_idx = base_idx + int(np.flatnonzero(valid)[-1])
        existing = stats[field]["latest_idx"]
        stats[field]["latest_idx"] = latest_idx if existing is None else max(int(existing), latest_idx)


def min_timestamp(current: Optional[pd.Timestamp], value: pd.Timestamp) -> pd.Timestamp:
    value = pd.Timestamp(value)
    if current is None or value < pd.Timestamp(current):
        return value
    return pd.Timestamp(current)


def max_timestamp(current: Optional[pd.Timestamp], value: pd.Timestamp) -> pd.Timestamp:
    value = pd.Timestamp(value)
    if current is None or value > pd.Timestamp(current):
        return value
    return pd.Timestamp(current)


def compute_one_word_limit_like(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    change: np.ndarray,
    board: str,
) -> np.ndarray:
    limit = BOARD_LIMITS.get(board)
    if limit is None:
        return np.zeros_like(close, dtype=bool)
    all_prices = np.vstack([open_, high, low, close])
    price_ok = np.all(np.isfinite(all_prices), axis=0)
    max_price = np.full(close.shape, np.nan, dtype=np.float64)
    min_price = np.full(close.shape, np.nan, dtype=np.float64)
    if price_ok.any():
        max_price[price_ok] = np.max(all_prices[:, price_ok], axis=0)
        min_price[price_ok] = np.min(all_prices[:, price_ok], axis=0)
    flat_bar = price_ok & (max_price - min_price <= np.maximum(close, 1e-12) * 1e-4)
    near_limit = np.isfinite(change) & (change >= limit * 0.98)
    return flat_bar & near_limit


def build_filter_summary_rows(
    instruments: pd.DataFrame,
    filter_totals: Dict[str, Dict[str, int]],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    total_rows = int(instruments["active_row_count"].sum())
    add_summary_row(
        rows,
        "00_initial_active_rows",
        "统计窗口内标的-交易日行数",
        "implemented",
        False,
        total_rows,
        0,
        int(len(instruments)),
        "all instruments in market file",
        "按标的有效区间与请求交易日窗口的交集统计。",
    )
    b_share_mask = instruments["board"] == "b_share"
    b_share_rows = int(instruments.loc[b_share_mask, "active_row_count"].sum())
    add_summary_row(
        rows,
        "01_exclude_b_share",
        "剔除 B 股标的",
        "implemented",
        True,
        b_share_rows,
        b_share_rows,
        count_instruments(b_share_mask),
        "all instruments in market file",
        "板块用代码前缀代理识别：SH900*/SZ200*。",
    )
    non_stock_mask = ~instruments["board"].isin(ALLOWED_BOARDS | {"b_share"})
    non_stock_rows = int(instruments.loc[non_stock_mask, "active_row_count"].sum())
    add_summary_row(
        rows,
        "02_exclude_index_fund_other",
        "剔除指数、基金和其他非普通股标的",
        "implemented",
        True,
        non_stock_rows,
        non_stock_rows,
        count_instruments(non_stock_mask),
        "all instruments in market file",
        "all.txt 股票池包含 SZ399* 等指数类代码，阶段 1 不纳入普通 A 股样本。",
    )

    rule_meta = [
        (
            "03_missing_required_or_not_tradable",
            "跳过必需 OHLCV/factor 缺失或成交量 <= 0 的日期",
            "implemented",
            True,
            "missing_required",
            "allowed stock-like boards",
            "停牌和不可交易状态用 close/volume 缺失或 volume <= 0 代理。",
        ),
        (
            "04_new_stock_first_5_trading_days",
            "剔除首次有效行情后的前 5 个交易日",
            "implemented",
            True,
            "first_days",
            "allowed stock-like boards",
            "上市交易年龄用本地 Qlib 首个有效 OHLCV 观测日代理。",
        ),
        (
            "05_listed_less_than_250_trading_days",
            "剔除交易年龄 <= 250 日的样本",
            "implemented",
            True,
            "listed_lt_min_history",
            "allowed stock-like boards",
            "上市日期用本地 Qlib 首个有效 OHLCV 观测日代理。",
        ),
        (
            "06_resume_first_day",
            "跳过前一交易日不可交易后的首个可交易日",
            "implemented",
            True,
            "resume_first_day_proxy",
            "allowed stock-like boards",
            "复牌首日用前一交易日不可交易代理。",
        ),
        (
            "07_one_word_limit_like",
            "跳过近似一字涨停日线",
            "implemented",
            True,
            "one_word_limit_like_proxy",
            "allowed stock-like boards",
            "缺少 high_limit/low_limit 字段时，用 OHLC 近似相等和板块涨幅阈值代理。",
        ),
    ]
    for rule_id, name, implementation, uses_proxy, key, scope, notes in rule_meta:
        totals = filter_totals[key]
        add_summary_row(
            rows,
            rule_id,
            name,
            implementation,
            uses_proxy,
            totals["matched_rows"],
            totals["removed_rows"],
            totals["matched_instruments"],
            scope,
            notes,
        )

    not_implemented = [
        (
            "08_st_delisting_status",
            "剔除 ST/*ST/退市整理样本",
            "not_implemented",
            False,
            "本地 Qlib 日线包没有证券名称或状态历史。",
        ),
        (
            "09_strict_limit_open_after_consecutive_one_word",
            "跳过连续一字涨停后首次打开日",
            "partial_not_strict",
            True,
            "规则 07 只代理当日一字涨停形态；缺少涨跌停价字段时无法严格识别连续一字板打开。",
        ),
        (
            "10_ex_right_step_unfixed",
            "跳过复权无法修正的除权除息价格台阶异常",
            "not_implemented",
            False,
            "阶段 1 仅盘点 factor 可用性，尚未检测全部公司行为价格台阶异常。",
        ),
    ]
    for rule_id, name, implementation, uses_proxy, notes in not_implemented:
        add_summary_row(
            rows,
            rule_id,
            name,
            implementation,
            uses_proxy,
            0,
            0,
            0,
            "documented limitation",
            notes,
        )

    remaining = total_rows
    for row in rows:
        remaining -= int(row["removed_rows_sequential"])
        row["remaining_rows_after_rule"] = remaining
    return rows


def build_data_inventory(
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    instruments: pd.DataFrame,
    active_instruments: pd.DataFrame,
    field_file_counts: Dict[str, int],
    field_stats: Dict[str, Dict[str, object]],
    start_idx: int,
    end_idx: int,
) -> pd.DataFrame:
    total_active = int(len(active_instruments))
    allowed_active = int(active_instruments["board"].isin(ALLOWED_BOARDS).sum())
    rows: List[Dict[str, object]] = []

    def add(
        section: str,
        item: str,
        required_level: str,
        qlib_source: str,
        status: str,
        coverage_n: int,
        total_n: int,
        latest_idx: Optional[int],
        notes: str,
    ):
        rows.append(
            {
                "section": section,
                "item": item,
                "required_level": required_level,
                "qlib_source": qlib_source,
                "status": status,
                "coverage_n": int(coverage_n),
                "total_n": int(total_n),
                "coverage_pct": pct(int(coverage_n), int(total_n)),
                "latest_available_date": "" if latest_idx is None else calendar[int(latest_idx)].strftime("%Y-%m-%d"),
                "analysis_start": calendar[start_idx].strftime("%Y-%m-%d"),
                "analysis_end": calendar[end_idx].strftime("%Y-%m-%d"),
                "notes": notes,
            }
        )

    add(
        "dataset",
        "calendar",
        "required",
        "calendars/day.txt",
        "available",
        len(calendar),
        len(calendar),
        len(calendar) - 1,
        f"数据路径：{provider_uri}",
    )
    add(
        "dataset",
        "instrument_pool",
        "required",
        "instruments/all.txt or selected market file",
        "available",
        total_active,
        int(len(instruments)),
        end_idx,
        f"统计窗口内活跃标的 {total_active} 个；代码前缀识别的 A 股股票类标的 {allowed_active} 个。",
    )
    add(
        "field",
        "trade_date",
        "required",
        "datetime index",
        "available",
        len(calendar[start_idx : end_idx + 1]),
        len(calendar[start_idx : end_idx + 1]),
        end_idx,
        "由 Qlib 日线交易日历派生。",
    )
    add(
        "field",
        "code",
        "required",
        "instrument index",
        "available",
        total_active,
        total_active,
        end_idx,
        "由 instruments 文件派生。",
    )

    field_specs = [
        ("open", "required", "$open", "available", "用于 T+1 开盘执行和缺口分析。"),
        ("high", "required", "$high", "available", "用于 ATR 和日内振幅。"),
        ("low", "required", "$low", "available", "用于 ATR 和止损诊断。"),
        ("close", "required", "$close", "available", "用于突破识别和收益计算。"),
        ("pre_close", "recommended", "Ref($close, 1)", "derived", "需要时由 close 派生。"),
        ("volume", "required", "$volume", "available", "用于量能确认和停牌代理。"),
        ("amount", "recommended", "$amount", "available", "用于流动性过滤和成交额分位代理。"),
        ("vwap", "recommended", "$vwap", "available", "字段存在时用于 T+1 VWAP 执行情景。"),
        ("adj_factor", "required", "$factor", "available", "用于复权因子可用性盘点。"),
        ("paused", "recommended", "close/volume 缺失或成交量为 0", "proxy", "本地日线包没有显式 paused 字段。"),
        ("high_limit", "recommended", "", "missing", "本地日线包没有 high_limit 字段。"),
        ("low_limit", "recommended", "", "missing", "本地日线包没有 low_limit 字段。"),
        ("list_date", "recommended", "首个有效行情日", "proxy", "没有官方 list_date 字段，使用首个有效行情日代理。"),
        ("ST_status", "recommended", "", "missing", "本地日线包没有历史 ST/名称/证券状态字段。"),
        ("board", "recommended", "instrument 代码前缀", "proxy", "板块由 SH/SZ/BJ 代码前缀推断。"),
    ]
    for item, required_level, source, default_status, notes in field_specs:
        if item == "pre_close":
            close_stats = field_stats["close"]
            add("field", item, required_level, source, "derived", close_stats["nonnull_instruments"], allowed_active, close_stats["latest_idx"], notes)
            continue
        if item == "paused":
            close_stats = field_stats["close"]
            add("field", item, required_level, source, "proxy", close_stats["nonnull_instruments"], allowed_active, close_stats["latest_idx"], notes)
            continue
        if item == "list_date":
            add("field", item, required_level, source, "proxy", allowed_active, allowed_active, end_idx, notes)
            continue
        if item == "board":
            add("field", item, required_level, source, "proxy", allowed_active, allowed_active, end_idx, notes)
            continue
        field = "factor" if item == "adj_factor" else item
        if field in field_stats:
            stats = field_stats[field]
            add(
                "field",
                item,
                required_level,
                source,
                default_status,
                int(stats["nonnull_instruments"]),
                allowed_active,
                stats["latest_idx"],
                f"{notes} 全部 feature 目录中的该字段文件数：{field_file_counts.get(field, 0)}。",
            )
        else:
            add("field", item, required_level, source, default_status, 0, allowed_active, None, notes)

    return pd.DataFrame(rows)


def localize_data_inventory(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["section"] = out["section"].map({"dataset": "数据集", "field": "字段"}).fillna(out["section"])
    out["item"] = out["item"].map(
        {
            "calendar": "交易日历",
            "instrument_pool": "标的池",
            "trade_date": "交易日期",
            "code": "股票代码",
            "open": "开盘价",
            "high": "最高价",
            "low": "最低价",
            "close": "收盘价",
            "pre_close": "前收盘价",
            "volume": "成交量",
            "amount": "成交额",
            "vwap": "VWAP",
            "adj_factor": "复权因子",
            "paused": "停牌状态",
            "high_limit": "涨停价",
            "low_limit": "跌停价",
            "list_date": "上市日期",
            "ST_status": "ST 状态",
            "board": "板块",
        }
    ).fillna(out["item"])
    out["qlib_source"] = out["qlib_source"].map(
        {
            "instruments/all.txt or selected market file": "instruments/all.txt 或指定股票池文件",
            "datetime index": "datetime 索引",
            "instrument index": "instrument 索引",
        }
    ).fillna(out["qlib_source"])
    out["required_level"] = out["required_level"].map({"required": "必需", "recommended": "建议"}).fillna(
        out["required_level"]
    )
    out["status"] = out["status"].map({"available": "可用", "derived": "可派生", "proxy": "代理实现", "missing": "缺失"}).fillna(
        out["status"]
    )
    return out.rename(
        columns={
            "section": "分类",
            "item": "项目",
            "required_level": "必需性",
            "qlib_source": "Qlib来源",
            "status": "状态",
            "coverage_n": "覆盖数量",
            "total_n": "总数",
            "coverage_pct": "覆盖率",
            "latest_available_date": "最新可用日期",
            "analysis_start": "统计开始",
            "analysis_end": "统计结束",
            "notes": "说明",
        }
    )


def localize_filter_summary(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["implementation"] = out["implementation"].map(
        {
            "implemented": "已实现",
            "not_implemented": "未实现",
            "partial_not_strict": "部分实现但不严格",
        }
    ).fillna(out["implementation"])
    out["uses_proxy"] = out["uses_proxy"].map({True: "是", False: "否"})
    out["scope"] = out["scope"].map(
        {
            "all instruments in market file": "市场文件全部标的",
            "allowed stock-like boards": "股票类板块",
            "documented limitation": "已记录限制",
        }
    ).fillna(out["scope"])
    return out.rename(
        columns={
            "rule_id": "规则ID",
            "rule_name": "规则名称",
            "implementation": "实现状态",
            "uses_proxy": "是否代理",
            "matched_rows_before_any_filter": "规则匹配行数_未去重",
            "removed_rows_sequential": "顺序剔除行数",
            "matched_instruments": "匹配标的数",
            "scope": "适用范围",
            "notes": "说明",
            "remaining_rows_after_rule": "规则后剩余行数",
        }
    )


def localize_universe_by_board(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["board"] = out["board"].map(BOARD_CN).fillna(out["board"])
    out["stock_like"] = out["stock_like"].map({True: "是", False: "否"})
    return out.rename(
        columns={
            "board": "板块",
            "instrument_count": "标的数",
            "active_instrument_count": "活跃标的数",
            "stock_like": "是否股票类",
            "active_rows": "活跃标的日期行数",
            "tradable_rows": "可交易行数",
            "stage1_remaining_rows": "阶段1剩余行数",
            "first_trade_date": "首个交易日",
            "last_trade_date": "最新交易日",
            "first_instrument_start": "首个标的开始日",
            "last_instrument_end": "最新标的结束日",
        }
    )


def write_outputs(
    output_dir: Path,
    data_inventory: pd.DataFrame,
    filter_summary: pd.DataFrame,
    universe_by_board: pd.DataFrame,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    localize_data_inventory(data_inventory).to_csv(output_dir / "data_inventory.csv", index=False)
    localize_filter_summary(filter_summary).to_csv(output_dir / "sample_filter_summary.csv", index=False)
    localize_universe_by_board(universe_by_board).to_csv(output_dir / "universe_by_board.csv", index=False)


def main():
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
    field_file_counts = discover_field_file_counts(provider_uri, freq=args.freq)
    filter_summary, universe_by_board, field_stats = process_filters(
        provider_uri=provider_uri,
        calendar=calendar,
        instruments=active_instruments,
        freq=args.freq,
        first_days=args.first_days,
        min_history_days=args.min_history_days,
    )
    data_inventory = build_data_inventory(
        provider_uri=provider_uri,
        calendar=calendar,
        instruments=instruments,
        active_instruments=active_instruments,
        field_file_counts=field_file_counts,
        field_stats=field_stats,
        start_idx=start_idx,
        end_idx=end_idx,
    )
    output_dir = Path(args.output_dir)
    write_outputs(output_dir, data_inventory, filter_summary, universe_by_board)

    print(f"数据路径={provider_uri}")
    print(f"统计窗口={calendar[start_idx].date()}..{calendar[end_idx].date()}")
    print(f"活跃标的数={len(active_instruments)}")
    print(f"输出目录={output_dir.resolve()}")
    print(f"生成时间={dt.datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
