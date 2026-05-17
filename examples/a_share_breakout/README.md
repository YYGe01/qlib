# A 股日线突破研究

本目录承接 `a股日线趋势交易多阶段实施计划.md` 的日线规则研究，目前已完成阶段 1 数据盘点与阶段 2 突破事件标注脚本。

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
它们是后续事件生成和 qrun 接入的参数清单，目前还不是 qrun workflow 文件。
