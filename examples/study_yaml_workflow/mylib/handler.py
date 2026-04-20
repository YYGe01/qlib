# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""
自定义数据处理器（标准做法：继承 Alpha158 / DataHandlerLP）。

说明：
- Alpha158 的因子来自 ``get_feature_config()`` → ``Alpha158DL.get_feature_config(conf)`` 返回 (表达式列表, 列名列表)。
- 新增因子时，在子类中 ``append`` 自定义表达式与列名即可，无需复制整套 Alpha158 源码。
- 若完全自定义因子集，可继承 ``DataHandlerLP`` 并自行配置 ``QlibDataLoader``（参考 ``qlib.contrib.data.handler.Alpha158``）。
"""

from qlib.contrib.data.handler import Alpha158
from qlib.contrib.data.loader import Alpha158DL


class StudyAlpha158(Alpha158):
    """
    在官方 Alpha158 特征集基础上，追加一条「双均线差」趋势类因子。

    列名 MA_TREND_5_20 需在 workflow 中与 FactorColumnModel 的 feature_col 一致。
    """

    def get_feature_config(self):
        conf = {
            "kbar": {},
            "price": {
                "windows": [0],
                "feature": ["OPEN", "HIGH", "LOW", "VWAP"],
            },
            "rolling": {},
        }
        fields, names = Alpha158DL.get_feature_config(conf)
        fields.append("Mean($close, 5) - Mean($close, 20)")
        names.append("MA_TREND_5_20")
        return fields, names
