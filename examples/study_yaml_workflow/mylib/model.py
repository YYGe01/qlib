# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""
与「训练模型」接口兼容的占位模型：把数据集中某一列特征直接当作预测分数。

用途：
- 与 ``qrun`` + ``task_train`` + ``SignalRecord`` 完全同一套流水线；
- ``fit`` 不做拟合（或仅校验数据），``predict`` 输出指定特征列，供 TopK 回测与 IC 分析。

进阶时可将此类替换为 LGBModel / LinearModel，YAML 中仅改 ``task.model`` 段即可。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from qlib.data.dataset import DatasetH
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.weight import Reweighter
from qlib.model.base import Model


class FactorColumnModel(Model):
    """
    将 ``dataset.prepare(..., col_set='feature')`` 中的单列作为 pred。

    参数
    ----
    feature_col : str
        特征列名，须与 Handler 产出的列一致（如 StudyAlpha158 中的 MA_TREND_5_20）。
    """

    def __init__(self, feature_col: str = "MA_TREND_5_20"):
        self.feature_col = feature_col

    def fit(self, dataset: DatasetH, reweighter: Optional[Reweighter] = None):
        """不进行参数学习；与树模型共用同一 fit 调用约定。"""
        return self

    def predict(self, dataset: DatasetH, segment: str = "test") -> pd.Series:
        """推理阶段使用 DK_I（与 LinearModel 等一致）。"""
        x_test = dataset.prepare(segment, col_set="feature", data_key=DataHandlerLP.DK_I)
        if self.feature_col not in x_test.columns:
            cols = list(x_test.columns)
            preview = cols[:30]
            raise ValueError(
                f"特征列 {self.feature_col!r} 不存在。当前列数={len(cols)}，示例: {preview} ..."
            )
        return pd.Series(x_test[self.feature_col].values, index=x_test.index)
