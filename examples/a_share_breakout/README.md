# A 股日线突破研究

本目录承接 `a股日线趋势交易多阶段实施计划.md` 的日线规则研究，目前已完成阶段 1 数据盘点、阶段 2 突破事件标注、阶段 3 日线规则特征、阶段 4 无训练 qrun 接入和阶段 5 事件研究报告。

## 阶段 1：数据盘点与样本过滤

在仓库根目录执行：

```bash
python examples/a_share_breakout/data_inventory.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --start-time 2021-01-01
```

命令会在 `examples/a_share_breakout/outputs/` 下输出三份审计表：

| 输出文件 | 用途 |
|---|---|
| `data_inventory.csv` | 本地交易日历范围、活跃股票池、核心字段覆盖和缺失/代理字段。 |
| `sample_filter_summary.csv` | 各条剔除规则的样本数，包括板块剔除、可交易性、新股、复牌首日和一字板代理过滤。 |
| `universe_by_board.csv` | 基于代码前缀的板块分布、可交易行数和日期范围。 |

生成的 CSV 不进入 git。它们是与当前本地数据包绑定的研究产物。

最近一次本地运行：

| 项目 | 值 |
|---|---|
| 命令 | `python examples/a_share_breakout/data_inventory.py --provider-uri ~/.qlib/qlib_data/cn_data --start-time 2021-01-01` |
| 运行日期 | 2026-05-17 |
| 统计窗口 | 2021-01-04 至 2026-04-17 |
| 活跃标的 | 5952 |
| A 股股票类标的 | 5946 |
| 阶段 1 过滤后标的-日期行数 | 5997259 |

验证记录：

| 命令 | 结果 |
|---|---|
| `python -m py_compile examples/a_share_breakout/data_inventory.py` | 通过 |
| `pytest -q tests/test_a_share_breakout_data_inventory.py` | 通过：2 个测试 |
| `python examples/a_share_breakout/data_inventory.py --provider-uri ~/.qlib/qlib_data/cn_data --start-time 2021-01-01` | 通过，并生成三份阶段 1 CSV |

## 当前代理口径与缺口

阶段 1/2 脚本会显式记录无法严格实现的过滤项，而不是把代理口径伪装成完整实现：

| 项目 | 阶段 1 处理方式 |
|---|---|
| 板块 | 用代码前缀推断：`SH60*`、`SZ00*`、`SZ30*`、`SH68*`、`BJ*`。 |
| 上市日期 | 用本地首个有效 OHLCV 观测日代理。 |
| 上市前 5 个交易日 | 用首个有效 OHLCV 观测日后的交易年龄代理。 |
| 上市不足 250 个交易日 | 用同一交易年龄计数代理。 |
| 停牌日 | 用 close/volume 缺失或 `volume <= 0` 代理。 |
| 复牌首日 | 用前一交易日不可交易、当日可交易代理。 |
| 一字涨停日 | 用 OHLC 近似相等加板块涨幅阈值代理。 |
| ST/*ST/退市整理 | 未实现，需要历史证券状态或名称数据。 |
| 高低涨跌停价 | 本地日线包没有对应字段。 |
| 除权除息异常 | 尚未严格识别；阶段 1 只盘点 factor 可用性。 |
| 尾盘集合竞价、30 分钟 VWAP、盘口、撤单、资金流 | 未实现，需要分钟、Level-2 或外部供应商字段。 |

## 阶段 2：突破事件识别与标注

在仓库根目录执行：

```bash
python examples/a_share_breakout/breakout_events.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --start-time 2021-01-01
```

命令会默认生成 60 日和 120 日两组突破事件：

| 输出文件 | 用途 |
|---|---|
| `breakout_events_60d.csv` / `breakout_events_60d.parquet` | 60 日突破候选中未来 20 日完整、可标注的事件表。 |
| `breakout_events_120d.csv` / `breakout_events_120d.parquet` | 120 日突破候选中未来 20 日完整、可标注的事件表。 |
| `breakout_event_summary.csv` | 候选数、未来窗口不足剔除数、标签分布和板块-标签分布。 |
| `breakout_events_60d_manual_check_ohlcv.csv` | 随机 20 个 60 日事件的 `T-5` 至 `T+20` OHLCV 核对样本。 |
| `breakout_events_120d_manual_check_ohlcv.csv` | 随机 20 个 120 日事件的 `T-5` 至 `T+20` OHLCV 核对样本。 |

最近一次本地运行：

| 项目 | 60 日突破 | 120 日突破 |
|---|---:|---:|
| 候选事件 | 144033 | 89571 |
| 未来 20 日不足剔除 | 3512 | 2542 |
| 输出可标注事件 | 140521 | 87029 |
| 真突破 | 35491 | 21557 |
| 假突破 | 92889 | 59730 |
| 不确定 | 12141 | 5742 |

阶段 2 事件识别只使用 T 日及以前字段：过去窗口高点、ATR、量比和成交额历史分位。未来 5/20 日窗口只用于研究标签，且未来 20 日价格不完整的候选不会进入事件标签统计。

阶段 2 验证记录：

| 命令 | 结果 |
|---|---|
| `python -m py_compile examples/a_share_breakout/data_inventory.py examples/a_share_breakout/breakout_events.py` | 通过 |
| `pytest -q tests/test_a_share_breakout_breakout_events.py tests/test_a_share_breakout_data_inventory.py` | 通过：6 个测试 |
| `python examples/a_share_breakout/breakout_events.py --provider-uri ~/.qlib/qlib_data/cn_data --start-time 2021-01-01` | 通过，并生成阶段 2 事件表 |
| CSV/Parquet 行数一致性与抽样核对范围审计 | 通过：60/120 日事件表行数一致，抽样事件均覆盖 `T-5` 至 `T+20` |

## 阶段 3：规则指标库与日线失真评分

在仓库根目录执行：

```bash
python examples/a_share_breakout/daily_features.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --start-time 2021-01-01
```

命令会生成全市场日线面板特征。`feature_matrix_daily.csv` 体积较大，默认只写 CSV；如确实需要 Parquet，可追加 `--write-parquet`。

| 输出文件 | 用途 |
|---|---|
| `feature_matrix_daily.csv` | 阶段 1 过滤后的每日股票规则指标矩阵，包含 60/120 日突破强度、均线结构、相对强弱、量能持续性、波动分位、涨停依赖和日线失真评分。 |
| `feature_dictionary_daily.csv` | 每个已实现、代理实现、研究专用和未实现指标的定义、可见时间、是否可用于交易信号和缺失数据原因。 |
| `feature_matrix_summary.csv` | 特征矩阵行数、股票数、日期范围、板块分布、候选突破数量和字段非空覆盖。 |

最近一次本地运行：

| 项目 | 值 |
|---|---|
| 命令 | `python examples/a_share_breakout/daily_features.py --provider-uri ~/.qlib/qlib_data/cn_data --start-time 2021-01-01` |
| 运行日期 | 2026-05-17 |
| 统计窗口 | 2021-01-04 至 2026-04-17 |
| 输出行数 | 5997259 |
| 输出标的 | 5553 |
| 基准指数 | `SH000300` |
| 60 日候选突破 | 144033 |
| 120 日候选突破 | 89571 |

阶段 3 的 `fake_prob_daily_t_*` 只使用 T 日收盘前可见的日线代理指标，可用于后续交易信号；`fake_prob_daily_research_*` 和 `next_open_*_research` 使用 T+1 开盘，只能用于事后归因和事件研究。

阶段 3 验证记录：

| 命令 | 结果 |
|---|---|
| `python -m py_compile examples/a_share_breakout/daily_features.py` | 通过 |
| `pytest -q tests/test_a_share_breakout_daily_features.py` | 通过：3 个测试 |
| `python examples/a_share_breakout/daily_features.py --provider-uri ~/.qlib/qlib_data/cn_data --start-time 2021-01-01` | 通过，并生成阶段 3 特征矩阵、特征字典和摘要 |
| `feature_matrix_summary.csv` 候选数审计 | 通过：60/120 日候选数与阶段 2 `breakout_event_summary.csv` 一致 |

## 阶段 0 脚手架

`configs/baseline_60d.yaml` 和 `configs/baseline_120d.yaml` 固定第一版 60 日/120 日突破参数。
它们是阶段 1-3 脚本使用的参数清单；阶段 4 qrun 使用 `workflow_rule_breakout.yaml`。

## 阶段 4：无训练规则信号与 qrun 流水线

在仓库根目录执行：

```bash
python -m qlib.cli.run examples/a_share_breakout/workflow_rule_breakout.yaml
```

阶段 4 新增文件：

| 文件 | 用途 |
|---|---|
| `workflow_rule_breakout.yaml` | 60 日突破规则信号的 qrun workflow，包含 `SignalRecord`、`SigAnaRecord` 和 `PortAnaRecord`。 |
| `mylib/handler.py` | `AShareBreakoutRuleHandler`，用 Qlib 表达式生成 T 日可见的规则特征。 |
| `mylib/model.py` | `RuleSignalModel`，`fit` 只校验列，`predict` 计算 `trend_score`，不训练模型。 |

最近一次本地运行：

| 项目 | 值 |
|---|---|
| 命令 | `python -m qlib.cli.run examples/a_share_breakout/workflow_rule_breakout.yaml` |
| 运行日期 | 2026-05-17 |
| qrun recorder | `mlruns/476777289722113917/80ae45a5cf0b400f8e05bdfccd337e7b` |
| 预测窗口 | 2025-01-02 至 2026-04-17 |
| `pred.pkl` 行数 | 50228 |
| `pred.pkl` 覆盖标的 | 5632 |
| 记录产物 | `pred.pkl`、`label.pkl`、`sig_analysis/*.pkl`、`portfolio_analysis/*.pkl` |

阶段 4 workflow 不使用 `RobustZScoreNorm`、`Fillna` 或 label processor。原因是 `RuleSignalModel` 内部会处理 NaN/inf，且不训练参数；对全市场日线面板额外复制处理会显著增加内存占用。

阶段 4 验证记录：

| 命令 | 结果 |
|---|---|
| `python -m py_compile examples/a_share_breakout/mylib/handler.py examples/a_share_breakout/mylib/model.py` | 通过 |
| `pytest -q tests/test_a_share_breakout_rule_workflow.py` | 通过：4 个测试 |
| Qlib 小样本表达式取数 | 通过：`SH600000` 可生成突破位、ATR、突破强度和候选标记 |
| `python -m qlib.cli.run examples/a_share_breakout/workflow_rule_breakout.yaml` | 通过：`SignalRecord`、`SigAnaRecord`、`PortAnaRecord` 均保存产物；运行中出现 `$open` 含 NaN 的数据质量警告 |

## 阶段 5：事件研究统计与可视化报告

在仓库根目录执行：

```bash
python examples/a_share_breakout/event_study.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --output-dir examples/a_share_breakout/outputs \
  --breakout-windows 60 120
```

阶段 5 读取阶段 2 事件表、阶段 3 特征矩阵和本地 Qlib close/benchmark 数据，生成事件研究报告和图表。阶段 3 的 `feature_matrix_daily.csv` 较大，脚本会按 chunk 读取事件日需要的列。

| 输出文件 | 用途 |
|---|---|
| `event_study_report.md` | 阶段 5 Markdown 报告，汇总标签分布、特征诊断、分层稳定性、20 日收益 HAC 统计和图表索引。 |
| `event_label_summary.csv` | 60/120 日突破的真突破、假突破、不确定标签数量和占比。 |
| `event_feature_diagnostics.csv` | 真/假突破单变量差异、KS 检验、Benjamini-Hochberg FDR q 值和单变量 AUC。 |
| `event_segment_summary.csv` | 板块、年份、指数 MA60、市场成交额、流动性、波动、布林带宽和失真概率分层。 |
| `event_forward_return_curve.csv` | 事件后 0-20 个交易日按标签聚合的平均累计收益曲线数据。 |
| `event_forward_return_hac.csv` | 20 日收益按事件日期聚合后的 Newey-West HAC 标准误、t 值和样本数。 |
| `figures/*.png` | 事件后收益曲线、趋势强度 × 失真概率热力图、失真概率分组真突破率图。 |

最近一次本地运行：

| 项目 | 值 |
|---|---|
| 命令 | `python examples/a_share_breakout/event_study.py --provider-uri ~/.qlib/qlib_data/cn_data --output-dir examples/a_share_breakout/outputs --breakout-windows 60 120` |
| 运行日期 | 2026-05-17 |
| 事件窗口 | 2021-01-04 至 2026-03-19 |
| 事件数 | 227550 |
| 图表数 | 6 |
| 报告 | `examples/a_share_breakout/outputs/event_study_report.md` |

阶段 5 验证记录：

| 命令 | 结果 |
|---|---|
| `python -m py_compile examples/a_share_breakout/event_study.py` | 通过 |
| `pytest -q tests/test_a_share_breakout_event_study.py` | 通过：4 个测试 |
| `python examples/a_share_breakout/event_study.py --provider-uri ~/.qlib/qlib_data/cn_data --output-dir examples/a_share_breakout/outputs --breakout-windows 60 120` | 通过，并生成阶段 5 报告、统计表和 6 张图 |

## 阶段 6：组合回测 MVP 与成本敏感性

阶段 6 使用阶段 4 的无训练 `RuleSignalModel`，不重新定义打分逻辑。脚本会对每个突破窗口只生成一次 `pred.pkl`，再复用同一份预测跑 `open/vwap × 低/中/高成本` 回测矩阵。

在仓库根目录执行：

```bash
python examples/a_share_breakout/backtest_rule_breakout.py \
  --provider-uri ~/.qlib/qlib_data/cn_data \
  --output-dir examples/a_share_breakout/outputs \
  --breakout-window 60 120 \
  --deal-price open vwap \
  --cost-scenario low neutral high
```

阶段 6 新增文件：

| 文件 | 用途 |
|---|---|
| `backtest_rule_breakout.py` | 阶段 6 CLI 入口，批量生成规则预测、运行组合回测、输出摘要和报告。 |
| `mylib/stage6_config.py` | 成本场景、数据集、模型和 `PortAnaRecord` 配置构建。 |
| `mylib/stage6_metrics.py` | 组合指标提取、open/vwap 可成交性审计、成本敏感性和 Markdown 报告。 |
| `configs/cost_scenarios.yaml` | 低/中/高成本场景，包含 `open_cost`、`close_cost`、`impact_cost` 和 `min_cost`。 |
| `configs/workflow_baseline_*` | 四组中性成本 qrun baseline：60/120 日 × open/vwap。 |

阶段 6 输出文件仍在 `outputs/` 下，不进入 git：

| 输出文件 | 用途 |
|---|---|
| `baseline_backtest_summary.csv` | 12 组组合回测摘要，含 recorder、年化收益、最大回撤、IR、换手和成本。 |
| `cost_sensitivity.csv` | 低/中/高成本敏感性长表。 |
| `baseline_yearly_returns.csv` | 分年度收益、基准、超额和成本。 |
| `baseline_board_exposure.csv` | 持仓板块暴露；当前不是收益贡献归因。 |
| `deal_price_availability_audit.csv` | open/vwap 执行价缺失率和可交易代理率审计。 |
| `baseline_backtest_report.md` | 阶段 6 Markdown 报告。 |

最近一次本地运行：

| baseline | 中性成本 recorder | 成本后超额年化 | 最大回撤 | 日均换手 | 持有天数代理 |
|---|---|---:|---:|---:|---:|
| `baseline_60d_open` | `mlruns/867736467774860149/c6dfa9026f1f45f793127b817645be8f` | -178.57% | -214.46% | 38.61% | 2.59 |
| `baseline_60d_vwap` | `mlruns/228360756557040550/586fb7ca6a0e41c598f52abf080b1c99` | -161.85% | -193.78% | 42.30% | 2.36 |
| `baseline_120d_open` | `mlruns/195305598796427711/ecc1dfa0cf9a4075bdac50376128273c` | -211.21% | -257.23% | 48.07% | 2.08 |
| `baseline_120d_vwap` | `mlruns/291751630157164956/e0d04f06258149db9ab13cdeaa0b8ac1` | -181.02% | -219.69% | 52.52% | 1.90 |

成本敏感性结论：低成本场景下四组 baseline 成本后超额年化仍全部为负；中性成本和高成本进一步恶化。按实施计划，当前不应直接进入阶段 7 自定义事件策略，应先回到事件研究、候选过滤和 TopK 换手问题修正规则。

open/vwap 可成交性审计：

| window | deal_price | execution rows | 缺成交价率 | 可交易代理率 |
|---:|---|---:|---:|---:|
| 60 | open | 50072 | 0.27% | 99.73% |
| 60 | vwap | 50072 | 0.88% | 99.12% |
| 120 | open | 36330 | 0.32% | 99.68% |
| 120 | vwap | 36330 | 0.99% | 99.01% |

阶段 6 验证记录：

| 命令 | 结果 |
|---|---|
| `python -m py_compile examples/a_share_breakout/backtest_rule_breakout.py examples/a_share_breakout/mylib/stage6_config.py examples/a_share_breakout/mylib/stage6_metrics.py` | 通过 |
| `pytest -q tests/test_a_share_breakout_stage6_backtest.py` | 通过：4 个测试 |
| `python examples/a_share_breakout/backtest_rule_breakout.py --provider-uri ~/.qlib/qlib_data/cn_data --output-dir examples/a_share_breakout/outputs --breakout-window 60 120 --deal-price open vwap --cost-scenario low neutral high` | 通过，并生成 12 组回测、成本敏感性、年度收益、板块暴露和 open/vwap 审计 |
