#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""A 股日线突破研究阶段 5：事件研究统计与可视化报告。"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover - plotting is optional for headless/minimal envs
    plt = None

try:
    from scipy.stats import ks_2samp
except Exception:  # pragma: no cover - scipy may be absent in a minimal env
    ks_2samp = None

try:
    from .breakout_events import rolling_current_mean
    from .data_inventory import provider_path, read_calendar, read_feature_slice
except ImportError:  # pragma: no cover - enables `python examples/.../event_study.py`
    from breakout_events import rolling_current_mean  # type: ignore
    from data_inventory import provider_path, read_calendar, read_feature_slice  # type: ignore


DEFAULT_PROVIDER_URI = "~/.qlib/qlib_data/cn_data"
DEFAULT_OUTPUT_DIR = "examples/a_share_breakout/outputs"
DEFAULT_BREAKOUT_WINDOWS = (60, 120)
DEFAULT_BENCHMARK = "SH000300"
DEFAULT_HORIZON = 20

LABEL_CN = {
    "true_breakout": "真突破",
    "false_breakout": "假突破",
    "ambiguous": "不确定",
}
LABEL_PLOT = {
    "true_breakout": "True breakout",
    "false_breakout": "False breakout",
    "ambiguous": "Ambiguous",
}
GROUP_CN = {"low": "低", "mid": "中", "high": "高", "missing": "缺失", "unknown": "未知"}
GROUP_PLOT = {"low": "Low", "mid": "Mid", "high": "High", "missing": "Missing"}

FEATURE_SPECS = [
    ("breakout_strength_atr", "突破强度(ATR)"),
    ("vol_ratio_20", "单日量比"),
    ("vol_ratio_3d", "3日量能持续性"),
    ("amount_rank_252", "成交额/成交量252日分位"),
    ("atr_pct", "ATR%"),
    ("relative_strength_20d", "20日相对强弱"),
    ("bb_width_rank_252", "布林带宽252日分位"),
    ("fake_prob_daily_t", "T日可见日线失真概率"),
    ("limit_dependency_score", "涨停依赖代理"),
    ("volume_spike_no_persistence", "单日量突刺不持续"),
    ("next_open_return_research", "T+1开盘收益(研究用)"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-uri", default=DEFAULT_PROVIDER_URI, help="Qlib 日线数据根目录。")
    parser.add_argument("--freq", default="day", choices=["day"], help="Qlib 二进制数据频率。")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="阶段 2/3 输入和阶段 5 输出目录。")
    parser.add_argument(
        "--breakout-windows",
        nargs="+",
        type=int,
        default=list(DEFAULT_BREAKOUT_WINDOWS),
        help="突破窗口列表，默认读取 60 和 120 日事件。",
    )
    parser.add_argument("--feature-matrix", default=None, help="阶段 3 feature_matrix_daily.csv/parquet 路径。")
    parser.add_argument("--benchmark-instrument", default=DEFAULT_BENCHMARK, help="市场环境基准指数代码。")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON, help="事件后收益曲线窗口。")
    parser.add_argument("--csv-chunksize", type=int, default=500_000, help="读取大型特征 CSV 的 chunksize。")
    parser.add_argument("--skip-figures", action="store_true", help="只生成表格和 Markdown，不画图。")
    return parser.parse_args()


def read_event_tables(output_dir: Path, windows: Iterable[int]) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for window in windows:
        base = output_dir / f"breakout_events_{int(window)}d"
        path = base.with_suffix(".parquet") if base.with_suffix(".parquet").exists() else base.with_suffix(".csv")
        if not path.exists():
            raise FileNotFoundError(f"missing event table for {window}d: {path}")
        frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        frame["event_date"] = pd.to_datetime(frame["event_date"])
        frame["breakout_window"] = int(window)
        frames.append(frame)
    if not frames:
        raise ValueError("no breakout windows were provided")
    return pd.concat(frames, ignore_index=True).sort_values(["breakout_window", "event_date", "instrument"])


def assign_tertile(values: pd.Series) -> pd.Series:
    out = pd.Series("missing", index=values.index, dtype=object)
    valid = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if valid.empty:
        return out
    if valid.nunique() < 3:
        out.loc[valid.index] = "mid"
        return out
    ranked = valid.rank(method="first")
    out.loc[valid.index] = pd.qcut(ranked, q=3, labels=["low", "mid", "high"]).astype(str)
    return out


def load_event_feature_rows(
    feature_path: Path,
    events: pd.DataFrame,
    windows: Sequence[int],
    chunksize: int,
) -> Tuple[pd.DataFrame, List[str]]:
    if not feature_path.exists():
        return pd.DataFrame(columns=["datetime", "instrument"]), []
    if feature_path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq

            header = pd.Index(pq.ParquetFile(feature_path).schema.names)
        except Exception:
            header = pd.read_parquet(feature_path).columns
    else:
        header = pd.read_csv(feature_path, nrows=0).columns
    wanted = [
        "datetime",
        "instrument",
        "relative_strength_20d",
        "bb_width_rank_252",
        "atr_noise_rank_252",
        "limit_dependency_score",
        "volume_spike_no_persistence",
        "next_open_return_research",
    ]
    for window in windows:
        wanted.extend([f"fake_prob_daily_t_{window}d", f"fake_prob_daily_research_{window}d"])
    usecols = [column for column in wanted if column in set(header)]
    if not {"datetime", "instrument"}.issubset(usecols):
        return pd.DataFrame(columns=["datetime", "instrument"]), []

    keys = events[["event_date", "instrument"]].drop_duplicates().rename(columns={"event_date": "datetime"})
    keys["datetime"] = pd.to_datetime(keys["datetime"])
    if feature_path.suffix == ".parquet":
        features = pd.read_parquet(feature_path, columns=usecols)
        features["datetime"] = pd.to_datetime(features["datetime"])
        return keys.merge(features, on=["datetime", "instrument"], how="inner"), usecols

    chunks: List[pd.DataFrame] = []
    for chunk in pd.read_csv(feature_path, usecols=usecols, parse_dates=["datetime"], chunksize=chunksize):
        matched = keys.merge(chunk, on=["datetime", "instrument"], how="inner")
        if not matched.empty:
            chunks.append(matched)
    if not chunks:
        return pd.DataFrame(columns=usecols), usecols
    return pd.concat(chunks, ignore_index=True).drop_duplicates(["datetime", "instrument"]), usecols


def attach_event_features(events: pd.DataFrame, feature_rows: pd.DataFrame, windows: Sequence[int]) -> pd.DataFrame:
    if feature_rows.empty:
        events = events.copy()
    else:
        events = events.merge(
            feature_rows.rename(columns={"datetime": "event_date"}),
            on=["event_date", "instrument"],
            how="left",
        )
    for target, prefix in [
        ("fake_prob_daily_t", "fake_prob_daily_t"),
        ("fake_prob_daily_research", "fake_prob_daily_research"),
    ]:
        events[target] = np.nan
        for window in windows:
            source = f"{prefix}_{window}d"
            if source in events.columns:
                mask = events["breakout_window"].eq(window)
                events.loc[mask, target] = events.loc[mask, source]
    return events


def read_market_environment(
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    events: pd.DataFrame,
    benchmark: str,
    freq: str,
) -> pd.DataFrame:
    event_idx = calendar.get_indexer(pd.to_datetime(events["event_date"].drop_duplicates()).sort_values())
    event_idx = event_idx[event_idx >= 0]
    if len(event_idx) == 0:
        return pd.DataFrame(columns=["event_date", "benchmark_ma60_state", "market_amount_state"])
    start_idx = max(0, int(event_idx.min()) - 80)
    end_idx = int(event_idx.max())
    close = read_feature_slice(provider_uri, benchmark, "close", start_idx, end_idx, freq=freq)
    if not close.exists or not np.isfinite(close.values).any():
        dates = calendar[event_idx]
        return pd.DataFrame(
            {"event_date": dates, "benchmark_ma60_state": "unknown", "market_amount_state": "unknown"}
        )
    amount = read_feature_slice(provider_uri, benchmark, "amount", start_idx, end_idx, freq=freq)
    ma60 = rolling_current_mean(close.values, 60)
    amount20 = rolling_current_mean(amount.values, 20) if amount.exists else np.full(len(close.values), np.nan)
    amount60 = rolling_current_mean(amount.values, 60) if amount.exists else np.full(len(close.values), np.nan)
    local = event_idx - start_idx
    ma_known = np.isfinite(close.values[local]) & np.isfinite(ma60[local])
    up = ma_known & (close.values[local] >= ma60[local])
    amount_expanding = np.isfinite(amount20[local]) & np.isfinite(amount60[local]) & (amount20[local] >= amount60[local])
    amount_known = np.isfinite(amount20[local]) & np.isfinite(amount60[local])
    return pd.DataFrame(
        {
            "event_date": calendar[event_idx],
            "benchmark_ma60_state": np.where(ma_known, np.where(up, "above_ma60", "below_ma60"), "unknown"),
            "market_amount_state": np.where(amount_known, np.where(amount_expanding, "expanding", "contracting"), "unknown"),
        }
    )


def enrich_for_segments(events: pd.DataFrame, market_env: pd.DataFrame) -> pd.DataFrame:
    out = events.merge(market_env, on="event_date", how="left") if not market_env.empty else events.copy()
    out["year"] = out["event_date"].dt.year.astype(str)
    out["amount_rank_group"] = assign_tertile(out["amount_rank_252"])
    out["atr_pct_group"] = assign_tertile(out["atr_pct"])
    out["fake_prob_group"] = assign_tertile(out.get("fake_prob_daily_t", pd.Series(index=out.index, dtype=float)))
    out["bb_width_group"] = assign_tertile(out.get("bb_width_rank_252", pd.Series(index=out.index, dtype=float)))
    out["trend_strength_group"] = assign_tertile(out["breakout_strength_atr"])
    if "benchmark_ma60_state" not in out.columns:
        out["benchmark_ma60_state"] = "unknown"
    if "market_amount_state" not in out.columns:
        out["market_amount_state"] = "unknown"
    out["benchmark_ma60_state"] = out["benchmark_ma60_state"].fillna("unknown")
    out["market_amount_state"] = out["market_amount_state"].fillna("unknown")
    return out


def summarize_labels(events: pd.DataFrame) -> pd.DataFrame:
    summary = events.groupby(["breakout_window", "label"]).size().reset_index(name="count")
    totals = summary.groupby("breakout_window")["count"].transform("sum")
    summary["share"] = summary["count"] / totals
    summary["label_cn"] = summary["label"].map(LABEL_CN).fillna(summary["label"])
    return summary.sort_values(["breakout_window", "label"])


def summarize_segments(events: pd.DataFrame) -> pd.DataFrame:
    segment_cols = [
        ("board", "板块"),
        ("year", "年份"),
        ("benchmark_ma60_state", "指数MA60状态"),
        ("market_amount_state", "市场成交额状态"),
        ("amount_rank_group", "流动性分组"),
        ("atr_pct_group", "波动分组"),
        ("bb_width_group", "布林带宽分组"),
        ("fake_prob_group", "失真概率分组"),
    ]
    rows: List[Dict[str, object]] = []
    for column, section_cn in segment_cols:
        if column not in events.columns:
            continue
        grouped = events.groupby(["breakout_window", column, "label"], dropna=False).size().unstack(fill_value=0)
        for (window, value), counts in grouped.iterrows():
            true_count = int(counts.get("true_breakout", 0))
            false_count = int(counts.get("false_breakout", 0))
            ambiguous_count = int(counts.get("ambiguous", 0))
            labeled = true_count + false_count
            rows.append(
                {
                    "breakout_window": int(window),
                    "section": column,
                    "section_cn": section_cn,
                    "segment": str(value),
                    "events": int(counts.sum()),
                    "true_breakout": true_count,
                    "false_breakout": false_count,
                    "ambiguous": ambiguous_count,
                    "true_rate_labeled": true_count / labeled if labeled else np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values(["breakout_window", "section", "segment"])


def rank_auc(pos: np.ndarray, neg: np.ndarray) -> float:
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    values = pd.Series(np.r_[pos, neg])
    ranks = values.rank(method="average").to_numpy()
    n_pos = len(pos)
    return float((ranks[:n_pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * len(neg)))


def add_bh_q_values(frame: pd.DataFrame, p_col: str = "ks_p_value") -> pd.DataFrame:
    out = frame.copy()
    out["ks_q_value"] = np.nan
    for window, idx in out.groupby("breakout_window").groups.items():
        pvals = out.loc[idx, p_col].astype(float)
        valid = pvals.replace([np.inf, -np.inf], np.nan).dropna().sort_values()
        if valid.empty:
            continue
        m = len(valid)
        prev = 1.0
        adjusted: Dict[int, float] = {}
        for rank, (row_idx, pval) in enumerate(valid.iloc[::-1].items(), start=1):
            bh_rank = m - rank + 1
            prev = min(prev, float(pval) * m / bh_rank)
            adjusted[row_idx] = prev
        for row_idx, qval in adjusted.items():
            out.at[row_idx, "ks_q_value"] = min(qval, 1.0)
    return out


def compute_feature_diagnostics(events: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    labeled = events[events["label"].isin(["true_breakout", "false_breakout"])]
    for window, window_frame in labeled.groupby("breakout_window"):
        for column, name_cn in FEATURE_SPECS:
            if column not in window_frame.columns:
                continue
            values = pd.to_numeric(window_frame[column], errors="coerce")
            true_values = values[window_frame["label"].eq("true_breakout")].replace([np.inf, -np.inf], np.nan).dropna()
            false_values = values[window_frame["label"].eq("false_breakout")].replace([np.inf, -np.inf], np.nan).dropna()
            if len(true_values) < 20 or len(false_values) < 20:
                continue
            ks_p = float(ks_2samp(true_values, false_values).pvalue) if ks_2samp else np.nan
            auc = rank_auc(true_values.to_numpy(), false_values.to_numpy())
            rows.append(
                {
                    "breakout_window": int(window),
                    "feature": column,
                    "feature_cn": name_cn,
                    "true_mean": float(true_values.mean()),
                    "false_mean": float(false_values.mean()),
                    "median_diff_true_minus_false": float(true_values.median() - false_values.median()),
                    "ks_p_value": ks_p,
                    "true_higher_auc": auc,
                    "directional_auc": max(auc, 1.0 - auc) if np.isfinite(auc) else np.nan,
                    "higher_in_true": bool(auc >= 0.5) if np.isfinite(auc) else np.nan,
                    "n_true": int(len(true_values)),
                    "n_false": int(len(false_values)),
                }
            )
    return add_bh_q_values(pd.DataFrame(rows)) if rows else pd.DataFrame()


def read_close_series_by_instrument(
    provider_uri: Path,
    calendar: pd.DatetimeIndex,
    events: pd.DataFrame,
    horizon: int,
    freq: str,
) -> Dict[str, pd.Series]:
    series_by_instrument: Dict[str, pd.Series] = {}
    for instrument, group in events.groupby("instrument"):
        positions = calendar.get_indexer(pd.to_datetime(group["event_date"]))
        positions = positions[positions >= 0]
        if len(positions) == 0:
            continue
        start_idx = int(positions.min())
        end_idx = min(len(calendar) - 1, int(positions.max()) + horizon)
        close = read_feature_slice(provider_uri, instrument, "close", start_idx, end_idx, freq=freq)
        if close.exists:
            series_by_instrument[instrument] = pd.Series(close.values, index=calendar[start_idx : end_idx + 1])
    return series_by_instrument


def aggregate_forward_returns(
    events: pd.DataFrame,
    close_by_instrument: Mapping[str, pd.Series],
    horizon: int,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    acc: Dict[Tuple[int, str, int], List[float]] = {}
    final_rows: List[Dict[str, object]] = []
    for _, event in events.iterrows():
        close = close_by_instrument.get(event["instrument"])
        if close is None or event["event_date"] not in close.index:
            continue
        pos = close.index.get_loc(event["event_date"])
        if not isinstance(pos, int) or pos + horizon >= len(close):
            continue
        window = close.iloc[pos : pos + horizon + 1].astype(float).to_numpy()
        if not np.isfinite(window).all() or abs(window[0]) <= 1e-12:
            continue
        returns = window / window[0] - 1.0
        breakout_window = int(event["breakout_window"])
        label = str(event["label"])
        for day, value in enumerate(returns):
            acc.setdefault((breakout_window, label, day), [0.0, 0.0])[0] += float(value)
            acc[(breakout_window, label, day)][1] += 1.0
        final_rows.append(
            {
                "breakout_window": breakout_window,
                "label": label,
                "event_date": event["event_date"],
                "forward_return": float(returns[horizon]),
            }
        )
    curve_rows = [
        {
            "breakout_window": window,
            "label": label,
            "relative_day": day,
            "mean_return": sums[0] / sums[1],
            "event_count": int(sums[1]),
        }
        for (window, label, day), sums in acc.items()
        if sums[1] > 0
    ]
    return pd.DataFrame(curve_rows).sort_values(["breakout_window", "label", "relative_day"]), pd.DataFrame(final_rows)


def newey_west_mean_se(values: Sequence[float], max_lag: int) -> float:
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n <= 1:
        return np.nan
    demeaned = x - x.mean()
    lag = min(max_lag, n - 1)
    gamma = float(np.dot(demeaned, demeaned) / n)
    for current_lag in range(1, lag + 1):
        weight = 1.0 - current_lag / (lag + 1.0)
        cov = float(np.dot(demeaned[current_lag:], demeaned[:-current_lag]) / n)
        gamma += 2.0 * weight * cov
    return float(np.sqrt(max(gamma, 0.0) / n))


def summarize_hac(final_returns: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    if final_returns.empty:
        return pd.DataFrame(rows)
    daily = final_returns.groupby(["breakout_window", "label", "event_date"])["forward_return"].mean().reset_index()
    for (window, label), group in daily.groupby(["breakout_window", "label"]):
        values = group.sort_values("event_date")["forward_return"].to_numpy()
        mean = float(np.nanmean(values))
        se = newey_west_mean_se(values, max_lag=horizon)
        rows.append(
            {
                "breakout_window": int(window),
                "label": label,
                "horizon": horizon,
                "mean_forward_return": mean,
                "newey_west_se": se,
                "t_stat": mean / se if np.isfinite(se) and se > 0 else np.nan,
                "event_dates": int(len(values)),
                "events": int(len(final_returns[(final_returns["breakout_window"].eq(window)) & (final_returns["label"].eq(label))])),
            }
        )
    return pd.DataFrame(rows).sort_values(["breakout_window", "label"])


def plot_outputs(output_dir: Path, events: pd.DataFrame, curve: pd.DataFrame, segments: pd.DataFrame) -> List[Path]:
    figure_paths: List[Path] = []
    if plt is None:
        return figure_paths
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    for window, window_curve in curve.groupby("breakout_window"):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        for label, label_frame in window_curve.groupby("label"):
            ax.plot(label_frame["relative_day"], label_frame["mean_return"], label=LABEL_PLOT.get(label, label))
        ax.axhline(0, color="#666666", linewidth=0.8)
        ax.set_title(f"Mean Forward Return after {window}D Breakout")
        ax.set_xlabel("Trading Days after Event")
        ax.set_ylabel("Mean Cumulative Return")
        ax.legend()
        path = figure_dir / f"event_forward_returns_{window}d.png"
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        figure_paths.append(path)

    for window, window_events in events.groupby("breakout_window"):
        heat = window_events[window_events["label"].isin(["true_breakout", "false_breakout"])]
        if {"trend_strength_group", "fake_prob_group"}.issubset(heat.columns) and not heat.empty:
            pivot = heat.pivot_table(
                index="trend_strength_group",
                columns="fake_prob_group",
                values="label",
                aggfunc=lambda s: (s == "true_breakout").sum() / len(s),
            ).reindex(index=["low", "mid", "high"], columns=["low", "mid", "high"])
            fig, ax = plt.subplots(figsize=(5, 4))
            image = ax.imshow(pivot.to_numpy(dtype=float), vmin=0, vmax=1, cmap="RdYlGn")
            ax.set_xticks(range(3), [GROUP_PLOT[x] for x in ["low", "mid", "high"]])
            ax.set_yticks(range(3), [GROUP_PLOT[x] for x in ["low", "mid", "high"]])
            ax.set_xlabel("Fake Probability Tertile")
            ax.set_ylabel("Trend Strength Tertile")
            ax.set_title(f"{window}D True-Breakout Rate")
            fig.colorbar(image, ax=ax, label="True-Breakout Rate")
            path = figure_dir / f"trend_strength_fake_prob_heatmap_{window}d.png"
            fig.tight_layout()
            fig.savefig(path, dpi=150)
            plt.close(fig)
            figure_paths.append(path)

        board_year = segments[(segments["breakout_window"].eq(window)) & (segments["section"].isin(["board", "year"]))]
        fake_prob = segments[(segments["breakout_window"].eq(window)) & (segments["section"].eq("fake_prob_group"))]
        if not fake_prob.empty:
            fig, ax = plt.subplots(figsize=(5.5, 3.5))
            ordered = fake_prob.set_index("segment").reindex(["low", "mid", "high", "missing"]).dropna(how="all")
            ax.bar([GROUP_PLOT.get(str(i), str(i)) for i in ordered.index], ordered["true_rate_labeled"])
            ax.set_ylim(0, 1)
            ax.set_title(f"{window}D True Rate by Fake Probability")
            ax.set_ylabel("True Rate, Ambiguous Excluded")
            path = figure_dir / f"true_rate_by_fake_prob_{window}d.png"
            fig.tight_layout()
            fig.savefig(path, dpi=150)
            plt.close(fig)
            figure_paths.append(path)
        if not board_year.empty:
            board_year.to_csv(figure_dir / f"board_year_segment_data_{window}d.csv", index=False)
    return figure_paths


def markdown_table(frame: pd.DataFrame, columns: Sequence[str], max_rows: int = 20) -> str:
    if frame.empty:
        return "无可用数据。"
    return frame.loc[:, columns].head(max_rows).to_markdown(index=False, floatfmt=".4f")


def stable_feature_summary(feature_diag: pd.DataFrame) -> str:
    if feature_diag.empty:
        return "特征诊断未生成，通常是阶段 3 特征矩阵缺失或真/假样本不足。"
    stable = feature_diag[(feature_diag["directional_auc"] >= 0.56) & (feature_diag["ks_q_value"] <= 0.05)]
    if stable.empty:
        return "未发现同时满足 directional AUC >= 0.56 且 FDR q <= 0.05 的强稳定单变量特征。"
    counts = stable.groupby("feature_cn").agg(windows=("breakout_window", "nunique"), best_auc=("directional_auc", "max"))
    counts = counts.sort_values(["windows", "best_auc"], ascending=False)
    names = [f"{idx}（覆盖 {row.windows} 个窗口，最高AUC {row.best_auc:.3f}）" for idx, row in counts.head(6).iterrows()]
    return "；".join(names) + "。"


def concentration_summary(segments: pd.DataFrame) -> str:
    if segments.empty:
        return "分层统计未生成。"
    lines: List[str] = []
    for section, name in [("year", "年份"), ("board", "板块")]:
        part = segments[(segments["section"].eq(section)) & (segments["true_rate_labeled"].notna())]
        if part.empty:
            continue
        spread = part.groupby("breakout_window")["true_rate_labeled"].agg(["min", "max"]).reset_index()
        details = ", ".join(f"{int(row.breakout_window)}日 {row['min']:.2%}..{row['max']:.2%}" for _, row in spread.iterrows())
        lines.append(f"{name}分层真突破率范围：{details}")
    return "；".join(lines) + "。" if lines else "年份或板块分层缺少足够数据。"


def write_report(
    output_dir: Path,
    events: pd.DataFrame,
    label_summary: pd.DataFrame,
    segments: pd.DataFrame,
    feature_diag: pd.DataFrame,
    curve: pd.DataFrame,
    hac: pd.DataFrame,
    figures: Sequence[Path],
    feature_columns: Sequence[str],
    benchmark: str,
    horizon: int,
) -> Path:
    report = output_dir / "event_study_report.md"
    generated = dt.datetime.now().isoformat(timespec="seconds")
    lines = [
        "# A 股日线突破事件研究报告",
        "",
        f"- 生成时间：{generated}",
        f"- 事件窗口：{events['event_date'].min().date()} 至 {events['event_date'].max().date()}",
        f"- 事件数：{len(events)}",
        f"- 基准指数：`{benchmark}`",
        f"- 未来收益窗口：{horizon} 个交易日",
        f"- 已接入阶段 3 特征列：{', '.join(feature_columns) if feature_columns else '未接入'}",
        "",
        "## 结论摘要",
        "",
        f"- 稳定区分真/假突破的单变量特征：{stable_feature_summary(feature_diag)}",
        f"- 年份/板块集中性检查：{concentration_summary(segments)}",
        "- `fake_prob_daily_t` 只使用 T 日及以前字段；`next_open_return_research` 仅用于事后归因，不可作为交易信号。",
        "- 事件后收益均值的标准误按事件日期聚合后使用 Newey-West HAC，lag 等于未来收益窗口。",
        "",
        "## 标签分布",
        "",
        markdown_table(label_summary, ["breakout_window", "label_cn", "count", "share"]),
        "",
        "## 特征差异诊断",
        "",
        markdown_table(
            feature_diag.sort_values(["breakout_window", "directional_auc"], ascending=[True, False]),
            [
                "breakout_window",
                "feature_cn",
                "true_mean",
                "false_mean",
                "median_diff_true_minus_false",
                "true_higher_auc",
                "directional_auc",
                "ks_q_value",
            ],
            max_rows=30,
        ),
        "",
        "## 分层稳定性",
        "",
        markdown_table(
            segments[segments["section"].isin(["board", "year", "benchmark_ma60_state", "market_amount_state", "fake_prob_group"])],
            ["breakout_window", "section_cn", "segment", "events", "true_breakout", "false_breakout", "ambiguous", "true_rate_labeled"],
            max_rows=50,
        ),
        "",
        "## 20 日收益 HAC 统计",
        "",
        markdown_table(hac, ["breakout_window", "label", "mean_forward_return", "newey_west_se", "t_stat", "event_dates", "events"]),
        "",
        "## 图表",
        "",
    ]
    if figures:
        lines.extend([f"- `{path.relative_to(output_dir)}`" for path in figures])
    else:
        lines.append("- 未生成图表。")
    lines.extend(
        [
            "",
            "## 口径与限制",
            "",
            "- 事件标签来自阶段 2，未来窗口只用于研究统计，不参与阶段 4 交易信号生成。",
            "- 换手率、精确涨跌停价、分钟尾盘、Level-2、资金流和行业分类仍受阶段 3 数据缺口限制。",
            "- 本报告完成事件研究和单变量诊断，不包含 White Reality Check、Hansen SPA 或多策略样本外优选。",
        ]
    )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def write_tables(
    output_dir: Path,
    label_summary: pd.DataFrame,
    segments: pd.DataFrame,
    feature_diag: pd.DataFrame,
    curve: pd.DataFrame,
    hac: pd.DataFrame,
) -> None:
    label_summary.to_csv(output_dir / "event_label_summary.csv", index=False)
    segments.to_csv(output_dir / "event_segment_summary.csv", index=False)
    feature_diag.to_csv(output_dir / "event_feature_diagnostics.csv", index=False)
    curve.to_csv(output_dir / "event_forward_return_curve.csv", index=False)
    hac.to_csv(output_dir / "event_forward_return_hac.csv", index=False)


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    windows = tuple(int(window) for window in args.breakout_windows)
    events = read_event_tables(output_dir, windows)
    feature_path = Path(args.feature_matrix) if args.feature_matrix else output_dir / "feature_matrix_daily.csv"
    feature_rows, feature_columns = load_event_feature_rows(feature_path, events, windows, chunksize=args.csv_chunksize)
    events = attach_event_features(events, feature_rows, windows)

    provider_uri = provider_path(args.provider_uri)
    calendar = read_calendar(provider_uri, freq=args.freq)
    market_env = read_market_environment(provider_uri, calendar, events, args.benchmark_instrument, args.freq)
    events = enrich_for_segments(events, market_env)

    close_by_instrument = read_close_series_by_instrument(provider_uri, calendar, events, args.horizon, args.freq)
    curve, final_returns = aggregate_forward_returns(events, close_by_instrument, args.horizon)
    hac = summarize_hac(final_returns, args.horizon)
    label_summary = summarize_labels(events)
    segments = summarize_segments(events)
    feature_diag = compute_feature_diagnostics(events)
    figures = [] if args.skip_figures else plot_outputs(output_dir, events, curve, segments)
    write_tables(output_dir, label_summary, segments, feature_diag, curve, hac)
    report = write_report(
        output_dir=output_dir,
        events=events,
        label_summary=label_summary,
        segments=segments,
        feature_diag=feature_diag,
        curve=curve,
        hac=hac,
        figures=figures,
        feature_columns=feature_columns,
        benchmark=args.benchmark_instrument,
        horizon=args.horizon,
    )
    print(f"事件数={len(events)}")
    print(f"特征矩阵={feature_path}")
    print(f"报告={report.resolve()}")
    print(f"图表数={len(figures)}")
    print(f"生成时间={dt.datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
