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


class RuleSignalModel(Model):
    """Compute ``trend_score`` from rule features without parameter training.

    ``fit`` performs only a schema check.  ``predict`` returns a sparse Series:
    rows that are not current breakout candidates are dropped so TopK selection
    cannot buy non-breakout names merely to fill the portfolio.
    """

    def __init__(
        self,
        breakout_window: int = 60,
        score_weights: Optional[Dict[str, float]] = None,
        require_candidate: bool = True,
        score_name: str = "trend_score",
    ):
        self.breakout_window = int(breakout_window)
        self.score_weights = dict(DEFAULT_SCORE_WEIGHTS)
        if score_weights:
            self.score_weights.update(score_weights)
        self.require_candidate = require_candidate
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
            score = score.where(candidate)

        score = score.replace([np.inf, -np.inf], np.nan).dropna()
        score.name = self.score_name
        return score
