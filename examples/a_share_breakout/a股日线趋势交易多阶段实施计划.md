# A股日线趋势交易多阶段实施计划

> 本文基于 `a股趋势交易研究报告.md` 拆解为可执行工程计划。目标是先做**不基于模型训练**的日线趋势/突破研究，用规则、事件标注和回测验证“真突破/假突破”的可交易性。本文不是投资建议，也不是最终策略承诺；所有结论必须以样本外回测、交易成本、滑点、容量和实盘小资金验证为准。

## 1. 总体结论

当前项目适合作为第一阶段实验环境，不建议一开始另起完整项目。

原因：

- Qlib 已经具备数据读取、公式因子、信号记录、组合回测、成本建模和实验产物记录能力。
- 项目中已有 `examples/study_yaml_workflow/` 示例，证明可以用“规则因子直接当预测分数”的方式跑完整 qrun 流水线，`fit` 不做模型训练。
- 本地 `~/.qlib/qlib_data/cn_data` 已有 A 股日线数据，可覆盖日线 OHLCV、成交额、复权因子、vwap 等第一阶段必须字段。
- 报告里的分钟尾盘、盘口、订单簿、资金流、行业拥挤度等内容超出当前日线数据能力，适合后续分阶段补充。

建议仓库组织：

```text
examples/a_share_breakout/
  README.md
  a股趋势交易研究报告.md
  a股日线趋势交易多阶段实施计划.md
  workflow_rule_breakout.yaml
  event_study.py
  backtest_rule_breakout.py
  mylib/
    __init__.py
    handler.py
    model.py
    strategy.py
  configs/
    baseline_60d.yaml
    baseline_120d.yaml
    cost_scenarios.yaml
  outputs/
    .gitignore
```

第一阶段先把实验放在 `examples/a_share_breakout/`，尽量不改 qlib 核心包。等研究闭环稳定后，再考虑抽成单独项目，只依赖 `pyqlib`。

## 2. 研究目标与边界

### 2.1 核心目标

本研究不直接预测下一根 K 线，也不训练机器学习模型预测股价。核心目标是构建一套可复现的事件研究和规则回测流程：

```text
日线数据
  -> 样本清洗与板块分层
  -> 突破候选识别
  -> 未来窗口真/假突破标注
  -> 规则指标与失真过滤
  -> 无训练信号打分
  -> T+1 执行回测
  -> 统计检验与结果报告
```

### 2.2 默认研究假设

| 项目 | 默认值 | 实施说明 |
|---|---|---|
| 样本范围 | 2021-01-01 至最新可用日 | 与报告一致；本地数据目前需先确认最新交易日 |
| 形成期 | 2021-2023 | 用来调规则阈值，不做模型训练 |
| 验证期 | 2024 | 用来筛选规则组合 |
| 留出期 | 2025-最新 | 样本外检验，禁止反复调参污染 |
| 股票池 | 沪深 A 股普通股为主 | 北交所先单独分层，不与沪深混合 |
| 数据频率 | 日线 | 第一阶段不依赖分钟和 Level-2 |
| 形态口径 | 前复权/连续价格 | 用于突破、均线、ATR、布林带等形态计算 |
| 撮合口径 | 未复权或 qlib 可成交价格口径 | 用于回测收益和交易执行 |
| 执行时点 | T 日收盘出信号，T+1 开盘或 VWAP 执行 | 避免未来函数 |
| 基础持有期 | 20 个交易日 | 同时允许止损/趋势退出 |
| 交易成本 | 低/中/高三档 | 印花税、佣金、滑点、最低手续费分开建模 |

### 2.3 明确不做的事情

第一阶段不做：

- 不训练 LightGBM、XGBoost、深度学习或强化学习模型。
- 不使用未来窗口信息生成交易信号。
- 不把“真突破/假突破标签”用于训练预测模型。
- 不基于单日主力净流入做一票通过。
- 不把所有 A 股混成同质样本直接汇总结论。
- 不在没有分钟数据时强行伪造尾盘成交占比、撤单率、盘口失衡等指标。

## 3. 当前项目适配评估

### 3.1 可直接复用的 qlib 能力

| 研究需求 | qlib 可用能力 | 使用方式 |
|---|---|---|
| 日线行情读取 | `qlib.data.D.features`、`QlibDataLoader` | 读取 `$open/$high/$low/$close/$volume/$amount/$factor/$vwap` |
| 公式因子 | `Mean`、`Max`、`Min`、`Std`、`Rank`、`Ref`、`EMA`、`Slope` 等 | 在自定义 handler 里追加表达式 |
| 无训练预测 | 自定义 `FactorColumnModel` | `fit` 返回自身，`predict` 输出规则分数列 |
| qrun 流水线 | `SignalRecord`、`SigAnaRecord`、`PortAnaRecord` | 复用标准实验记录 |
| 排序组合回测 | `TopkDropoutStrategy` | 第一版按规则分数选前 N 只 |
| 成本与交易限制 | `Exchange` | 配置 `deal_price`、`open_cost`、`close_cost`、`limit_threshold`、`volume_threshold` |
| 自定义策略 | `BaseStrategy`、`WeightStrategyBase` | 第二阶段实现 ATR 止损、固定持有期、事件退出 |

### 3.2 当前项目缺口

| 缺口 | 对报告内容的影响 | 处理策略 |
|---|---|---|
| 分钟数据缺失 | 不能计算尾盘 30 分钟成交占比、尾盘 VWAP 偏离、次日开盘回吐的高精度版本 | 第一阶段用日线替代代理；第二阶段接入 1min 数据 |
| Level-2/逐笔数据缺失 | 不能计算盘口挂单失衡、撤单率、订单-成交比 | 作为后续增强，不进入 MVP |
| 资金流字段缺失 | 不能验证主力净流入、大单净额、一致性 | 先不使用；接入外部数据后只作为辅助确认 |
| 行业/概念数据缺失 | 相对行业强弱、主题拥挤度无法精确计算 | 先用指数相对强弱；后续补行业分类 |
| 高低涨跌停字段不完整 | 板块差异和新股前 5 日限制难完全精确 | 第一阶段用 `$change` 与代码前缀近似；后续补 `high_limit/low_limit/list_date/board` |
| ST/退市状态缺失或不完整 | 样本过滤可能不彻底 | 先按名称/股票池文件可得信息过滤；后续补证券状态表 |
| 复牌首日识别不足 | 可能把复牌跳空误判为自然突破 | 用停牌/成交量缺失代理；后续补停复牌字段 |
| qlib 默认 TopK 策略不表达事件生命周期 | 不能天然做到 20 日持有、ATR 止损、Chandelier Exit | MVP 用 TopK；第二版自定义事件策略 |

## 4. 多阶段路线图

### 阶段 0：项目脚手架与口径冻结

目标：把研究从聊天报告变成可追踪的工程实验。

交付物：

- `examples/a_share_breakout/README.md`
- `examples/a_share_breakout/configs/baseline_60d.yaml`
- `examples/a_share_breakout/configs/baseline_120d.yaml`
- `examples/a_share_breakout/outputs/.gitignore`
- 数据字段盘点脚本或 notebook
- 规则口径清单

关键任务：

1. 固定第一版研究参数。
   - `breakout_window = 60`
   - `robust_window = 120`
   - `atr_window = 14`
   - `volume_window = 20`
   - `turnover_rank_window = 252`
   - `retest_window = 5`
   - `holding_window = 20`
   - `true_breakout_return = 0.08`
   - `weak_follow_return = 0.03`
   - `false_breakout_drawdown = -0.06`

2. 固定执行口径。
   - T 日收盘产生信号。
   - T+1 开盘或 T+1 VWAP 成交。
   - 不允许 T 日信号用 T+1 之后的数据。
   - 回测结果分别输出 open 执行和 vwap 执行。

3. 固定数据口径。
   - 形态和指标优先使用连续复权价格。
   - 回测撮合使用 qlib exchange 提供的可成交字段。
   - 停牌日不生成突破事件。
   - 成交量为 0 或 close 缺失视为不可交易。

4. 固定板块分层。
   - 主板：`SH60*`、`SZ00*` 等。
   - 创业板：`SZ30*`。
   - 科创板：`SH68*`。
   - 北交所：`BJ*`。
   - 第一版允许用代码前缀近似，文档中标记为待精修。

阶段验收：

- 能列出本地数据最新交易日、字段覆盖、股票池数量。
- 能输出每个板块的样本数和可交易日期范围。
- 能明确哪些字段真实存在，哪些字段缺失。

### 阶段 1：数据盘点、清洗与样本过滤

目标：建立可复现的数据基础，避免停牌、复权、特殊制度污染事件样本。

最低字段：

| 字段 | 必需性 | 用途 | 当前 qlib 可能字段 |
|---|---|---|---|
| trade_date | 必需 | 时间索引 | `datetime` |
| code | 必需 | 标的索引 | `instrument` |
| open | 必需 | T+1 开盘执行、缺口 | `$open` |
| high | 必需 | ATR、真实波动 | `$high` |
| low | 必需 | ATR、止损判断 | `$low` |
| close | 必需 | 突破、标签、收益 | `$close` |
| pre_close | 建议 | 涨跌幅、缺口 | 可由 `Ref($close, 1)` 代理 |
| volume | 必需 | 量能确认、停牌识别 | `$volume` |
| amount | 建议 | 流动性过滤 | `$amount` 或 `$money` |
| vwap | 建议 | T+1 VWAP 执行 | `$vwap`，需检查缺失 |
| adj_factor | 必需 | 复权口径 | `$factor` |
| paused | 建议 | 停牌过滤 | 可由 close/volume 缺失代理 |
| high_limit/low_limit | 建议 | 涨跌停过滤 | 当前缺，后续补 |
| list_date | 建议 | 新股前 250 日/前 5 日过滤 | 当前缺，后续补 |
| ST 状态 | 建议 | 剔除 ST/*ST | 当前缺，后续补 |
| board | 建议 | 板块分层 | 第一版代码前缀代理 |

过滤规则：

- 剔除 B 股。
- 剔除 ST、*ST、退市整理期，若状态字段缺失则标记为暂未完全处理。
- 剔除上市不足 250 个交易日的样本，若 `list_date` 缺失则用首次有效行情日代理。
- 事件识别跳过停牌日和成交量为 0 的日期。
- 跳过复牌首日，第一版用前一交易日无成交/无 close 代理。
- 跳过新股上市前 5 个交易日，第一版用首次有效行情日代理。
- 跳过连续一字涨停后首次打开的交易日，第一版若无涨跌停价字段则暂不严格执行。
- 跳过除权除息价格台阶异常且复权口径无法修正的日期。

阶段验收：

- 输出 `data_inventory.csv`。
- 输出 `sample_filter_summary.csv`，包含每条剔除规则的样本数。
- 输出 `universe_by_board.csv`，包含主板、创业板、科创板、北交所样本分布。
- 文档记录未能严格实现的过滤项。

实施记录（2026-05-17）：

- 已创建 `examples/a_share_breakout/` 阶段 1 实验目录。
- 已实现 `examples/a_share_breakout/data_inventory.py`，默认读取本地 `~/.qlib/qlib_data/cn_data`。
- 已生成 `examples/a_share_breakout/outputs/data_inventory.csv`、`sample_filter_summary.csv`、`universe_by_board.csv`。
- 本地运行窗口为 2021-01-04 至 2026-04-17，活跃标的 5952 个，其中代码前缀识别的 A 股股票类标的 5946 个。
- README 已记录阶段 1 的代理口径和缺口：ST/退市状态、高低涨跌停价、严格连续一字板打开日、除权除息异常、分钟尾盘、Level-2、资金流和行业字段仍待后续数据补充。

### 阶段 2：突破事件识别与真/假突破标注

目标：把报告中的“真突破/假突破”定义变成可复现事件表。

候选事件默认规则：

```text
breakout_level[t] = max(close[t-60 : t-1])
atr[t] = ATR(14)

candidate[t] =
  close[t] > breakout_level[t]
  and close[t] >= breakout_level[t] + 0.5 * atr[t]
  and tradable[t] == true
  and not special_event[t]
```

成交确认：

```text
vol_ratio[t] = volume[t] / mean(volume[t-20 : t-1])
vol_ok[t] = vol_ratio[t] >= 1.5

turnover_ok[t] =
  turnover_pct[t] >= rolling_percentile(turnover_pct[t-252 : t-1], 70%)
```

如果没有换手率字段：

- 第一版使用 `amount` 或 `volume` 的 252 日分位替代。
- 文档中明确“换手率分位未严格实现”。

未来窗口标签：

```text
future_max_20 = max(close[t+1 : t+20]) / close[t] - 1
future_min_20 = min(close[t+1 : t+20]) / close[t] - 1
retest_fail_5 = any(close[t+1 : t+5] < breakout_level[t] - 1.0 * atr[t])

true_breakout =
  (vol_ok or turnover_ok)
  and future_max_20 >= 0.08
  and not retest_fail_5

false_breakout =
  retest_fail_5
  or future_max_20 < 0.03
  or future_min_20 <= -0.06

otherwise = ambiguous
```

注意事项：

- 标签允许用未来数据，因为标签只用于研究统计，不用于生成交易信号。
- 交易信号只能使用 T 日及以前可见数据。
- 事件标签、特征矩阵、交易信号要分开落盘，避免误用。

事件表字段：

| 字段 | 说明 |
|---|---|
| event_date | 突破确认日 T |
| instrument | 股票代码 |
| board | 板块 |
| breakout_window | 60 或 120 |
| breakout_level | T 日之前形成的突破位 |
| close_t | T 日收盘 |
| atr_14 | T 日 ATR |
| atr_pct | `atr_14 / close_t` |
| vol_ratio_20 | 单日量比 |
| vol_ratio_3d | 3 日量能持续性 |
| amount_rank_252 | 成交额历史分位 |
| retest_fail_5 | 5 日是否跌回 |
| future_max_20 | 20 日最大有利波动 |
| future_min_20 | 20 日最大不利波动 |
| label | `true_breakout/false_breakout/ambiguous` |
| special_event_flags | 特殊事件标记 |

阶段验收：

- 生成 `breakout_events_60d.parquet/csv`。
- 生成 `breakout_events_120d.parquet/csv`。
- 随机抽样 20 个事件人工核对 K 线。
- 检查事件日后 20 日不足的样本不参与标签统计。

实施记录（2026-05-17）：

- 已实现 `examples/a_share_breakout/breakout_events.py`，默认一次生成 60 日和 120 日突破事件。
- 已生成 `examples/a_share_breakout/outputs/breakout_events_60d.csv`、`breakout_events_60d.parquet`、`breakout_events_120d.csv`、`breakout_events_120d.parquet`。
- 已生成 `breakout_event_summary.csv`，记录候选事件、未来 20 日不足剔除数、标签分布和板块-标签分布。
- 已生成 `breakout_events_60d_manual_check_ohlcv.csv` 和 `breakout_events_120d_manual_check_ohlcv.csv`，每个窗口随机抽样 20 个事件并输出 `T-5` 至 `T+20` 的 OHLCV 核对行。
- 本地 2021-01-04 至 2026-04-17 窗口内，60 日突破候选 144033 个，未来 20 日不足剔除 3512 个，输出可标注事件 140521 个；其中真突破 35491、假突破 92889、不确定 12141。
- 同一窗口内，120 日突破候选 89571 个，未来 20 日不足剔除 2542 个，输出可标注事件 87029 个；其中真突破 21557、假突破 59730、不确定 5742。
- 已通过 `python -m py_compile examples/a_share_breakout/data_inventory.py examples/a_share_breakout/breakout_events.py`、`pytest -q tests/test_a_share_breakout_breakout_events.py tests/test_a_share_breakout_data_inventory.py` 和 CSV/Parquet 行数一致性审计。
- 换手率分位仍未严格实现；阶段 2 使用成交额 252 日历史分位作为代理，若成交额不可用则回落到成交量分位并在 `amount_rank_source` 中标记。
- 标签使用未来 5/20 日数据，仅用于事件研究统计；突破候选、量能确认和成交额分位只使用 T 日及以前可见数据。

### 阶段 3：规则指标库与失真评分

目标：实现报告中的高优先级指标、辅助确认指标和风险过滤指标。

#### 3.1 高优先级主判据

| 指标 | 默认实现 | 当前阶段 |
|---|---|---|
| 60/120 日突破 | `close > Ref(Max($close, N), 1)` | MVP |
| ATR/NATR | `ATR(14) / close` | MVP |
| 均线斜率 | `Slope(Mean($close, 20), 20)` 或 `Mean($close,20)-Ref(Mean($close,20),20)` | MVP |
| MA20/MA60 结构 | `Mean($close,20) > Mean($close,60)` | MVP |
| 相对强弱 | 个股收益减指数收益，或个股/指数比值创新高 | MVP 简化 |
| 布林带宽 | `(Mean(close,N)+2*Std(close,N) - (Mean(close,N)-2*Std(close,N))) / Mean(close,N)` | MVP |
| 波动收缩后扩张 | 布林带宽历史低分位后上升 | 第二轮 |
| ADX/DMI | 标准 ADX 公式 | 第二轮，可能需要 pandas/talib 自算 |

#### 3.2 辅助确认指标

| 指标 | 默认实现 | 当前阶段 |
|---|---|---|
| 单日量比 | `volume / Mean(Ref(volume,1),20)` | MVP |
| 3 日均量放大 | `Mean(volume,3) / Mean(Ref(volume,3),20)` | MVP |
| 成交额分位 | `Rank(amount,252)` | MVP |
| 换手率分位 | 需流通股本 | 后续补 |
| 3 日资金流一致性 | 需资金流数据 | 后续补 |

#### 3.3 风险过滤指标

| 指标 | 默认实现 | 当前阶段 |
|---|---|---|
| 接近涨跌停依赖 | `abs($change)` 接近板块阈值 | MVP 简化 |
| 一字板过滤 | high/low/open/close 近似相等且涨幅接近涨停 | MVP 简化 |
| 次日回吐 | `open[t+1]/close[t]-1`，只用于事件研究 | MVP |
| 尾盘扭曲 | 需要分钟数据 | 后续补 |
| 盘口失衡衰减 | 需要 Level-2 | 后续补 |
| 订单-成交比/撤单率 | 需要 Level-2 | 后续补 |

#### 3.4 失真概率分数

报告建议的完整框架：

```text
fake_prob
= sigmoid(
    0.22 * 尾盘成交占比异常
  + 0.18 * 收盘价相对30分钟VWAP偏离
  + 0.18 * 次日开盘回吐率
  + 0.15 * 单日量能突刺但3日不持续
  + 0.12 * 订单簿失衡衰减过快
  + 0.10 * 接近涨跌停板依赖度
  + 0.05 * 1日资金流与3日资金流不一致
)
```

第一阶段可实现的简化版本：

```text
fake_prob_daily
= sigmoid(
    0.30 * 次日开盘回吐率_研究用
  + 0.25 * 单日量能突刺但3日不持续
  + 0.20 * 接近涨跌停板依赖度
  + 0.15 * 高ATR噪声分位
  + 0.10 * 收盘刚好越过突破位
)
```

重要限制：

- `次日开盘回吐率` 不能用于 T 日实时交易信号，只能用于事件归因或事后标签分析。
- 若要在实盘前过滤，只能使用 T 日及以前字段，例如“收盘刚好越过突破位”“单日量突刺但 3 日不持续”“接近涨停”等。
- 完整 `fake_prob` 必须等分钟或 Level-2 数据接入后再实现。

阶段验收：

- 输出 `feature_matrix_daily.csv`。
- 每个指标有定义、可见时间、是否可用于交易信号的标记。
- 每个缺失指标有“缺数据原因”和“后续数据源”。

实施记录（2026-05-17）：

- 已实现 `examples/a_share_breakout/daily_features.py`，默认读取本地 `~/.qlib/qlib_data/cn_data`，生成阶段 1 过滤后的日线规则指标矩阵。
- 已生成 `examples/a_share_breakout/outputs/feature_matrix_daily.csv`、`feature_dictionary_daily.csv`、`feature_matrix_summary.csv`。
- 本地 2021-01-04 至 2026-04-17 窗口内，输出 5997259 行、5553 个标的，覆盖主板、创业板、科创板、北交所。
- 阶段 3 特征包含 60/120 日突破位与 ATR 强度、ATR/NATR、MA20/MA60 结构、MA20 斜率、布林带宽、20 日相对 `SH000300` 强弱、单日量比、3 日量能持续性、成交额 252 日分位、涨停依赖代理、一字板代理和日线简化失真评分。
- `fake_prob_daily_t_60d` / `fake_prob_daily_t_120d` 只使用 T 日及以前可见字段；`fake_prob_daily_research_60d` / `fake_prob_daily_research_120d` 加入 T+1 开盘回吐，只能用于事后归因。
- `feature_dictionary_daily.csv` 已记录每个指标的定义、可见时间和是否可用于交易信号，并记录缺失的换手率、精确涨跌停价、尾盘 30 分钟、Level-2、资金流、行业强弱和标准 ADX/DMI 所需数据源。
- `feature_matrix_summary.csv` 中 60 日候选突破 144033 个、120 日候选突破 89571 个，与阶段 2 候选统计一致。
- 已通过 `python -m py_compile examples/a_share_breakout/daily_features.py`、`pytest -q tests/test_a_share_breakout_daily_features.py` 和全量阶段 3 生成命令。

### 阶段 4：无训练信号与 qlib 流水线

目标：把规则指标转换成 qlib 可回测的每日股票分数。

第一版信号：

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

其中：

```text
breakout_strength = (close - breakout_level) / atr
ma_structure_score = I(MA20 > MA60) + normalized(MA20_slope)
relative_strength_score = rank(stock_return_20d - benchmark_return_20d)
volume_persistence_score = rank(Mean(volume,3) / Mean(volume,20))
volatility_regime_score = low_to_mid ATR/BB width regime, not extreme high noise
```

qlib 实现方式：

- `mylib/handler.py`
  - 继承 `Alpha158` 或直接继承 `DataHandlerLP`。
  - 追加规则特征列。
  - 第一版尽量只用 qlib 表达式能表达的指标。

- `mylib/model.py`
  - 实现 `RuleSignalModel`。
  - `fit(dataset)` 不训练，只做列存在性校验。
  - `predict(dataset, segment="test")` 输出 `trend_score`。

- `workflow_rule_breakout.yaml`
  - `task.model` 使用 `RuleSignalModel`。
  - `task.dataset.handler` 使用自定义 handler。
  - `PortAnaRecord` 使用 `TopkDropoutStrategy`。

第一版组合参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| topk | 8 或 10 | 更贴近报告建议的 8-12 只 |
| n_drop | 2 或 3 | 控制换手 |
| risk_degree | 0.95 | 预留现金 |
| deal_price | open 和 vwap 分别跑 | 对比追突破与稳健执行 |
| open_cost | 0.0003-0.0005 | 情景参数 |
| close_cost | 0.0010-0.0015 | 卖出端含印花税情景 |
| min_cost | 5 | qlib 默认可配置 |

阶段验收：

- qrun 能生成 `pred.pkl`。
- `pred.pkl` 中每日每股有一列规则分数。
- `SignalRecord` 和 `PortAnaRecord` 正常完成。
- 不调用任何训练模型。

### 阶段 5：事件研究统计与可视化报告

目标：先分析事件规律，再看净值曲线，降低过拟合风险。

核心统计：

| 维度 | 输出 |
|---|---|
| 标签分布 | 真突破、假突破、不确定事件数量 |
| 板块分层 | 主板、创业板、科创板、北交所分别统计 |
| 年份分层 | 2021、2022、2023、2024、2025、2026 |
| 市场环境 | 指数 MA60 上/下、成交额扩张/收缩 |
| 流动性分组 | 成交额分位、成交量分位 |
| 波动分组 | ATR% 分位、布林带宽分位 |
| 失真分组 | 低/中/高 fake_prob |

指标差异表模板：

| 指标 | 真突破均值 | 假突破均值 | 中位数差 | KS p 值 | 单变量 AUC | 解释 |
|---|---:|---:|---:|---:|---:|---|
| 成交量放大比 | 待计算 | 待计算 | 待计算 | 待计算 | 待计算 | 观察量能持续性 |
| 3 日量能持续性 | 待计算 | 待计算 | 待计算 | 待计算 | 待计算 | 替代单日突刺 |
| ADX 或趋势强度 | 待计算 | 待计算 | 待计算 | 待计算 | 待计算 | 第二轮补 ADX |
| ATR% | 待计算 | 待计算 | 待计算 | 待计算 | 待计算 | 高噪声过滤 |
| 相对强弱 | 待计算 | 待计算 | 待计算 | 待计算 | 待计算 | 个股是否强于指数 |
| 尾盘扭曲分数 | 缺数据 | 缺数据 | 缺数据 | 缺数据 | 缺数据 | 需分钟数据 |

图表：

- 事件后 1-20 日平均累计收益曲线。
- 真突破/假突破按特征分位的柱状图。
- `趋势强度 × 失真概率` 热力图。
- 按年份分面的收益/胜率图。
- 按板块分面的突破成功率图。
- 市场成交额扩张/收缩状态下的策略表现。

统计检验：

- 事件后窗口重叠时，收益均值和回归系数使用 Newey-West HAC 标准误。
- 多参数网格比较时，后续引入 White Reality Check 或 Hansen SPA。
- 多单变量检验时，使用 Benjamini-Hochberg FDR 控制伪阳性。
- 若比较两个信号分数样本外预测表现，可使用 Diebold-Mariano 或 Giacomini-White。

阶段验收：

- 输出 `event_study_report.md`。
- 输出图表目录 `outputs/figures/`。
- 能回答“哪些特征稳定区分真/假突破”。
- 能回答“结论是否只来自某一年或某个板块”。

### 阶段 6：组合回测 MVP

目标：用最简单的可交易规则验证是否值得继续做复杂策略。

交易规则：

```text
每日收盘后：
  1. 计算所有股票 trend_score。
  2. 过滤不可交易、特殊事件、高失真、高涨停依赖样本。
  3. 选分数最高的 8-12 只。
  4. T+1 开盘或 VWAP 买入。
  5. TopK Dropout 每日小幅调仓。
```

回测设置：

| 场景 | deal_price | open_cost | close_cost | 滑点/impact | 目的 |
|---|---|---:|---:|---:|---|
| 乐观 | open | 0.0003 | 0.0010 | 0 | 上限参考 |
| 中性 | open | 0.0005 | 0.0015 | 0.0005 | 主报告 |
| 保守 | vwap/open 较差侧 | 0.0008 | 0.0020 | 0.0010 | 压力测试 |

评价指标：

- 年化收益。
- 最大回撤。
- 信息比率。
- 超额收益均值与波动。
- 胜率。
- 换手率。
- 单票平均持有天数。
- 成本前后收益差。
- 分年度收益。
- 分板块贡献。

阶段验收：

- 形成 `baseline_60d_open`、`baseline_60d_vwap`、`baseline_120d_open`、`baseline_120d_vwap` 四组结果。
- 输出成本敏感性表。
- 若成本后收益消失，暂停进入复杂策略，回到事件研究修正规则。

### 阶段 7：自定义事件策略

目标：摆脱 TopK Dropout 的限制，实现报告里的事件进入、持有期、ATR 止损和趋势退出。

策略规则：

```text
入场：
  T 日收盘出现有效突破，T+1 买入。

初始止损：
  stop = breakout_level - 1.2 * ATR(14)

退出：
  1. 收盘跌破 stop。
  2. 跌破 MA20。
  3. Chandelier Exit 触发。
  4. ADX 高位回落且价格失守。
  5. 持有满 20 日仍无延续。
  6. 出现更高优先级风险过滤信号。

仓位：
  低失真概率：正常权重。
  中失真概率：半权重。
  高失真概率：不交易。
```

仓位约束：

- 单票 5%-10%。
- 总持仓 8-12 只。
- 单板块或单主题集中度上限。
- 高波动股票权重下调。
- 流动性不足股票权重下调。

实现方式：

- 新增 `mylib/strategy.py`。
- 继承 `BaseStrategy` 或 `WeightStrategyBase`。
- 使用事件表或每日信号表管理持仓生命周期。
- 对每个持仓记录入场日、突破位、ATR、止损价、事件来源。

阶段验收：

- 策略能复现实验规则，不再依赖每日 TopK 强制换仓。
- 持仓日志能解释每笔交易的入场和退出原因。
- 对比 TopK MVP，确认自定义策略是否降低换手和回撤。

### 阶段 8：数据增强

目标：补齐报告中当前日线数据无法实现的关键失真检测。

优先级 1：分钟数据。

新增指标：

- 尾盘 30 分钟成交占比。
- 尾盘收益占全天收益比例。
- 收盘价相对 30 分钟 VWAP 偏离。
- T+1 开盘回吐。
- 日内 VWAP 上破，而非 close-only 上破。

优先级 2：行业/概念数据。

新增指标：

- 个股相对行业强弱。
- 行业指数是否同步突破。
- 行业内排名。
- 主题拥挤度。
- 行业中性超额收益。

优先级 3：资金流数据。

新增指标：

- 1 日主力净流入。
- 3 日主力净流入中位数。
- 1 日与 3 日资金流一致性。
- 大单/超大单净额持续性。

注意：

- 资金流依赖供应商口径，不能作为单独一票通过。
- 资金流只适合作为辅助确认或仓位折扣。

优先级 4：Level-2/逐笔数据。

新增指标：

- 订单簿失衡。
- 失衡衰减速度。
- 撤单率。
- 订单-成交比。
- 主动买额占比。
- 已成交净主动买额。

阶段验收：

- 完整实现报告版 `fake_prob`。
- 对比“日线简化 fake_prob”和“分钟/L2 fake_prob”的过滤效果。
- 明确额外数据是否真正提升样本外表现。

### 阶段 9：稳健性、滚动验证与偏差控制

目标：防止参数挖掘得到只在历史有效的规则。

滚动验证设计：

```text
方案 A：Anchored
  2021-2023 形成
  2024 验证
  2025-2026 留出

方案 B：Walk-forward
  2021-2022 形成 -> 2023 验证
  2021-2023 形成 -> 2024 验证
  2022-2024 形成 -> 2025 验证
  2023-2025 形成 -> 2026 验证
```

参数网格：

| 参数 | 候选值 |
|---|---|
| breakout_window | 60, 90, 120 |
| ATR 倍数 | 0.3, 0.5, 0.8 |
| retest ATR | 0.8, 1.0, 1.2 |
| holding_window | 10, 20, 30 |
| true_return | 5%, 8%, 10% |
| max_drawdown | -4%, -6%, -8% |
| topk | 8, 10, 12 |
| n_drop | 1, 2, 3 |

偏差控制：

- 参数搜索只在形成期和验证期做。
- 留出期只跑最终少数规则。
- 每次参数变更要记录原因，不能只因为净值好看。
- 多参数比较后做 Reality Check 或 SPA。
- 多单变量指标检验后做 FDR 控制。

阶段验收：

- 输出 `walk_forward_summary.csv`。
- 输出 `parameter_sensitivity.md`。
- 明确哪些参数稳定，哪些参数脆弱。
- 如果策略只在单一年份有效，结论降级为“阶段性现象”。

### 阶段 10：报告、复现与后续工程化

目标：让研究可以复现、审计和继续迭代。

最终报告结构：

```text
1. 研究问题
2. 数据来源与字段缺口
3. 样本过滤与板块分层
4. 突破事件定义
5. 真/假突破标签统计
6. 指标库与失真评分
7. 无训练规则信号
8. 组合回测
9. 成本与滑点敏感性
10. 分年份/板块/市场环境稳健性
11. 偏差控制与统计检验
12. 缺失数据与后续计划
13. 是否进入小资金模拟观察
```

复现要求：

- 所有配置写入 `configs/`。
- 所有运行命令写入 README。
- 所有输出表格带运行日期和数据截止日。
- 每个实验有唯一名称。
- 不把大体积输出提交到 git。
- 重要结果以小表格或 markdown 摘要提交。

进入实盘模拟前的最低门槛：

- 留出期成本后仍为正超额。
- 最大回撤可接受。
- 分年度不是单一年份贡献。
- 高成本情景下不崩溃。
- 低流动性过滤后仍有足够交易样本。
- 持仓日志能解释交易原因。
- 无未来函数。
- 数据缺口已明确，不能把缺失指标当已验证结论。

## 5. 第一版 MVP 规则建议

为了尽快跑通闭环，第一版规则不追求完整复刻报告所有指标。

候选规则：

```text
candidate =
  close > Ref(Max($close, 60), 1)
  and close >= Ref(Max($close, 60), 1) + 0.5 * ATR14
  and Mean($volume, 3) / Mean(Ref($volume, 3), 20) >= 1.2
  and Mean($close, 20) > Mean($close, 60)
  and close / Mean($close, 20) < 1.20
  and abs($change) < board_limit_guard
```

打分：

```text
score =
    1.5 * ((close - breakout_level) / ATR14)
  + 1.0 * MA20_slope_rank
  + 1.0 * relative_strength_rank
  + 0.8 * volume_persistence_rank
  - 1.0 * ATR_noise_rank
  - 1.0 * limit_dependency
```

过滤：

```text
filter_out =
  suspended
  or new_stock_first_250_days
  or first_5_trading_days
  or likely_ST
  or amount too low
  or one_word_limit_like
  or close just barely above breakout_level without ATR buffer
```

输出：

- `score` 用于 qlib 回测。
- `candidate` 用于事件研究。
- `label` 只用于事后统计。

## 6. 必须显式记录的缺失项

| 报告提到的点 | 第一版是否实现 | 说明 |
|---|---|---|
| 主板/创业板/科创板/北交所分层 | 部分实现 | 先用代码前缀代理，后续补官方板块字段 |
| 新股上市前 5 日剔除 | 部分实现 | 先用首次有效行情日代理 |
| 上市不足 250 日剔除 | 部分实现 | 先用首次有效行情日代理 |
| ST/*ST/退市整理剔除 | 待补 | 需要证券状态或名称历史 |
| 停牌日跳过 | 部分实现 | 用 close/volume 缺失或 0 代理 |
| 复牌首日剔除 | 部分实现 | 用前一日不可交易代理 |
| 未复权撮合、前复权形态 | 部分实现 | 需确认 qlib 本地价格和 factor 口径 |
| 高低涨跌停价 | 待补 | 当前需用 `$change` 和板块阈值近似 |
| 尾盘集合竞价扭曲 | 待补 | 需要分钟数据，日线不能严格实现 |
| 30 分钟 VWAP 偏离 | 待补 | 需要分钟数据 |
| 盘口订单失衡 | 待补 | 需要 Level-2 |
| 撤单率/虚假申报代理 | 待补 | 需要 Level-2 或逐笔委托 |
| 主力资金流 | 待补 | 需要外部供应商字段 |
| 行业相对强弱 | 待补 | 需要行业分类和行业指数 |
| ADX 标准实现 | 第二轮 | 可用 pandas/talib 自算或自定义算子 |
| White Reality Check / SPA | 后期 | MVP 后再做 |
| Newey-West HAC | 后期 | 事件研究报告阶段做 |

## 7. 推荐执行顺序

优先级从高到低：

1. 建立 `examples/a_share_breakout/` 实验目录。
2. 做本地数据盘点和字段缺口报告。
3. 实现 60/120 日突破事件识别。
4. 生成真/假/不确定标签。
5. 实现 MVP 规则分数。
6. 用 qlib 跑无训练 TopK 回测。
7. 输出事件研究统计报告。
8. 做 open/vwap、低/中/高成本敏感性。
9. 实现自定义事件策略。
10. 补分钟、行业、资金流、Level-2 数据。
11. 做 walk-forward 和统计检验。
12. 决定是否独立成项目或进入模拟观察。

## 8. 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| 数据幸存者偏差 | 回测高估 | 使用历史成分/全市场并记录股票池口径 |
| 未来函数 | 策略不可交易 | 严格区分信号、标签、执行时间 |
| 复权口径混乱 | 突破和收益失真 | 形态口径和撮合口径分开 |
| 停牌填充 | 伪造平台整理 | 停牌日不生成事件 |
| 单日量价被操纵或扭曲 | 假突破误判 | 用跨日确认和失真过滤 |
| 涨跌停制度差异 | 板块间统计不可比 | 板块分层 |
| 参数过拟合 | 样本外失效 | 留出期和 Reality Check |
| 成本低估 | 净值虚高 | 低/中/高成本情景 |
| 流动性不足 | 实盘不可成交 | 成交额过滤和容量评估 |
| 外部数据口径不一致 | 难复现 | 记录供应商、字段定义和版本 |

## 9. 下一步最小任务

下一步不需要先补所有数据。建议按下面 5 个任务开始：

1. 创建 `examples/a_share_breakout/`。
2. 写 `data_inventory.py`，输出本地字段、日期范围、股票池统计。
3. 写 `event_study.py`，生成 60/120 日突破事件表。
4. 写 `mylib/handler.py` 和 `mylib/model.py`，生成无训练规则分数。
5. 写 `workflow_rule_breakout.yaml`，跑第一版 qlib 回测。

完成这 5 步后，再根据事件统计结果决定是否值得进入自定义策略和分钟数据阶段。
