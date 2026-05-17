# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""No-training rule model for the A-share breakout workflow."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd

from qlib.data.dataset import DatasetH
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.weight import Reweighter
from qlib.model.base import Model


DEFAULT_SCORE_WEIGHTS: Dict[str, float] = {
    "breakout_strength": 2.0,
    "ma_structure": 1.5,
    "relative_strength": 1.0,
    "volume_persistence": 1.0,
    "volatility_regime": 0.5,
    "fake_prob": -2.0,
    "limit_dependency": -1.0,
}

SIGNAL_MODE_CURRENT = "current"
SIGNAL_MODE_ACTIVE = "active"
VALID_SIGNAL_MODES = {SIGNAL_MODE_CURRENT, SIGNAL_MODE_ACTIVE}


def _sigmoid(values: pd.Series) -> pd.Series:
    return 1.0 / (1.0 + np.exp(-values.clip(lower=-60.0, upper=60.0)))


def _finite_series(values: pd.Series, default: float = 0.0) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric.replace([np.inf, -np.inf], np.nan)
    return numeric.fillna(default)


def _cross_section_rank(values: pd.Series, default: float = 0.5) -> pd.Series:
    clean = _finite_series(values, default=np.nan)
    if isinstance(clean.index, pd.MultiIndex) and "datetime" in clean.index.names:
        ranked = clean.groupby(level="datetime").rank(pct=True)
    else:
        ranked = clean.rank(pct=True)
    return ranked.fillna(default)


def _bars_since_latest_true(values: pd.Series) -> pd.Series:
    """Count bars since the latest true value within each instrument."""

    def _distance(group: pd.Series) -> pd.Series:
        if isinstance(group.index, pd.MultiIndex) and "datetime" in group.index.names:
            group = group.sort_index(level="datetime")
        else:
            group = group.sort_index()
        positions = np.arange(len(group), dtype=float)
        latest = pd.Series(np.where(group.to_numpy(dtype=bool), positions, np.nan), index=group.index).ffill()
        return pd.Series(positions, index=group.index) - latest

    if isinstance(values.index, pd.MultiIndex) and "instrument" in values.index.names:
        distance = values.groupby(level="instrument", group_keys=False).apply(_distance)
    else:
        distance = _distance(values)
    return distance.reindex(values.index)


class RuleSignalModel(Model):
    """Compute ``trend_score`` from rule features without parameter training.

    ``fit`` performs only a schema check.  ``predict`` returns a sparse Series.
    In ``current`` mode only same-day breakout candidates are eligible; in
    ``active`` mode recent breakout candidates keep a score during a bounded
    holding window while the trend structure remains valid.
    """

    def __init__(
        self,
        breakout_window: int = 60,
        score_weights: Optional[Dict[str, float]] = None,
        require_candidate: bool = True,
        signal_mode: str = SIGNAL_MODE_CURRENT,
        active_window: int = 20,
        hold_atr_buffer: float = 1.2,
        hold_requires_ma: bool = True,
        score_name: str = "trend_score",
    ):
        if signal_mode not in VALID_SIGNAL_MODES:
            raise ValueError(f"signal_mode must be one of {sorted(VALID_SIGNAL_MODES)}, got {signal_mode!r}")
        if int(active_window) <= 0:
            raise ValueError("active_window must be positive")
        self.breakout_window = int(breakout_window)
        self.score_weights = dict(DEFAULT_SCORE_WEIGHTS)
        if score_weights:
            self.score_weights.update(score_weights)
        self.require_candidate = require_candidate
        self.signal_mode = signal_mode
        self.active_window = int(active_window)
        self.hold_atr_buffer = float(hold_atr_buffer)
        self.hold_requires_ma = bool(hold_requires_ma)
        self.score_name = score_name
        self.is_fitted = False

    @property
    def suffix(self) -> str:
        return f"{self.breakout_window}D"

    @property
    def required_feature_columns(self) -> Iterable[str]:
        return (
            f"BREAKOUT_STRENGTH_{self.suffix}",
            f"CANDIDATE_{self.suffix}",
            "MA20_GT_MA60",
            "MA20_SLOPE_20",
            "REL_STRENGTH_20D",
            "VOL_RATIO_3D",
            "ATR_NOISE_RANK_252",
            "BB_WIDTH_RANK_252",
            f"FAKE_PROB_DAILY_T_RAW_{self.suffix}",
            "LIMIT_DEPENDENCY_SCORE",
        )

    def _prepare_feature_frame(self, dataset: DatasetH, segment: str) -> pd.DataFrame:
        frame = dataset.prepare(segment, col_set="feature", data_key=DataHandlerLP.DK_I)
        if isinstance(frame.columns, pd.MultiIndex):
            if "feature" in frame.columns.get_level_values(0):
                frame = frame["feature"]
            else:
                frame = frame.copy()
                frame.columns = ["_".join(str(part) for part in col if part != "") for col in frame.columns]
        return frame

    def _validate_columns(self, columns: Iterable[str]) -> None:
        missing = [col for col in self.required_feature_columns if col not in columns]
        if missing:
            preview = list(columns)[:30]
            raise ValueError(f"缺少规则信号特征列: {missing}; 当前列示例: {preview}")

    def fit(self, dataset: DatasetH, reweighter: Optional[Reweighter] = None):
        frame = self._prepare_feature_frame(dataset, "train")
        self._validate_columns(frame.columns)
        self.is_fitted = True
        return self

    def predict(self, dataset: DatasetH, segment: str = "test") -> pd.Series:
        frame = self._prepare_feature_frame(dataset, segment)
        self._validate_columns(frame.columns)

        suffix = self.suffix
        breakout_strength = _finite_series(frame[f"BREAKOUT_STRENGTH_{suffix}"])
        ma_structure = _finite_series(frame["MA20_GT_MA60"]) + np.tanh(_finite_series(frame["MA20_SLOPE_20"]) / 0.03)
        relative_strength = _cross_section_rank(frame["REL_STRENGTH_20D"])
        volume_persistence = _cross_section_rank(frame["VOL_RATIO_3D"])
        atr_noise_rank = _finite_series(frame["ATR_NOISE_RANK_252"], default=0.5).clip(0.0, 1.0)
        bb_width_rank = _finite_series(frame["BB_WIDTH_RANK_252"], default=0.5).clip(0.0, 1.0)
        volatility_regime = 0.5 * (1.0 - atr_noise_rank) + 0.5 * (1.0 - bb_width_rank)
        fake_prob = _sigmoid(_finite_series(frame[f"FAKE_PROB_DAILY_T_RAW_{suffix}"]))
        limit_dependency = _finite_series(frame["LIMIT_DEPENDENCY_SCORE"]).clip(0.0, 1.0)

        score = (
            self.score_weights["breakout_strength"] * breakout_strength
            + self.score_weights["ma_structure"] * ma_structure
            + self.score_weights["relative_strength"] * relative_strength
            + self.score_weights["volume_persistence"] * volume_persistence
            + self.score_weights["volatility_regime"] * volatility_regime
            + self.score_weights["fake_prob"] * fake_prob
            + self.score_weights["limit_dependency"] * limit_dependency
        )
        if self.require_candidate:
            candidate = _finite_series(frame[f"CANDIDATE_{suffix}"]) > 0.5
            if self.signal_mode == SIGNAL_MODE_CURRENT:
                eligible = candidate
            else:
                bars_since_candidate = _bars_since_latest_true(candidate)
                active_after_breakout = bars_since_candidate.ge(0) & bars_since_candidate.lt(self.active_window)
                hold_ok = breakout_strength.ge(-self.hold_atr_buffer)
                if self.hold_requires_ma:
                    hold_ok &= _finite_series(frame["MA20_GT_MA60"]) > 0.5
                eligible = active_after_breakout & (candidate | hold_ok)
            score = score.where(eligible)

        score = score.replace([np.inf, -np.inf], np.nan).dropna()
        score.name = self.score_name
        return score
