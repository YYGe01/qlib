# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Metrics and audit helpers for stage 6 breakout backtests."""

from __future__ import annotations

from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd

from qlib.contrib.evaluate import risk_analysis
from qlib.utils import flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import PortAnaRecord

from mylib.stage6_config import (
    CostScenario,
    baseline_id,
    build_port_analysis_config,
    infer_board,
    run_id,
)


TRADING_DAYS_PER_YEAR = 238


def _risk_value(analysis_df: pd.DataFrame, section: str, metric: str) -> float:
    try:
        return float(analysis_df.loc[(section, metric), "risk"])
    except KeyError:
        return float("nan")


def _risk_series(values: pd.Series) -> pd.Series:
    return risk_analysis(values.dropna(), freq="day")["risk"]


def _safe_mean(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    return float(clean.mean()) if len(clean) else float("nan")


def _position_weight_dict(position: object) -> Dict[str, float]:
    if hasattr(position, "get_stock_weight_dict"):
        return dict(position.get_stock_weight_dict())
    if isinstance(position, Mapping):
        out: Dict[str, float] = {}
        for code, value in position.items():
            if code in {"cash", "cash_delay", "now_account_value"}:
                continue
            if isinstance(value, Mapping):
                out[str(code)] = float(value.get("weight", 0.0))
        return out
    return {}


def _position_holding_counts(position: object) -> List[float]:
    pos_dict = getattr(position, "position", position)
    if not isinstance(pos_dict, Mapping):
        return []
    counts: List[float] = []
    for code, value in pos_dict.items():
        if code in {"cash", "cash_delay", "now_account_value"} or not isinstance(value, Mapping):
            continue
        count = value.get("count_day")
        if count is not None and np.isfinite(float(count)):
            counts.append(float(count))
    return counts


def summarize_board_exposure(
    positions: object,
    *,
    breakout_window: int,
    deal_price: str,
    scenario: CostScenario,
) -> Tuple[pd.DataFrame, float, float]:
    if not isinstance(positions, Mapping):
        return pd.DataFrame(), float("nan"), float("nan")

    rows: List[Dict[str, object]] = []
    position_counts: List[int] = []
    holding_counts: List[float] = []
    for dt, position in positions.items():
        weights = _position_weight_dict(position)
        position_counts.append(len(weights))
        holding_counts.extend(_position_holding_counts(position))
        board_weights: Dict[str, float] = {}
        for instrument, weight in weights.items():
            board = infer_board(instrument)
            board_weights[board] = board_weights.get(board, 0.0) + float(weight)
        for board, weight in board_weights.items():
            rows.append(
                {
                    "datetime": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                    "breakout_window": breakout_window,
                    "deal_price": deal_price,
                    "cost_scenario": scenario.name,
                    "board": board,
                    "weight": weight,
                }
            )

    board_df = pd.DataFrame(rows)
    if not board_df.empty:
        board_df = (
            board_df.groupby(["breakout_window", "deal_price", "cost_scenario", "board"], as_index=False)
            .agg(avg_weight=("weight", "mean"), max_weight=("weight", "max"), observations=("weight", "size"))
            .sort_values(["breakout_window", "deal_price", "cost_scenario", "board"])
        )
    avg_position_count = float(np.mean(position_counts)) if position_counts else float("nan")
    mean_holding_count = float(np.mean(holding_counts)) if holding_counts else float("nan")
    return board_df, avg_position_count, mean_holding_count


def extract_portfolio_summary(
    *,
    report: pd.DataFrame,
    analysis_df: pd.DataFrame,
    positions: object,
    recorder_path: str,
    pred: pd.DataFrame,
    breakout_window: int,
    deal_price: str,
    scenario: CostScenario,
    backtest_start: str,
    backtest_end: str,
    signal_mode: str,
    active_window: int,
    hold_atr_buffer: float,
    hold_requires_ma: bool,
) -> Tuple[Dict[str, object], pd.DataFrame, pd.DataFrame]:
    net_return = report["return"] - report["cost"]
    excess_net = net_return - report["bench"]
    gross_risk = _risk_series(report["return"])
    net_risk = _risk_series(net_return)
    board_df, avg_position_count, mean_holding_count = summarize_board_exposure(
        positions,
        breakout_window=breakout_window,
        deal_price=deal_price,
        scenario=scenario,
    )

    avg_turnover = _safe_mean(report.get("turnover", pd.Series(dtype=float)))
    summary = {
        "run_id": run_id(breakout_window, deal_price, scenario.name),
        "baseline": baseline_id(breakout_window, deal_price),
        "breakout_window": int(breakout_window),
        "deal_price": deal_price,
        "cost_scenario": scenario.name,
        "cost_label": scenario.label,
        "recorder": recorder_path,
        "pred_rows": int(len(pred)),
        "pred_instruments": int(pred.index.get_level_values("instrument").nunique()),
        "pred_start": pred.index.get_level_values("datetime").min().strftime("%Y-%m-%d"),
        "pred_end": pred.index.get_level_values("datetime").max().strftime("%Y-%m-%d"),
        "backtest_start": backtest_start,
        "backtest_end": backtest_end,
        "signal_mode": signal_mode,
        "active_window": int(active_window),
        "hold_atr_buffer": float(hold_atr_buffer),
        "hold_requires_ma": bool(hold_requires_ma),
        "annualized_return_without_cost": float(gross_risk["annualized_return"]),
        "annualized_return_with_cost": float(net_risk["annualized_return"]),
        "information_ratio_with_cost": float(net_risk["information_ratio"]),
        "max_drawdown_with_cost": float(net_risk["max_drawdown"]),
        "excess_ann_return_without_cost": _risk_value(
            analysis_df, "excess_return_without_cost", "annualized_return"
        ),
        "excess_ann_return_with_cost": _risk_value(analysis_df, "excess_return_with_cost", "annualized_return"),
        "excess_information_ratio_with_cost": _risk_value(
            analysis_df, "excess_return_with_cost", "information_ratio"
        ),
        "excess_max_drawdown_with_cost": _risk_value(analysis_df, "excess_return_with_cost", "max_drawdown"),
        "annualized_cost": float(report["cost"].mean() * TRADING_DAYS_PER_YEAR),
        "cost_drag_excess_ann_return": _risk_value(
            analysis_df, "excess_return_without_cost", "annualized_return"
        )
        - _risk_value(analysis_df, "excess_return_with_cost", "annualized_return"),
        "daily_win_rate_with_cost": float((net_return > 0).mean()),
        "daily_excess_win_rate_with_cost": float((excess_net > 0).mean()),
        "avg_turnover": avg_turnover,
        "avg_holding_days_proxy": float(1.0 / avg_turnover) if avg_turnover > 0 else float("nan"),
        "avg_position_count": avg_position_count,
        "mean_current_holding_days": mean_holding_count,
        "final_account": float(report["account"].iloc[-1]),
    }

    yearly = pd.DataFrame(
        {
            "year": report.index.year,
            "return_without_cost": report["return"].to_numpy(),
            "return_with_cost": net_return.to_numpy(),
            "benchmark_return": report["bench"].to_numpy(),
            "excess_return_with_cost": excess_net.to_numpy(),
            "cost": report["cost"].to_numpy(),
        },
        index=report.index,
    )
    yearly = yearly.groupby("year", as_index=False).sum(numeric_only=True)
    yearly.insert(0, "cost_scenario", scenario.name)
    yearly.insert(0, "deal_price", deal_price)
    yearly.insert(0, "breakout_window", int(breakout_window))
    yearly.insert(0, "baseline", baseline_id(breakout_window, deal_price))
    return summary, yearly, board_df


def _recorder_path(recorder: object) -> str:
    info = recorder.info
    return f"mlruns/{info['experiment_id']}/{info['id']}"


def run_portfolio_backtest(
    *,
    pred: pd.DataFrame,
    breakout_window: int,
    deal_price: str,
    scenario: CostScenario,
    backtest_start: str,
    backtest_end: str,
    benchmark: str,
    topk: int,
    n_drop: int,
    hold_thresh: int,
    risk_degree: float,
    account: int,
    signal_mode: str,
    active_window: int,
    hold_atr_buffer: float,
    hold_requires_ma: bool,
) -> Tuple[Dict[str, object], pd.DataFrame, pd.DataFrame]:
    experiment_name = f"a_share_breakout_stage6_{int(breakout_window)}d_{deal_price}_{scenario.name}"
    port_config = build_port_analysis_config(
        pred=None,
        deal_price=deal_price,
        scenario=scenario,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        benchmark=benchmark,
        topk=topk,
        n_drop=n_drop,
        hold_thresh=hold_thresh,
        risk_degree=risk_degree,
        account=account,
    )
    params = {
        "breakout_window": int(breakout_window),
        "deal_price": deal_price,
        "cost_scenario": scenario.name,
        "topk": topk,
        "n_drop": n_drop,
        "hold_thresh": hold_thresh,
        "risk_degree": risk_degree,
        "signal_mode": signal_mode,
        "active_window": int(active_window),
        "hold_atr_buffer": float(hold_atr_buffer),
        "hold_requires_ma": bool(hold_requires_ma),
        "backtest_start": backtest_start,
        "backtest_end": backtest_end,
        "open_cost": scenario.open_cost,
        "close_cost": scenario.close_cost,
        "impact_cost": scenario.impact_cost,
        "min_cost": scenario.min_cost,
    }
    with R.start(experiment_name=experiment_name):
        recorder = R.get_recorder()
        R.log_params(**flatten_dict(params))
        R.save_objects(**{"pred.pkl": pred, "label.pkl": None, "stage6_port_config.pkl": port_config})
        par = PortAnaRecord(recorder, port_config, risk_analysis_freq="day", indicator_analysis_freq="day")
        artifacts = par.generate()
        if not artifacts:
            raise RuntimeError(f"PortAnaRecord did not generate artifacts for {experiment_name}")

    summary, yearly, board = extract_portfolio_summary(
        report=artifacts["report_normal_1day.pkl"],
        analysis_df=artifacts["port_analysis_1day.pkl"],
        positions=artifacts["positions_normal_1day.pkl"],
        recorder_path=_recorder_path(recorder),
        pred=pred,
        breakout_window=breakout_window,
        deal_price=deal_price,
        scenario=scenario,
        backtest_start=backtest_start,
        backtest_end=backtest_end,
        signal_mode=signal_mode,
        active_window=active_window,
        hold_atr_buffer=hold_atr_buffer,
        hold_requires_ma=hold_requires_ma,
    )
    summary.update({"topk": int(topk), "n_drop": int(n_drop), "hold_thresh": int(hold_thresh)})
    return summary, yearly, board


def _normalize_quote_index(quote: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(quote.index, pd.MultiIndex):
        raise ValueError("Qlib quote data must use a MultiIndex")
    names = list(quote.index.names)
    if "datetime" in names and "instrument" in names:
        return quote.reorder_levels(["datetime", "instrument"]).sort_index()
    if len(names) == 2:
        return quote.swaplevel().sort_index()
    raise ValueError(f"Unsupported quote index names: {names}")


def audit_deal_price_availability(
    pred: pd.DataFrame,
    *,
    deal_prices: Sequence[str],
    backtest_end: str,
) -> pd.DataFrame:
    from qlib.data import D

    pred_dates = pd.DatetimeIndex(pred.index.get_level_values("datetime").unique()).sort_values()
    if pred_dates.empty:
        return pd.DataFrame()

    calendar = pd.DatetimeIndex(D.calendar(start_time=pred_dates.min(), end_time=backtest_end))
    next_date = {calendar[i]: calendar[i + 1] for i in range(len(calendar) - 1)}
    pairs = pred.reset_index()[["datetime", "instrument"]].copy()
    pairs["execution_date"] = pairs["datetime"].map(next_date)
    missing_execution_date = int(pairs["execution_date"].isna().sum())
    pairs = pairs.dropna(subset=["execution_date"]).copy()
    if pairs.empty:
        return pd.DataFrame(
            [
                {
                    "deal_price": price,
                    "board": "ALL",
                    "signal_rows": int(len(pred)),
                    "execution_rows": 0,
                    "missing_execution_date": missing_execution_date,
                    "missing_deal_price": 0,
                    "missing_deal_price_rate": float("nan"),
                    "missing_close": 0,
                    "zero_or_missing_volume": 0,
                    "tradable_proxy_rows": 0,
                    "tradable_proxy_rate": float("nan"),
                }
                for price in deal_prices
            ]
        )

    fields = sorted({f"${price}" for price in deal_prices} | {"$close", "$volume"})
    quote = D.features(
        sorted(pairs["instrument"].unique()),
        fields,
        start_time=pairs["execution_date"].min(),
        end_time=pairs["execution_date"].max(),
    )
    quote = _normalize_quote_index(quote)
    needed_index = pd.MultiIndex.from_arrays(
        [pairs["execution_date"].to_numpy(), pairs["instrument"].to_numpy()],
        names=["datetime", "instrument"],
    )
    aligned = quote.reindex(needed_index).copy()
    aligned = aligned.drop(columns=[col for col in ("datetime", "instrument") if col in aligned.columns])
    aligned = aligned.reset_index()
    aligned["board"] = aligned["instrument"].map(infer_board)

    rows: List[Dict[str, object]] = []
    groups = [("ALL", aligned)]
    groups.extend((board, group) for board, group in aligned.groupby("board"))
    for price in deal_prices:
        price_col = f"${price}"
        for board, group in groups:
            total = int(len(group))
            missing_price = int(group[price_col].isna().sum())
            missing_close = int(group["$close"].isna().sum())
            zero_or_missing_volume = int((group["$volume"].fillna(0) <= 0).sum())
            tradable = group[price_col].notna() & group["$close"].notna() & (group["$volume"].fillna(0) > 0)
            signal_rows = int(len(pred)) if board == "ALL" else int((pairs["instrument"].map(infer_board) == board).sum())
            rows.append(
                {
                    "deal_price": price,
                    "board": board,
                    "signal_rows": signal_rows,
                    "execution_rows": total,
                    "missing_execution_date": missing_execution_date if board == "ALL" else 0,
                    "missing_deal_price": missing_price,
                    "missing_deal_price_rate": missing_price / total if total else float("nan"),
                    "missing_close": missing_close,
                    "zero_or_missing_volume": zero_or_missing_volume,
                    "tradable_proxy_rows": int(tradable.sum()),
                    "tradable_proxy_rate": float(tradable.mean()) if total else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def build_cost_sensitivity(summary: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for (window, deal_price), group in summary.groupby(["breakout_window", "deal_price"]):
        low = group[group["cost_scenario"] == "low"]
        low_excess = float(low["excess_ann_return_with_cost"].iloc[0]) if not low.empty else float("nan")
        for _, row in group.iterrows():
            rows.append(
                {
                    "baseline": row["baseline"],
                    "breakout_window": int(window),
                    "deal_price": deal_price,
                    "cost_scenario": row["cost_scenario"],
                    "annualized_cost": row["annualized_cost"],
                    "excess_ann_return_with_cost": row["excess_ann_return_with_cost"],
                    "delta_vs_low_cost_excess_ann_return": row["excess_ann_return_with_cost"] - low_excess,
                    "avg_turnover": row["avg_turnover"],
                    "avg_holding_days_proxy": row["avg_holding_days_proxy"],
                }
            )
    return pd.DataFrame(rows)
