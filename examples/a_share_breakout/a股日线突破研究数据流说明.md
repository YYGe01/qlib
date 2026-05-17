# A 股日线突破研究数据流说明

本文解释 `examples/a_share_breakout/` 与 Qlib 本身的关系，并按阶段列出输入、处理逻辑、输出格式、样例数据和阶段目的。

## 1. 先区分两件事

### 1.1 Qlib 是什么

Qlib 是通用量化研究和回测基础设施。它提供：

| Qlib 能力 | 在本研究中的用途 |
|---|---|
| 本地数据格式 | 读取 `~/.qlib/qlib_data/cn_data` 下的日线交易日历、股票池和 OHLCV 二进制字段。 |
| 公式/特征能力 | 后续可用 `DataHandlerLP`、表达式算子或自定义 handler 生成规则特征。 |
| 模型接口 | 后续实现“不训练模型”的 `RuleSignalModel`，只把规则分数输出为 prediction。 |
| 实验记录 | 后续用 `SignalRecord`、`SigAnaRecord`、`PortAnaRecord` 记录信号和组合表现。 |
| 组合回测 | 后续用 `TopkDropoutStrategy`、`Exchange`、交易成本和成交价配置跑回测。 |
| 自定义策略接口 | 后续可实现事件生命周期策略，如固定持有期、ATR 止损、趋势退出。 |

### 1.2 本目录是什么

`examples/a_share_breakout/` 不是 Qlib 核心库的新功能，而是一个基于 Qlib 数据和后续回测能力的研究案例。

它补充的是 Qlib 默认不会替你定义的领域逻辑：

| 本目录负责 | Qlib 默认不负责 |
|---|---|
| A 股板块分层，如主板、创业板、科创板、北交所。 | 不会自动知道本研究要按这些板块分层统计。 |
| 停牌、新股、一字板、复牌首日等样本过滤口径。 | Qlib 提供数据和交易限制能力，但研究前的样本审计要自己定义。 |
| “60/120 日突破”事件定义。 | Qlib 不知道什么叫本研究里的突破。 |
| “真突破/假突破/不确定”标签定义。 | Qlib 不会自动用未来 20 日走势给事件贴研究标签。 |
| 日线版失真评分。 | Qlib 没有内置本报告里的假突破概率模型。 |
| 将规则打成 `trend_score`。 | Qlib 可以承接预测分数，但分数本身由本研究定义。 |

所以当前逻辑可以理解为：

```text
Qlib = 数据、实验记录、回测和策略执行基础设施
a_share_breakout = 针对 A 股日线突破问题写的一套研究数据流和规则逻辑
```

## 2. 当前到底是在验证什么

当前已落地的是阶段 0 到阶段 6：

| 阶段 | 当前状态 | 性质 |
|---|---|---|
| 阶段 0 | 已有 `configs/baseline_60d.yaml`、`baseline_120d.yaml` | 冻结参数口径。 |
| 阶段 1 | 已有 `data_inventory.py` 和三份审计输出 | 验证本地 Qlib 数据是否够用，哪些字段缺失。 |
| 阶段 2 | 已有 `breakout_events.py` 和事件表 | 验证突破事件定义，给事件贴真/假突破研究标签。 |
| 阶段 3 | 已有 `daily_features.py` 和特征矩阵输出 | 验证规则特征和日线失真评分能否生成。 |
| 阶段 4 | 已接入 qrun | `RuleSignalModel` 不训练参数，把 T 日可见规则特征转成 Qlib prediction。 |
| 阶段 5 | 已生成正式事件研究报告 | 用事件统计、分层诊断和 HAC 收益统计判断阶段 6 回测重点。 |
| 阶段 6 | 已生成完整组合回测矩阵 | 已完成 60/120 日、open/vwap 和低/中/高成本情景敏感性；结果不支持直接进入复杂策略。 |

因此，目前确实主要是在做研究验证：

1. 本地 Qlib 日线数据能不能支撑这个研究。
2. 60/120 日突破事件能不能被可复现地识别。
3. 真突破/假突破标签能不能独立落盘，且不污染交易信号。
4. T 日可见的规则特征能不能形成每日股票面板。
5. TopK Dropout MVP 扣成本后是否仍有组合交易价值。

还没有完成的是：

1. 没有训练任何机器学习模型。
2. 阶段 6 已形成 60/120 日、open/vwap、低/中/高成本完整回测矩阵，但四组中性成本 baseline 成本后超额年化均明显为负。
3. 还没有实现阶段 7 的事件生命周期策略；按阶段 6 结果，应先修正规则与换手问题，再决定是否进入阶段 7。

## 3. 总体数据流

```text
本地 Qlib 数据目录
  calendars/day.txt
  instruments/all.txt
  features/<instrument>/*.day.bin
        |
        v
阶段 1：数据盘点和过滤审计
  data_inventory.py
        |
        +--> data_inventory.csv
        +--> sample_filter_summary.csv
        +--> universe_by_board.csv
        |
        v
阶段 2：突破事件识别和真/假突破标签
  breakout_events.py
        |
        +--> breakout_events_60d.csv / parquet
        +--> breakout_events_120d.csv / parquet
        +--> breakout_event_summary.csv
        +--> manual_check_ohlcv.csv
        |
        v
阶段 3：每日规则特征和日线失真评分
  daily_features.py
        |
        +--> feature_matrix_daily.csv
        +--> feature_dictionary_daily.csv
        +--> feature_matrix_summary.csv
        |
        v
阶段 4：无训练规则模型接入 Qlib
  mylib/handler.py + mylib/model.py + workflow_rule_breakout.yaml
        |
        +--> pred.pkl
        +--> signal analysis records
        |
        v
阶段 5/6：事件研究报告和组合回测
  event_study.py + qrun / PortAnaRecord
        |
        +--> event_study_report.md
        +--> portfolio metrics
        +--> cost sensitivity
```

时间可见性要分清：

```text
T-60 ... T-1:
  用来计算过去窗口最高价、均线、量能基准。

T 日收盘:
  用来判断是否突破，并生成可交易信号候选。

T+1 开盘或 VWAP:
  后续回测里的成交价格，只能用于执行，不用于 T 日信号计算。

T+1 ... T+20:
  只用于研究标签，比如 true_breakout/false_breakout，不允许用于 T 日交易信号。
```

## 4. 阶段 0：参数和口径冻结

### 4.1 目的

把聊天里的策略想法变成固定参数，避免一边看结果一边改定义。

### 4.2 输入

人工确定的研究口径：

```text
突破窗口：60 或 120
ATR 窗口：14
量能窗口：20
成交额历史分位窗口：252
未来标签窗口：20
真突破阈值：未来 20 日最大涨幅 >= 8%
假突破阈值：未来 20 日最大涨幅 < 3%，或最大跌幅 <= -6%，或 5 日内跌回
```

### 4.3 输出

`examples/a_share_breakout/configs/baseline_60d.yaml`：

```yaml
data:
  provider_uri: "~/.qlib/qlib_data/cn_data"
  market: "all"
  start_time: "2021-01-01"
  frequency: "day"

breakout:
  breakout_window: 60
  atr_window: 14
  volume_window: 20
  turnover_rank_window: 252
  retest_window: 5
  holding_window: 20
  true_breakout_return: 0.08
  weak_follow_return: 0.03
  false_breakout_drawdown: -0.06
```

### 4.4 是否使用 Qlib

此阶段不调用 Qlib，只是保存后续脚本和 qrun 需要遵守的参数。

## 5. 阶段 1：数据盘点、清洗与样本过滤

### 5.1 目的

回答三个问题：

1. 本地 Qlib 数据到底覆盖哪些日期和股票。
2. OHLCV、amount、vwap、factor 等字段是否存在。
3. 哪些样本应该在突破研究前剔除或标记为代理处理。

### 5.2 输入

本地 Qlib 数据目录：

```text
~/.qlib/qlib_data/cn_data/
  calendars/day.txt
  instruments/all.txt
  features/sh600000/open.day.bin
  features/sh600000/high.day.bin
  features/sh600000/low.day.bin
  features/sh600000/close.day.bin
  features/sh600000/volume.day.bin
  features/sh600000/amount.day.bin
  features/sh600000/factor.day.bin
  ...
```

交易日历样例：

```text
2000-01-04
2000-01-05
2000-01-06
```

股票池样例：

```text
BJ430017  2023-05-31  2025-09-30
BJ430047  2021-11-15  2025-09-30
BJ430090  2021-11-15  2025-09-30
```

### 5.3 处理

`data_inventory.py` 做几类处理：

| 处理 | 说明 |
|---|---|
| 读取日历 | 从 `calendars/day.txt` 得到交易日索引。 |
| 读取股票池 | 从 `instruments/all.txt` 得到代码、开始日期、结束日期。 |
| 板块分类 | 用代码前缀代理：`SH60*` 主板，`SZ30*` 创业板，`SH68*` 科创板，`BJ*` 北交所。 |
| 字段覆盖检查 | 检查 `open/high/low/close/volume/amount/vwap/factor/change` 的文件和非空覆盖。 |
| 可交易过滤 | 跳过 OHLCV/factor 缺失或 `volume <= 0` 的日期。 |
| 新股过滤 | 用首次有效行情日代理上市日，剔除前 5 日和交易年龄不足 250 日的样本。 |
| 复牌代理过滤 | 前一交易日不可交易、当日可交易时，标记为复牌首日代理。 |
| 一字板代理过滤 | 用 OHLC 近似相等和板块涨幅阈值代理一字涨停。 |

### 5.4 输出

#### 5.4.1 `data_inventory.csv`

用途：字段和数据集覆盖审计。

格式：

```csv
分类,项目,必需性,Qlib来源,状态,覆盖数量,总数,覆盖率,最新可用日期,统计开始,统计结束,说明
```

样例：

```csv
数据集,交易日历,必需,calendars/day.txt,可用,6369,6369,1.0,2026-04-17,2021-01-04,2026-04-17,数据路径：/root/.qlib/qlib_data/cn_data
字段,开盘价,必需,$open,可用,5946,5946,1.0,2026-04-17,2021-01-04,2026-04-17,用于 T+1 开盘执行和缺口分析。
字段,成交额,建议,$amount,可用,5943,5946,0.999495,2026-04-14,2021-01-04,2026-04-17,用于流动性过滤和成交额分位代理。
```

#### 5.4.2 `sample_filter_summary.csv`

用途：记录每条过滤规则剔除了多少样本。

格式：

```csv
规则ID,规则名称,实现状态,是否代理,规则匹配行数_未去重,顺序剔除行数,匹配标的数,适用范围,说明,规则后剩余行数
```

样例：

```csv
00_initial_active_rows,统计窗口内标的-交易日行数,已实现,否,6490642,0,5952,市场文件全部标的,按标的有效区间与请求交易日窗口的交集统计。,6490642
03_missing_required_or_not_tradable,跳过必需 OHLCV/factor 缺失或成交量 <= 0 的日期,已实现,是,17663,17663,1598,股票类板块,停牌和不可交易状态用 close/volume 缺失或 volume <= 0 代理。,6465314
07_one_word_limit_like,跳过近似一字涨停日线,已实现,是,6197,4982,2056,股票类板块,缺少 high_limit/low_limit 字段时，用 OHLC 近似相等和板块涨幅阈值代理。,5997259
```

#### 5.4.3 `universe_by_board.csv`

用途：确认各板块样本分布。

格式：

```csv
板块,标的数,活跃标的数,是否股票类,活跃标的日期行数,可交易行数,阶段1剩余行数,首个交易日,最新交易日,首个标的开始日,最新标的结束日
```

样例：

```csv
主板,3353,3353,是,4043714,4033985,3929400,2021-01-04,2026-04-17,2000-01-04,2026-04-17
创业板,1429,1429,是,1586557,1583683,1435603,2021-01-04,2026-04-17,2009-10-30,2026-04-17
科创板,609,609,是,631009,629657,513899,2021-01-04,2026-04-17,2019-07-22,2026-04-17
```

### 5.5 是否使用 Qlib

使用了 Qlib 的本地数据目录和二进制字段格式，但当前脚本是用 `numpy/pandas` 直接读取文件：

```text
calendars/day.txt
instruments/all.txt
features/<instrument>/<field>.day.bin
```

还没有调用 Qlib 的 `DataHandlerLP`、`DatasetH` 或回测模块。

## 6. 阶段 2：突破事件识别与真/假突破标注

### 6.1 目的

把“突破”从一句话变成一张可复现事件表。事件表用于研究统计，不等于交易下单。

### 6.2 输入

阶段 2 直接读取阶段 1 同一份 Qlib 日线数据，并复用阶段 1 的过滤逻辑。

必需字段：

```text
open, high, low, close, volume, factor
```

建议字段：

```text
amount
```

若没有换手率字段，则用 `amount` 的 252 日历史分位代理流动性和活跃度。

### 6.3 处理

对每只股票、每个交易日 T 计算：

```text
breakout_level[t] = max(close[t-60 : t-1])
atr_14[t] = mean(TrueRange, 14)

candidate[t] =
  close[t] > breakout_level[t]
  and close[t] >= breakout_level[t] + 0.5 * atr_14[t]
  and stage1_filter_pass[t]
```

再计算成交确认：

```text
vol_ratio_20[t] = volume[t] / mean(volume[t-20 : t-1])
vol_ok[t] = vol_ratio_20[t] >= 1.5

amount_rank_252[t] = amount[t] 在过去 252 日中的历史分位
amount_rank_ok[t] = amount_rank_252[t] >= 0.70
```

最后用未来窗口贴研究标签：

```text
future_max_20 = max(close[t+1 : t+20]) / close[t] - 1
future_min_20 = min(close[t+1 : t+20]) / close[t] - 1
retest_fail_5 = any(close[t+1 : t+5] < breakout_level[t] - 1.0 * atr_14[t])

true_breakout =
  (vol_ok or amount_rank_ok)
  and future_max_20 >= 0.08
  and not retest_fail_5

false_breakout =
  retest_fail_5
  or future_max_20 < 0.03
  or future_min_20 <= -0.06
```

注意：`future_max_20`、`future_min_20`、`retest_fail_5` 只用于研究标签，不允许进入后续 T 日交易信号。

### 6.4 输出

#### 6.4.1 `breakout_events_60d.csv` / `breakout_events_120d.csv`

用途：事件级别的真/假突破研究样本。

格式：

```csv
event_date,instrument,board,board_cn,breakout_window,breakout_level,close_t,atr_14,atr_pct,breakout_strength_atr,vol_ratio_20,vol_ratio_3d,amount_rank_252,amount_rank_source,vol_ok,amount_rank_ok,retest_fail_5,future_max_20,future_min_20,label,special_event_flags
```

样例：

```csv
2021-10-26,SZ002776,main_board,主板,60,0.374478,0.393858,0.017555,0.044572,1.103945,2.339959,2.972880,,amount,True,False,False,0.480696,0.017411,true_breakout,none
```

这个样例的含义：

| 字段 | 值 | 解释 |
|---|---:|---|
| `breakout_level` | 0.374478 | T 日之前 60 日最高收盘价。 |
| `close_t` | 0.393858 | T 日收盘价。 |
| `breakout_strength_atr` | 1.103945 | 收盘价高出突破位约 1.10 个 ATR。 |
| `vol_ratio_20` | 2.339959 | 当日成交量约为过去 20 日均量的 2.34 倍。 |
| `future_max_20` | 0.480696 | 未来 20 日最大有利波动约 +48.07%。 |
| `future_min_20` | 0.017411 | 未来 20 日最大不利波动仍约 +1.74%。 |
| `label` | true_breakout | 事后研究标签为真突破。 |

#### 6.4.2 `breakout_event_summary.csv`

用途：汇总事件数量和标签分布。

样例：

```csv
breakout_window,section,name,count
60,candidate,all_candidates,144033
60,candidate,insufficient_future_excluded,3512
60,candidate,events_written,140521
60,label,true_breakout,35491
60,label,false_breakout,92889
60,label,ambiguous,12141
```

#### 6.4.3 `breakout_events_60d_manual_check_ohlcv.csv`

用途：抽样人工核对 K 线，防止事件定义和数据读取错位。

格式：

```csv
breakout_window,instrument,event_date,label,relative_day,datetime,open,high,low,close,volume,breakout_level,atr_14
```

样例：

```csv
60,SZ002776,2021-10-26,true_breakout,-1,2021-10-25,0.359389,0.384080,0.358018,0.374478,1937389.875,0.374478,0.017555
60,SZ002776,2021-10-26,true_breakout,0,2021-10-26,0.370529,0.393858,0.369156,0.393858,2134574.000,0.374478,0.017555
60,SZ002776,2021-10-26,true_breakout,1,2021-10-27,0.393733,0.412940,0.386874,0.412940,3220602.250,0.374478,0.017555
```

### 6.5 是否使用 Qlib

仍然主要使用 Qlib 本地数据格式。此阶段没有调用 Qlib 的策略回测模块。

这样做的原因是：在跑组合回测前，先把事件定义和标签产物查清楚。如果事件表本身不可信，后续 qrun 净值没有解释价值。

## 7. 阶段 3：规则指标库与日线失真评分

### 7.1 目的

把单个事件扩展成每日全市场股票面板。后续 Qlib 的模型接口需要的是“每天每只股票一个分数”，而不是只在突破日才有一行事件。

### 7.2 输入

仍然读取本地 Qlib 日线数据：

```text
open, high, low, close, volume, amount, factor, change
```

并读取基准指数：

```text
SH000300 close
```

用于计算 20 日相对强弱。

### 7.3 处理

每个股票交易日生成以下类型特征：

| 特征组 | 示例字段 | 可用于 T 日交易信号 |
|---|---|---|
| 波动 | `atr_14`, `atr_pct`, `atr_noise_rank_252` | 是 |
| 均线结构 | `ma20`, `ma60`, `ma20_gt_ma60`, `ma20_slope_20` | 是 |
| 布林带宽 | `bb_width_20`, `bb_width_rank_252` | 是 |
| 量能 | `vol_ratio_20`, `vol_ratio_3d`, `volume_spike_no_persistence` | 是 |
| 流动性代理 | `amount_rank_252` | 是 |
| 相对强弱 | `stock_return_20d`, `benchmark_return_20d`, `relative_strength_20d` | 是 |
| 涨停依赖代理 | `limit_dependency_score`, `one_word_limit_like` | 是 |
| 突破强度 | `breakout_level_60d`, `breakout_strength_60d_atr`, `candidate_60d` | 是 |
| 日线失真评分 | `fake_prob_daily_t_60d` | 是 |
| 研究专用次日回吐 | `next_open_return_research`, `fake_prob_daily_research_60d` | 否 |

### 7.4 输出

#### 7.4.1 `feature_matrix_daily.csv`

用途：后续生成规则分数和 Qlib prediction 的基础面板。

格式节选：

```csv
datetime,instrument,board,open,high,low,close,volume,amount,atr_14,atr_pct,atr_noise_rank_252,ma20,ma60,ma20_gt_ma60,ma20_slope_20,bb_width_20,bb_width_rank_252,vol_ratio_20,vol_ratio_3d,volume_spike_no_persistence,amount_rank_252,amount_rank_source,stock_return_20d,benchmark_return_20d,relative_strength_20d,limit_dependency_score,one_word_limit_like,next_open_return_research,next_open_reversal_score_research,breakout_level_60d,breakout_strength_60d_atr,candidate_60d,barely_breakout_score_60d,fake_prob_daily_t_60d,fake_prob_daily_research_60d,breakout_level_120d,breakout_strength_120d_atr,candidate_120d,barely_breakout_score_120d,fake_prob_daily_t_120d,fake_prob_daily_research_120d
```

样例：

```csv
2021-10-26,SZ002776,main_board,0.370529,0.393858,0.369156,0.393858,2134574.000,83304.039,0.017555,0.044572,,0.341726,0.336136,True,0.011562,0.276315,,2.339959,2.972880,0.0,,amount,0.210816,0.022068,0.188748,0.523286,False,-0.000317,0.003169,0.374478,1.103945,True,0.0,,,0.404890,-0.628399,False,,,
```

同一事件在阶段 2 和阶段 3 中的区别：

| 阶段 2 事件表 | 阶段 3 特征矩阵 |
|---|---|
| 只在突破事件日有记录。 | 每个可用交易日、每只股票都有记录。 |
| 包含未来 20 日标签。 | 主要包含 T 日可见特征。 |
| 用于研究“突破后来成功了吗”。 | 用于后续每日排序和回测。 |
| `label` 可用未来数据。 | `fake_prob_daily_t_*` 不能用未来数据；`research` 字段必须隔离。 |

#### 7.4.2 `feature_dictionary_daily.csv`

用途：记录每个字段的定义、可见时间和是否能用于交易信号。

格式：

```csv
feature_name,definition,visible_time,usable_for_trade_signal,implementation_status,missing_data_reason,future_data_source
```

样例：

```csv
atr_14,"Mean(TrueRange, 14)",T close,True,implemented,,
atr_pct,atr_14 / close,T close,True,implemented,,
ma20_gt_ma60,"Mean(close,20) > Mean(close,60)",T close,True,implemented,,
```

#### 7.4.3 `feature_matrix_summary.csv`

用途：特征矩阵行数、日期范围、候选数量和字段覆盖摘要。

样例：

```csv
section,name,value
matrix,rows_written,5997259
matrix,instrument_count,5553
matrix,first_date,2021-01-04
matrix,last_date,2026-04-17
candidate_60d,count,144033
candidate_120d,count,89571
```

### 7.5 是否使用 Qlib

仍然没有进入 Qlib 回测。此阶段是在为 Qlib 后续回测准备“每日股票特征面板”。

换句话说，阶段 3 的输出相当于后续 Qlib `handler/model` 的原材料。

## 8. 阶段 4：无训练信号接入 Qlib

阶段 4 已完成第一版 Qlib 接入。`RuleSignalModel` 不训练参数，只把 T 日可见规则特征转成 Qlib prediction，并已通过标准 qrun 的 `SignalRecord`、`SigAnaRecord` 和 `PortAnaRecord`。

### 8.1 目的

把阶段 3 的规则特征变成 Qlib 标准的 prediction：

```text
MultiIndex(datetime, instrument) -> score
```

Qlib 的组合策略不关心这个分数来自机器学习模型还是规则。它只需要每天每只股票有一个可排序的分数。

### 8.2 输入

阶段 3 输出：

```text
feature_matrix_daily.csv
feature_dictionary_daily.csv
```

或者在 Qlib handler 中实时重算相同字段。

输入样例：

```csv
datetime,instrument,candidate_60d,breakout_strength_60d_atr,ma20_gt_ma60,relative_strength_20d,vol_ratio_3d,atr_noise_rank_252,limit_dependency_score,fake_prob_daily_t_60d
2021-10-26,SZ002776,True,1.103945,True,0.188748,2.972880,,0.523286,
```

### 8.3 处理

计划中的规则分数：

```text
trend_score =
    2.0 * breakout_strength
  + 1.5 * ma_structure_score
  + 1.0 * relative_strength_score
  + 1.0 * volume_persistence_score
  + 0.5 * volatility_regime_score
  - 2.0 * fake_prob_available_at_t
  - 1.0 * limit_dependency_score
```

新增文件：

```text
examples/a_share_breakout/mylib/handler.py
examples/a_share_breakout/mylib/model.py
examples/a_share_breakout/workflow_rule_breakout.yaml
```

Qlib 角色：

| 文件 | Qlib 接口 | 作用 |
|---|---|---|
| `mylib/handler.py` | `DataHandlerLP` 或现有 handler 扩展 | 提供特征列。 |
| `mylib/model.py` | Qlib model 接口 | `fit()` 不训练，只校验列；`predict()` 输出规则分数。 |
| `workflow_rule_breakout.yaml` | qrun task 配置 | 串起 dataset、model、record 和 backtest。 |

### 8.4 输出

已输出 Qlib prediction：

```text
pred.pkl
```

DataFrame 形态示例：

```text
datetime    instrument  score
2021-10-26  SZ002776    2.31
2021-10-26  SH600110    1.84
2021-10-26  SH600038    1.27
```

最近一次全量 qrun 预测窗口为 2025-01-02 至 2026-04-17，生成 `pred.pkl` 50228 行，覆盖 5632 个标的；recorder 为 `mlruns/476777289722113917/80ae45a5cf0b400f8e05bdfccd337e7b`。

### 8.5 是否使用 Qlib

从阶段 4 开始正式使用 Qlib 的 model、dataset、record 和 qrun 工作流。

## 9. 阶段 5：事件研究统计与可视化报告

### 9.1 目的

在看净值前先回答：

1. 真突破和假突破在特征上是否有稳定差异。
2. 结论是否只来自某一年或某个板块。
3. 日线失真评分是否真的能过滤假突破。

### 9.2 输入

```text
breakout_events_60d.csv
breakout_events_120d.csv
feature_matrix_daily.csv
```

### 9.3 处理

按以下维度分组：

```text
label: true_breakout / false_breakout / ambiguous
board: main_board / chinext / star_market / beijing
year: 2021 / 2022 / 2023 / 2024 / 2025 / 2026
amount_rank_252 分位
atr_pct 分位
fake_prob_daily_t 分位
```

对每个特征做差异统计：

```text
真突破均值
假突破均值
中位数差
KS p 值
单变量 AUC
```

### 9.4 输出

已输出：

```text
outputs/event_study_report.md
outputs/event_label_summary.csv
outputs/event_feature_diagnostics.csv
outputs/event_segment_summary.csv
outputs/event_forward_return_curve.csv
outputs/event_forward_return_hac.csv
outputs/figures/event_forward_returns_60d.png
outputs/figures/event_forward_returns_120d.png
outputs/figures/trend_strength_fake_prob_heatmap_60d.png
outputs/figures/trend_strength_fake_prob_heatmap_120d.png
outputs/figures/true_rate_by_fake_prob_60d.png
outputs/figures/true_rate_by_fake_prob_120d.png
```

最近一次本地运行覆盖 2021-01-04 至 2026-03-19，合计 227550 个事件，其中 60 日事件 140521 个、120 日事件 87029 个。

报告表格字段：

```csv
breakout_window,feature,feature_cn,true_mean,false_mean,median_diff_true_minus_false,ks_p_value,true_higher_auc,directional_auc,ks_q_value
60,vol_ratio_3d,3日量能持续性,2.2736,2.4781,-0.0652,0.0,0.4812,0.5188,0.0
```

### 9.5 是否使用 Qlib

主要不需要 Qlib 回测模块。事件研究可以用 pandas/scipy/matplotlib 完成。

## 10. 阶段 6：组合回测 MVP

### 10.1 目的

把“事件看起来有效”变成“扣交易成本后是否能形成组合收益”。

这是第一次真正回答交易问题：

```text
如果每天收盘后按 trend_score 排序，T+1 买入前 8-12 只，扣成本后是否还有正超额？
```

### 10.2 输入

来自阶段 4：

```text
pred.pkl
```

Qlib 回测配置：

```text
benchmark: SH000300
topk: 8 或 10
n_drop: 2 或 3
deal_price: open 或 vwap
open_cost: 0.0003 / 0.0005 / 0.0008
close_cost: 0.0010 / 0.0015 / 0.0020
```

### 10.3 处理

阶段 6 提供两类运行方式。

批量矩阵脚本：

```text
python examples/a_share_breakout/backtest_rule_breakout.py
  -> 每个突破窗口只生成一次规则预测
  -> 复用 pred 跑 open/vwap × 低/中/高成本
  -> 写出 summary、cost sensitivity、yearly return、board exposure 和 deal price audit
```

单组 qrun 配置：

```text
qrun configs/workflow_baseline_60d_open.yaml 等
  -> dataset 生成特征
  -> RuleSignalModel.predict() 输出分数
  -> SignalRecord 记录 pred.pkl
  -> PortAnaRecord 调用 TopkDropoutStrategy
  -> Exchange 应用成交价、涨跌停、成交量限制和交易成本
```

### 10.4 输出

输出 Qlib recorder 产物，典型包括：

```text
pred.pkl
portfolio_analysis/report_normal_1day.pkl
portfolio_analysis/positions_normal_1day.pkl
portfolio_analysis/port_analysis_1day.pkl
```

批量脚本还会输出：

```text
outputs/baseline_backtest_summary.csv
outputs/cost_sensitivity.csv
outputs/baseline_yearly_returns.csv
outputs/baseline_board_exposure.csv
outputs/deal_price_availability_audit.csv
outputs/baseline_backtest_report.md
```

最近一次中性成本结果：

| baseline | 成本后超额年化 | 日均换手 | 持有天数代理 |
|---|---:|---:|---:|
| `baseline_60d_open` | -178.57% | 38.61% | 2.59 |
| `baseline_60d_vwap` | -161.85% | 42.30% | 2.36 |
| `baseline_120d_open` | -211.21% | 48.07% | 2.08 |
| `baseline_120d_vwap` | -181.02% | 52.52% | 1.90 |

结论：低成本场景下四组 baseline 成本后超额年化仍全部为负；当前应暂停进入阶段 7，先回到事件研究、候选过滤、打分和 TopK 换手控制。

### 10.5 是否使用 Qlib

此阶段核心使用 Qlib 的 qrun、record、strategy、exchange 和 backtest 能力。

## 11. 阶段 7：自定义事件策略

### 11.1 目的

如果阶段 6 的 TopK MVP 有价值，再实现更接近真实交易的事件生命周期：

```text
突破日 T 生成事件
T+1 入场
持有最多 20 个交易日
跌破 stop 或 MA20 退出
高失真事件不交易或半仓
```

### 11.2 输入

```text
breakout_events_60d.csv
feature_matrix_daily.csv
pred.pkl 或每日 signal
```

### 11.3 处理

计划新增：

```text
examples/a_share_breakout/mylib/strategy.py
```

每个持仓要保存：

```text
instrument
entry_date
entry_price
breakout_level
atr_14_at_entry
stop_price
max_holding_days
exit_reason
```

### 11.4 输出

计划输出：

```csv
trade_log.csv
```

样例：

```csv
instrument,entry_date,entry_price,exit_date,exit_price,holding_days,entry_reason,exit_reason,return
SZ002776,2021-10-27,0.393733,2021-11-23,0.520000,20,60d_breakout,max_holding_days,0.3207
```

数值是格式示例，不是当前已生成结果。

### 11.5 是否使用 Qlib

使用 Qlib 的自定义策略接口和回测撮合能力。

## 12. 阶段 8：数据增强

### 12.1 目的

补齐日线数据无法严格判断的失真因素。

### 12.2 输入

新增数据源可能包括：

| 数据 | 新字段 |
|---|---|
| 分钟数据 | 尾盘 30 分钟成交占比、30 分钟 VWAP、日内上破时间。 |
| 行业/概念 | 行业相对强弱、行业同步突破、主题拥挤度。 |
| 资金流 | 1 日/3 日主力净流入一致性。 |
| Level-2/逐笔 | 盘口失衡、撤单率、订单-成交比、主动买额。 |

### 12.3 输出

扩展后的特征矩阵：

```csv
datetime,instrument,late_volume_share,close_vs_30m_vwap,industry_rs,flow_consistency_3d,order_book_imbalance_decay,fake_prob_full
```

### 12.4 是否使用 Qlib

取决于数据接入方式。若能转换成 Qlib 格式，可继续用 Qlib data provider；否则先用外部表 join 到阶段 3 的特征矩阵。

## 13. 阶段 9：稳健性和滚动验证

### 13.1 目的

防止只在某段历史里有效。

### 13.2 输入

```text
feature_matrix_daily.csv
breakout_events_60d.csv
pred.pkl
baseline configs
```

### 13.3 处理

滚动窗口示例：

```text
2021-2022 形成 -> 2023 验证
2021-2023 形成 -> 2024 验证
2022-2024 形成 -> 2025 验证
2023-2025 形成 -> 2026 验证
```

参数网格示例：

```text
breakout_window: 60, 90, 120
ATR 倍数: 0.3, 0.5, 0.8
holding_window: 10, 20, 30
topk: 8, 10, 12
```

### 13.4 输出

```csv
walk_forward_summary.csv
```

样例：

```csv
train_period,validation_period,selected_rule,out_sample_return,max_drawdown,turnover,comment
2021-2022,2023,60d_atr0.5_top10,0.08,-0.12,3.8,通过
2021-2023,2024,60d_atr0.5_top10,-0.02,-0.19,4.1,不稳定
```

数值是格式示例，不是当前结果。

### 13.5 是否使用 Qlib

回测部分使用 Qlib；统计检验和参数汇总可以用 pandas/scipy。

## 14. 阶段 10：报告和复现

### 14.1 目的

形成可审计结论，而不是只留下脚本和临时 CSV。

### 14.2 输入

```text
data_inventory.csv
sample_filter_summary.csv
breakout_event_summary.csv
feature_matrix_summary.csv
event_study_report.md
portfolio metrics
walk_forward_summary.csv
```

### 14.3 输出

最终研究报告：

```text
outputs/final_report.md
```

报告要回答：

1. 数据字段有哪些缺口。
2. 样本过滤是否充分。
3. 哪些特征能区分真/假突破。
4. 扣成本后组合是否有效。
5. 是否只依赖单一年份或单一板块。
6. 是否存在未来函数。
7. 是否值得进入小资金模拟。

## 15. 用一个事件串完整数据流

以 `SZ002776` 在 `2021-10-26` 的 60 日突破为例。

### 15.1 原始日线输入

来自 Qlib `features/sz002776/*.day.bin`，阶段 2 抽样核对表中可见：

```csv
relative_day,datetime,open,high,low,close,volume
-1,2021-10-25,0.359389,0.384080,0.358018,0.374478,1937389.875
0,2021-10-26,0.370529,0.393858,0.369156,0.393858,2134574.000
1,2021-10-27,0.393733,0.412940,0.386874,0.412940,3220602.250
```

### 15.2 阶段 1 过滤结果

这条记录需要满足：

```text
股票类板块：main_board
OHLCV/factor 非缺失
volume > 0
交易年龄 > 250
不是复牌首日代理
不是近似一字涨停日
```

满足后才能进入事件识别。

### 15.3 阶段 2 事件识别结果

```csv
event_date,instrument,breakout_window,breakout_level,close_t,atr_14,breakout_strength_atr,vol_ratio_20,vol_ratio_3d,label
2021-10-26,SZ002776,60,0.374478,0.393858,0.017555,1.103945,2.339959,2.972880,true_breakout
```

解释：

```text
close_t 0.393858 > breakout_level 0.374478
close_t - breakout_level = 0.019380
0.019380 / atr_14 0.017555 = 1.103945
```

所以这是一个超过 0.5 ATR 缓冲的 60 日突破。

### 15.4 阶段 3 特征矩阵结果

同一天在每日特征面板中变成：

```csv
datetime,instrument,board,close,ma20,ma60,ma20_gt_ma60,relative_strength_20d,vol_ratio_3d,limit_dependency_score,breakout_level_60d,breakout_strength_60d_atr,candidate_60d
2021-10-26,SZ002776,main_board,0.393858,0.341726,0.336136,True,0.188748,2.972880,0.523286,0.374478,1.103945,True
```

这行数据未来会被阶段 4 转换成一个 `trend_score`。

### 15.5 阶段 4 计划中的 prediction

格式会变成 Qlib 可消费的分数：

```text
datetime    instrument  score
2021-10-26  SZ002776    2.31
```

这里的分数是格式示例。真实分数要等 `RuleSignalModel` 实现后生成。

### 15.6 阶段 6 计划中的交易解释

若阶段 4/6 生成分数后，`SZ002776` 在 `2021-10-26` 收盘后位于全市场 TopK，则组合回测会在 `2021-10-27` 用 open 或 vwap 执行。

```text
T 日：2021-10-26 收盘后产生信号
T+1：2021-10-27 开盘或 VWAP 买入
后续：由 TopK 换仓或自定义事件退出规则卖出
```

如果它只是事后标签为 `true_breakout`，但 T 日分数没有进入 TopK，则组合不会买它。事件研究和组合交易是两层逻辑。

## 16. 关键边界

1. 阶段 1-3 是研究数据流，不是交易系统。
2. 阶段 2 的 `label` 使用未来数据，只能用于统计，不能用于信号。
3. 阶段 3 的 `next_open_*_research` 使用 T+1 数据，只能用于事后归因。
4. 阶段 4 才开始把规则分数接成 Qlib prediction。
5. 阶段 6 已回答第一版 TopK MVP “扣成本后是否能交易”：当前结果不支持直接进入更复杂策略。
6. Qlib 提供通用框架，本目录提供 A 股突破研究的具体定义、过滤、标签和分数。
