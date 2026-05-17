# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Qlib handler for daily A-share breakout rule features.

The handler intentionally keeps the feature set small.  It exposes only
T-close-visible fields needed by :class:`mylib.model.RuleSignalModel`, so the
rule score can be plugged into the standard qrun SignalRecord/PortAnaRecord
workflow without training a predictive model.
"""

from __future__ import annotations

from typing import List, Tuple

from qlib.contrib.data.handler import Alpha158


def _true_range_expr() -> str:
    prev_close = "Ref($close, 1)"
    high_low = "($high-$low)"
    high_prev_close = f"Abs($high-{prev_close})"
    low_prev_close = f"Abs($low-{prev_close})"
    return f"Greater({high_low}, Greater({high_prev_close}, {low_prev_close}))"


def _bounded_0_1(expr: str) -> str:
    return f"Less(Greater({expr}, 0), 1)"


def _sigmoid_raw_expr(
    volume_spike_no_persistence: str,
    limit_dependency_score: str,
    atr_noise_rank: str,
    barely_breakout_score: str,
) -> str:
    return (
        f"0.25*{volume_spike_no_persistence}"
        f" + 0.20*{limit_dependency_score}"
        f" + 0.15*{atr_noise_rank}"
        f" + 0.10*{barely_breakout_score}"
    )


def build_rule_feature_config(
    breakout_window: int = 60,
    benchmark_instrument: str = "SH000300",
    atr_window: int = 14,
    volume_window: int = 20,
    amount_rank_window: int = 252,
    ma_fast_window: int = 20,
    ma_slow_window: int = 60,
    ma_slope_window: int = 20,
    bb_window: int = 20,
    return_window: int = 20,
    breakout_atr_multiple: float = 0.5,
) -> Tuple[List[str], List[str]]:
    """Build qlib expression fields and feature names for one breakout window."""

    breakout_window = int(breakout_window)
    true_range = _true_range_expr()
    atr = f"Mean({true_range}, {int(atr_window)})"
    atr_pct = f"{atr}/($close+1e-12)"
    breakout_level = f"Ref(Max($close, {breakout_window}), 1)"
    breakout_strength = f"($close-{breakout_level})/({atr}+1e-12)"

    ma_fast = f"Mean($close, {int(ma_fast_window)})"
    ma_slow = f"Mean($close, {int(ma_slow_window)})"
    ma_slope = f"({ma_fast}-Ref({ma_fast}, {int(ma_slope_window)}))/(Abs(Ref({ma_fast}, {int(ma_slope_window)}))+1e-12)"

    stock_return = f"$close/(Ref($close, {int(return_window)})+1e-12)-1"
    bench_return = f"ChangeInstrument('{benchmark_instrument}', $close/(Ref($close, {int(return_window)})+1e-12)-1)"
    relative_strength = f"({stock_return})-({bench_return})"

    vol_ratio_20 = f"$volume/(Mean(Ref($volume, 1), {int(volume_window)})+1e-12)"
    vol_ratio_3d = f"Mean($volume, 3)/(Mean(Ref($volume, 3), {int(volume_window)})+1e-12)"
    volume_spike_no_persistence = (
        f"If(Gt({vol_ratio_20}, 1), "
        f"{_bounded_0_1(f'({vol_ratio_20}-{vol_ratio_3d})/({vol_ratio_20}+1e-12)')}, 0)"
    )

    bb_width = f"4*Std($close, {int(bb_window)})/(Mean($close, {int(bb_window)})+1e-12)"
    close_return_1d = "$close/(Ref($close, 1)+1e-12)-1"
    limit_dependency = _bounded_0_1(f"Greater({close_return_1d}, 0)/0.095")
    one_word_limit_like = (
        f"If(And(Lt(Abs($high-$low)/($close+1e-12), 0.001), Gt({close_return_1d}, 0.085)), 1, 0)"
    )
    barely_breakout = f"If(Gt({breakout_strength}, 0), {_bounded_0_1(f'1-({breakout_strength})')}, 0)"
    candidate = (
        f"If(And(Gt($close, {breakout_level}), "
        f"Ge($close, {breakout_level}+{float(breakout_atr_multiple)}*{atr})), 1, 0)"
    )
    fake_prob_raw = _sigmoid_raw_expr(
        volume_spike_no_persistence=volume_spike_no_persistence,
        limit_dependency_score=limit_dependency,
        atr_noise_rank=f"Rank({atr_pct}, {int(amount_rank_window)})",
        barely_breakout_score=barely_breakout,
    )

    suffix = f"{breakout_window}D"
    fields = [
        "$close",
        breakout_level,
        atr,
        atr_pct,
        f"Rank({atr_pct}, {int(amount_rank_window)})",
        breakout_strength,
        candidate,
        f"If(Gt({ma_fast}, {ma_slow}), 1, 0)",
        ma_slope,
        relative_strength,
        vol_ratio_20,
        vol_ratio_3d,
        volume_spike_no_persistence,
        f"Rank($amount, {int(amount_rank_window)})",
        bb_width,
        f"Rank({bb_width}, {int(amount_rank_window)})",
        limit_dependency,
        one_word_limit_like,
        barely_breakout,
        fake_prob_raw,
    ]
    names = [
        "CLOSE",
        f"BREAKOUT_LEVEL_{suffix}",
        "ATR_14",
        "ATR_PCT",
        "ATR_NOISE_RANK_252",
        f"BREAKOUT_STRENGTH_{suffix}",
        f"CANDIDATE_{suffix}",
        "MA20_GT_MA60",
        "MA20_SLOPE_20",
        "REL_STRENGTH_20D",
        "VOL_RATIO_20",
        "VOL_RATIO_3D",
        "VOLUME_SPIKE_NO_PERSISTENCE",
        "AMOUNT_RANK_252",
        "BB_WIDTH_20",
        "BB_WIDTH_RANK_252",
        "LIMIT_DEPENDENCY_SCORE",
        "ONE_WORD_LIMIT_LIKE",
        f"BARELY_BREAKOUT_SCORE_{suffix}",
        f"FAKE_PROB_DAILY_T_RAW_{suffix}",
    ]
    return fields, names


class AShareBreakoutRuleHandler(Alpha158):
    """Generate rule features for A-share daily breakout qrun workflows."""

    def __init__(
        self,
        breakout_window: int = 60,
        benchmark_instrument: str = "SH000300",
        **kwargs,
    ):
        self.breakout_window = int(breakout_window)
        self.benchmark_instrument = benchmark_instrument
        super().__init__(**kwargs)

    def get_feature_config(self):
        return build_rule_feature_config(
            breakout_window=self.breakout_window,
            benchmark_instrument=self.benchmark_instrument,
        )
