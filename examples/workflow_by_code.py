#  Copyright (c) Microsoft Corporation.
#  Licensed under the MIT License.
"""
Qlib provides two kinds of interfaces.
(1) Users could define the Quant research workflow by a simple configuration.
(2) Qlib is designed in a modularized way and supports creating research workflow by code just like building blocks.

The interface of (1) is `qrun XXX.yaml`.  The interface of (2) is script like this, which nearly does the same thing as `qrun XXX.yaml`
"""

import qlib
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord
from qlib.tests.data import GetData
from qlib.tests.config import CSI300_BENCH, CSI300_GBDT_TASK

if __name__ == "__main__":
    # 这是“代码方式跑完整研究流程”的最小闭环示例：
    # 1. 准备并初始化底层行情/特征数据
    # 2. 按任务配置实例化 model 和 dataset
    # 3. 训练模型并把产物记到 Recorder
    # 4. 生成预测信号
    # 5. 基于预测做信号分析和组合回测
    # use default data
    provider_uri = "~/.qlib/qlib_data/cn_data"  # target_dir
    GetData().qlib_data(target_dir=provider_uri, region=REG_CN, exists_skip=True)
    qlib.init(provider_uri=provider_uri, region=REG_CN)

    # task 里的 model/dataset 都是配置驱动实例化，调试时可以顺着配置继续定位到具体类。
    model = init_instance_by_config(CSI300_GBDT_TASK["model"])
    dataset = init_instance_by_config(CSI300_GBDT_TASK["dataset"])

    port_analysis_config = {
        "executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        },
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {
                "signal": (model, dataset),
                "topk": 50,
                "n_drop": 5,
            },
        },
        "backtest": {
            "start_time": "2017-01-01",
            "end_time": "2020-08-01",
            "account": 100000000,
            "benchmark": CSI300_BENCH,
            "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        },
    }

    # dataset.prepare("train") 是理解数据流最直接的入口：
    # 它会触发 handler.fetch，把原始数据按 train/valid/test 分段后返回给模型可消费的表结构。
    example_df = dataset.prepare("train")
    print(example_df.head())

    # Recorder 是训练/预测/分析这条链的挂载点；后续 SignalRecord / PortAnaRecord 都往这里写结果。
    with R.start(experiment_name="workflow"):
        R.log_params(**flatten_dict(CSI300_GBDT_TASK))
        model.fit(dataset)
        R.save_objects(**{"params.pkl": model})

        # SignalRecord 负责把模型预测落盘成 pred.pkl，并尽量把 label 也一并保存，供后续分析/回测复用。
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()

        # SigAnaRecord 读取 pred.pkl / label.pkl，计算 IC / Rank IC 等信号质量指标。
        sar = SigAnaRecord(recorder)
        sar.generate()

        # PortAnaRecord 会把 pred.pkl 注入策略配置，然后进入回测引擎，最终产出收益、持仓和风险分析结果。
        par = PortAnaRecord(recorder, port_analysis_config, "day")
        par.generate()
