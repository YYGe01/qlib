# examples 因子说明

本文梳理当前 `examples` 目录里用到的主要因子集、handler 和直接 `D.features` 表达式。这里的“因子”指由 Qlib 表达式或 DataHandler 生成、供模型训练/预测使用的特征列；`Alpha158`、`Alpha360` 更准确地说是“因子集”。

## 范围与读法

统计范围包括：

- `examples/**/*.yaml`、`examples/**/*.yml` 中的 `dataset.kwargs.handler` 配置。
- `examples/**/*.py` 中直接构造的 `Alpha158`、`Alpha360`、自定义 handler、`D.features(...)` 表达式。
- `examples/**/*.ipynb` 中出现的教程式 Alpha158 用法。

不纳入因子的内容：

- 模型参数、回测参数、processor 标准化参数。
- `SignalRecord`、`PortAnaRecord` 等记录器。
- `TRA/configs/*` 中的 `StaticDataLoader` 只指向已有 `data/feature.pkl`、`data/label.pkl`，配置文件本身没有定义可展开的表达式，因此本文只说明其数据来源形态。

表达式约定：

- `$close`、`$open`、`$high`、`$low`、`$vwap`、`$volume` 是当前行对应日期和标的的原始字段。
- `Ref($close, 5)` 表示 5 个 bar 以前的收盘价；在日频下就是 5 个交易日前。
- `Ref($close, -1)` 表示未来 1 个 bar 的收盘价；常用于构造 label，不能作为交易当日可见特征。
- `Mean($close, 20)`、`Std($close, 20)`、`Corr(a, b, 20)` 是 rolling window 表达式。
- 文中的样例默认以当前时点 `t` 为基准，窗口参数 `d` 取 `5` 举例；实际 Alpha158 会把很多 rolling 因子扩展到 `d in {5, 10, 20, 30, 60}`。

## 当前 examples 使用总览

| 因子集 / handler | 主要来源 | 典型使用位置 | 特征形态 | 样例 |
| --- | --- | --- | --- | --- |
| `Alpha158` | `qlib.contrib.data.handler.Alpha158` -> `Alpha158DL` | 多数传统模型 benchmark、`workflow_by_code.py`、`model_interpreter`、`portfolio`、`rolling_process_data`、`highfreq` 的 Alpha158 YAML | 158 个日频技术因子，部分例子会改为 1min 或多频取数 | `ROC5 = Ref($close, 5) / $close` |
| `Alpha360` | `qlib.contrib.data.handler.Alpha360` -> `Alpha360DL` | 多数深度模型 benchmark，如 ALSTM、GRU、Transformer、TCN、HIST、TCTS 等 | 最近 60 个 bar 的 6 类原始量价序列，共 360 列 | `CLOSE5 = Ref($close, 5) / $close` |
| LightGBM configurable 13 因子 | `examples/benchmarks/LightGBM/workflow_config_lightgbm_configurable_dataset.yaml` | 自定义 `DataHandlerLP` + `QlibDataLoader` 示例 | 从 Alpha158 风格因子中手工选 13 列 | `WVMA5 = Std(abs(ret)*volume, 5) / Mean(abs(ret)*volume, 5)` |
| `Avg15minHandler` | `examples/benchmarks/LightGBM/multi_freq_handler.py` | `workflow_config_lightgbm_multi_freq.yaml` | 日频 OHLCV + 1min 数据聚合成 15min 桶 | `close16 = Mean($close, 15)` |
| Alpha158 多频示例 | `workflow_config_lightgbm_Alpha158_multi_freq.yaml` | LightGBM 多频示例 | Alpha158 表达式不变，但 feature 从 1min 取样到日频，label 仍用日频 | `Resample1minProcessor(hour=14, minute=56)` 取 14:56 的 1min bar |
| `StudyAlpha158` | `examples/study_yaml_workflow/mylib/handler.py` | `workflow_rule_factor.yaml` | Alpha158 加 1 个规则趋势因子 | `MA_TREND_5_20 = Mean($close, 5) - Mean($close, 20)` |
| `AShareBreakoutRuleHandler` | `examples/a_share_breakout/mylib/handler.py` | A 股突破规则 workflow 与 baseline | 20 个日线突破/量能/趋势/伪突破规则因子 | `BREAKOUT_STRENGTH_60D = ($close - Ref(Max($close, 60), 1)) / ATR_14` |
| `HighFreqHandler` | `examples/highfreq/highfreq_handler.py` | `examples/highfreq/workflow.py` | 1min 当前日/上一日标准化 OHLCV | `$open = Cut($open / Ref(DayLast($close), 240), 240, None)` 的同类表达式 |
| `HighFreqGeneralHandler` | `qlib.contrib.data.highfreq_handler` | `rl_order_execution/scripts/pickle_data_config.yml` | 可配置分钟频字段，生成当前值、上一日值、成交量归一化 | `$close_1 = Ref($close, day_length) / DayLast(Ref($close, day_length))` 的同类表达式 |
| `HighFreqBacktestHandler` / `HighFreqGeneralBacktestHandler` | 高频 backtest handler | highfreq 与 RL order execution | 回测所需的 raw close/vwap/volume 等字段 | `$close0 = Cut(FFillNan($close), 480, None)` 的同类表达式 |
| `StaticDataLoader` | `examples/benchmarks/TRA/configs/*` | TRA 旧版复现实验 | 读取已有 `data/feature.pkl` 和 `data/label.pkl`，配置不定义表达式 | `feature: data/feature.pkl` |
| 订单簿表达式 | `examples/orderbook_data/example.py` | orderbook data 单测/示例 | tick/order/transaction 级别的价差、深度、强度、重采样因子 | `p_spread_1 = 2*TResample($ask1-$bid1,'1min','last') / (ask1+bid1)` |

## 通用 label

大多数 benchmark 默认 label 是：

```text
LABEL0 = Ref($close, -2) / Ref($close, -1) - 1
```

含义：用未来两个 close 与未来一个 close 构造下一段收益率。这样在当前 `t` 的 feature 对应未来可交易区间，避免直接把当前 close 到未来 close 的收益混进特征时点。

样例：如果 `t+1` close 为 10.00，`t+2` close 为 10.30，则 `LABEL0 = 10.30 / 10.00 - 1 = 0.03`。

特殊 label：

- `Alpha158vwap` / `Alpha360vwap` 使用 `Ref($vwap, -2) / Ref($vwap, -1) - 1`，当前 examples 中未作为主流 benchmark handler 使用。
- `TCTS` 的 `workflow_config_tcts_Alpha360.yaml` 配置了 3 个 label：未来 1、2、3 段收益，并用 `target_label: 0` 指定主目标。
- A 股突破研究脚本还会生成 `true_breakout`、`false_breakout`、`ambiguous` 等事件标签，这些是事后研究标签，不是通用 `LABEL0`。

## Alpha158

`Alpha158` 是当前 examples 中覆盖最广的因子集。实现路径：

- Handler：`qlib/contrib/data/handler.py` 的 `Alpha158`。
- Loader：`qlib/contrib/data/loader.py` 的 `Alpha158DL.get_feature_config()`。

默认配置生成：

- 9 个 K 线形态因子。
- 4 个当前价格位置因子：`OPEN0`、`HIGH0`、`LOW0`、`VWAP0`。
- 29 类 rolling 因子，每类展开到 `5/10/20/30/60` 五个窗口，共 145 列。
- 总数：`9 + 4 + 29 * 5 = 158`。

### Alpha158 K 线形态因子

| 因子 | 表达式 | 含义 | 样例 |
| --- | --- | --- | --- |
| `KMID` | `($close-$open)/$open` | 实体涨跌幅，衡量 close 相对 open 的方向和幅度 | open=10、close=10.5 时，`KMID=0.05` |
| `KLEN` | `($high-$low)/$open` | 日内振幅相对 open 的比例 | high=11、low=9.5、open=10 时，`KLEN=0.15` |
| `KMID2` | `($close-$open)/($high-$low+1e-12)` | 实体在全日振幅中的占比 | open=10、close=10.5、high-low=1.5 时，`KMID2=0.3333` |
| `KUP` | `($high-Greater($open,$close))/$open` | 上影线相对 open 的比例 | open=10、close=10.5、high=11 时，`KUP=(11-10.5)/10=0.05` |
| `KUP2` | `($high-Greater($open,$close))/($high-$low+1e-12)` | 上影线在全日振幅中的占比 | 上影线 0.5、振幅 1.5 时，`KUP2=0.3333` |
| `KLOW` | `(Less($open,$close)-$low)/$open` | 下影线相对 open 的比例 | open=10、close=10.5、low=9.5 时，`KLOW=(10-9.5)/10=0.05` |
| `KLOW2` | `(Less($open,$close)-$low)/($high-$low+1e-12)` | 下影线在全日振幅中的占比 | 下影线 0.5、振幅 1.5 时，`KLOW2=0.3333` |
| `KSFT` | `(2*$close-$high-$low)/$open` | close 相对日内高低区间中点的偏移 | close=10.5、high=11、low=9.5、open=10 时，`KSFT=0.05` |
| `KSFT2` | `(2*$close-$high-$low)/($high-$low+1e-12)` | close 偏移量在全日振幅中的占比 | 同上时，`KSFT2=0.3333` |

### Alpha158 当前价格位置因子

| 因子 | 表达式 | 含义 | 样例 |
| --- | --- | --- | --- |
| `OPEN0` | `$open/$close` | 当前 open 与 close 的相对位置 | open=10、close=10.5 时，`OPEN0=0.9524` |
| `HIGH0` | `$high/$close` | 当前 high 与 close 的相对位置 | high=11、close=10.5 时，`HIGH0=1.0476` |
| `LOW0` | `$low/$close` | 当前 low 与 close 的相对位置 | low=9.5、close=10.5 时，`LOW0=0.9048` |
| `VWAP0` | `$vwap/$close` | 当前 VWAP 与 close 的相对位置 | vwap=10.2、close=10.5 时，`VWAP0=0.9714` |

### Alpha158 rolling 因子族

下面每一行都会按 `d in {5, 10, 20, 30, 60}` 展开成实际列，例如 `ROC5/ROC10/.../ROC60`。样例统一用 `d=5`。

| 因子族 | 生成列 | 表达式样例 | 含义 | 样例 |
| --- | --- | --- | --- | --- |
| `ROC` | `ROC5` 等 | `Ref($close,5)/$close` | 过去 close 相对当前 close 的比值，反映反向归一化动量 | 5 日前 close=9.8、当前 close=10.5 时，`ROC5=0.9333` |
| `MA` | `MA5` 等 | `Mean($close,5)/$close` | 均线相对当前 close 的位置 | MA5=10.1、close=10.5 时，`MA5=0.9619` |
| `STD` | `STD5` 等 | `Std($close,5)/$close` | 价格波动率相对当前价格的比例 | 5 日 close 标准差 0.3、close=10.5 时，`STD5=0.0286` |
| `BETA` | `BETA5` 等 | `Slope($close,5)/$close` | rolling 线性回归斜率相对价格的比例 | 5 日斜率 0.08、close=10.5 时，`BETA5=0.0076` |
| `RSQR` | `RSQR5` 等 | `Rsquare($close,5)` | rolling 线性趋势的 R 方，越高说明走势越接近直线 | 回归 R 方 0.72 时，`RSQR5=0.72` |
| `RESI` | `RESI5` 等 | `Resi($close,5)/$close` | rolling 线性回归残差相对价格的比例 | 残差 -0.12、close=10.5 时，`RESI5=-0.0114` |
| `MAX` | `MAX5` 等 | `Max($high,5)/$close` | 近期最高价相对当前 close | 5 日最高 high=11.2、close=10.5 时，`MAX5=1.0667` |
| `MIN` | `MIN5` 等 | `Min($low,5)/$close` | 近期最低价相对当前 close | 5 日最低 low=9.4、close=10.5 时，`MIN5=0.8952` |
| `QTLU` | `QTLU5` 等 | `Quantile($close,5,0.8)/$close` | close 的 80% 分位相对当前 close | 5 日 80% 分位为 10.8 时，`QTLU5=1.0286` |
| `QTLD` | `QTLD5` 等 | `Quantile($close,5,0.2)/$close` | close 的 20% 分位相对当前 close | 5 日 20% 分位为 9.9 时，`QTLD5=0.9429` |
| `RANK` | `RANK5` 等 | `Rank($close,5)` | 当前 close 在窗口内的分位位置 | 5 日里当前 close 排在第 4/5 高时，约为 `0.8` |
| `RSV` | `RSV5` 等 | `($close-Min($low,5))/(Max($high,5)-Min($low,5)+1e-12)` | 当前 close 在近期高低区间内的位置 | close=10.5、低=9.4、高=11.2 时，`RSV5=0.6111` |
| `IMAX` | `IMAX5` 等 | `IdxMax($high,5)/5` | 窗口内最高价距离当前的归一化位置 | 最高价出现在 2 个 bar 前时，`IMAX5=0.4` |
| `IMIN` | `IMIN5` 等 | `IdxMin($low,5)/5` | 窗口内最低价距离当前的归一化位置 | 最低价出现在 4 个 bar 前时，`IMIN5=0.8` |
| `IMXD` | `IMXD5` 等 | `(IdxMax($high,5)-IdxMin($low,5))/5` | 最高点与最低点先后关系，辅助判断趋势方向 | 最高点位置 1、最低点位置 4 时，`IMXD5=-0.6` |
| `CORR` | `CORR5` 等 | `Corr($close,Log($volume+1),5)` | 价格与成交量对数的相关性 | 相关系数为 0.45 时，`CORR5=0.45` |
| `CORD` | `CORD5` 等 | `Corr($close/Ref($close,1),Log($volume/Ref($volume,1)+1),5)` | 价格涨跌比与成交量变化比的相关性 | 相关系数为 -0.2 时，`CORD5=-0.2` |
| `CNTP` | `CNTP5` 等 | `Mean($close>Ref($close,1),5)` | 窗口内上涨天数占比 | 5 天里 3 天上涨时，`CNTP5=0.6` |
| `CNTN` | `CNTN5` 等 | `Mean($close<Ref($close,1),5)` | 窗口内下跌天数占比 | 5 天里 2 天下跌时，`CNTN5=0.4` |
| `CNTD` | `CNTD5` 等 | `Mean(up,5)-Mean(down,5)` | 上涨占比与下跌占比之差 | 上涨占比 0.6、下跌占比 0.4 时，`CNTD5=0.2` |
| `SUMP` | `SUMP5` 等 | `Sum(Greater($close-Ref($close,1),0),5)/Sum(Abs($close-Ref($close,1)),5)` | 上涨幅度占总绝对波动的比例，类似 RSI 的上涨份额 | 上涨幅度合计 1.2、绝对波动合计 2.0 时，`SUMP5=0.6` |
| `SUMN` | `SUMN5` 等 | `Sum(Greater(Ref($close,1)-$close,0),5)/Sum(Abs($close-Ref($close,1)),5)` | 下跌幅度占总绝对波动的比例 | 下跌幅度合计 0.8、绝对波动合计 2.0 时，`SUMN5=0.4` |
| `SUMD` | `SUMD5` 等 | `(up_sum-down_sum)/abs_change_sum` | 上涨与下跌幅度差的归一化值 | 上涨 1.2、下跌 0.8、总波动 2.0 时，`SUMD5=0.2` |
| `VMA` | `VMA5` 等 | `Mean($volume,5)/($volume+1e-12)` | 均量相对当前成交量 | MA volume=1800、当前 volume=2000 时，`VMA5=0.9` |
| `VSTD` | `VSTD5` 等 | `Std($volume,5)/($volume+1e-12)` | 成交量波动率相对当前成交量 | volume 标准差 300、当前 2000 时，`VSTD5=0.15` |
| `WVMA` | `WVMA5` 等 | `Std(Abs(ret)*$volume,5)/Mean(Abs(ret)*$volume,5)` | 成交量加权价格变化的相对波动 | 加权变化均值 20、标准差 8 时，`WVMA5=0.4` |
| `VSUMP` | `VSUMP5` 等 | `Sum(Greater($volume-Ref($volume,1),0),5)/Sum(Abs($volume-Ref($volume,1)),5)` | 成交量上升幅度占总量变动的比例 | 上升量 600、总变动 1000 时，`VSUMP5=0.6` |
| `VSUMN` | `VSUMN5` 等 | `Sum(Greater(Ref($volume,1)-$volume,0),5)/Sum(Abs($volume-Ref($volume,1)),5)` | 成交量下降幅度占总量变动的比例 | 下降量 400、总变动 1000 时，`VSUMN5=0.4` |
| `VSUMD` | `VSUMD5` 等 | `(volume_up_sum-volume_down_sum)/volume_abs_change_sum` | 成交量上升与下降幅度差 | 上升 600、下降 400、总变动 1000 时，`VSUMD5=0.2` |

## Alpha360

`Alpha360` 是序列型深度模型常用的数据表示。实现路径：

- Handler：`qlib/contrib/data/handler.py` 的 `Alpha360`。
- Loader：`qlib/contrib/data/loader.py` 的 `Alpha360DL.get_feature_config()`。

它不手工构造技术指标，而是把最近 60 个 bar 的原始量价序列展开为 360 列：

| 因子族 | 生成列 | 表达式 | 含义 | 样例 |
| --- | --- | --- | --- | --- |
| `CLOSEi` | `CLOSE59` 到 `CLOSE0` | `Ref($close,i)/$close`，`i=0..59` | 过去 close 序列除以当前 close，`CLOSE0` 恒为 1 | 当前 close=10，5 日前 close=9.5，则 `CLOSE5=0.95` |
| `OPENi` | `OPEN59` 到 `OPEN0` | `Ref($open,i)/$close` | 过去 open 相对当前 close | 当前 close=10，昨日 open=9.8，则 `OPEN1=0.98` |
| `HIGHi` | `HIGH59` 到 `HIGH0` | `Ref($high,i)/$close` | 过去 high 相对当前 close | 当前 close=10，昨日 high=10.4，则 `HIGH1=1.04` |
| `LOWi` | `LOW59` 到 `LOW0` | `Ref($low,i)/$close` | 过去 low 相对当前 close | 当前 close=10，昨日 low=9.6，则 `LOW1=0.96` |
| `VWAPi` | `VWAP59` 到 `VWAP0` | `Ref($vwap,i)/$close` | 过去 VWAP 相对当前 close | 当前 close=10，昨日 vwap=10.1，则 `VWAP1=1.01` |
| `VOLUMEi` | `VOLUME59` 到 `VOLUME0` | `Ref($volume,i)/($volume+1e-12)` | 过去 volume 相对当前 volume，`VOLUME0` 约为 1 | 当前 volume=2000，5 日前 volume=1500，则 `VOLUME5=0.75` |

适用场景：

- Alpha360 更像“最近 60 天原始状态张量”，适合 RNN/Transformer/TCN 一类模型学习时序模式。
- Alpha158 更像“人工压缩后的技术指标表”，适合树模型、线性模型和一部分 tabular 模型。

## LightGBM configurable 13 因子

`examples/benchmarks/LightGBM/workflow_config_lightgbm_configurable_dataset.yaml` 直接配置 `DataHandlerLP` 和 `QlibDataLoader`，手工选择 13 个表达式。注意该配置中第一列名为 `RESI5`，但实际表达式是 `Resi($close, 15)/$close`，解释时应以表达式为准。

| 列名 | 表达式 | 含义 | 样例 |
| --- | --- | --- | --- |
| `RESI5` | `Resi($close,15)/$close` | 15 日线性回归残差相对当前 close | 残差 0.1、close=10 时，值为 `0.01` |
| `WVMA5` | `Std(Abs($close/Ref($close,1)-1)*$volume,5) / Mean(...,5)` | 成交量加权收益波动 | 加权收益均值 100、标准差 40 时，值为 `0.4` |
| `RSQR5` | `Rsquare($close,5)` | 5 日线性趋势拟合度 | R 方 0.8 时，值为 `0.8` |
| `KLEN` | `($high-$low)/$open` | K 线振幅 | high=11、low=9、open=10 时，值为 `0.2` |
| `RSQR10` | `Rsquare($close,10)` | 10 日线性趋势拟合度 | R 方 0.5 时，值为 `0.5` |
| `CORR5` | `Corr($close,Log($volume+1),5)` | 5 日价量相关 | 相关系数 0.3 时，值为 `0.3` |
| `CORD5` | `Corr($close/Ref($close,1),Log($volume/Ref($volume,1)+1),5)` | 5 日收益比与量变比相关 | 相关系数 -0.1 时，值为 `-0.1` |
| `CORR10` | `Corr($close,Log($volume+1),10)` | 10 日价量相关 | 相关系数 0.2 时，值为 `0.2` |
| `RSQR20` | `Rsquare($close,20)` | 20 日线性趋势拟合度 | R 方 0.7 时，值为 `0.7` |
| `CORD60` | `Corr($close/Ref($close,1),Log($volume/Ref($volume,1)+1),60)` | 60 日收益比与量变比相关 | 相关系数 0.05 时，值为 `0.05` |
| `CORD10` | `Corr($close/Ref($close,1),Log($volume/Ref($volume,1)+1),10)` | 10 日收益比与量变比相关 | 相关系数 0.12 时，值为 `0.12` |
| `CORR20` | `Corr($close,Log($volume+1),20)` | 20 日价量相关 | 相关系数 0.4 时，值为 `0.4` |
| `KLOW` | `(Less($open,$close)-$low)/$open` | 下影线相对 open 的比例 | open=10、close=10.5、low=9.7 时，值为 `0.03` |

## 多频与 15 分钟因子

### Alpha158 多频示例

`workflow_config_lightgbm_Alpha158_multi_freq.yaml` 仍使用 `Alpha158`，但将：

- `label` 频率设置为日频。
- `feature` 频率设置为 1min。
- `Resample1minProcessor(hour=14, minute=56)` 把 1min 数据取样到日频索引。

样例：`OPEN0 = $open/$close` 的公式不变，但 `$open` 和 `$close` 来自每日 14:56 的 1min bar，而不是日线 bar。

### Avg15minHandler

`workflow_config_lightgbm_multi_freq.yaml` 使用 `Avg15minHandler`，生成两组 feature：

| 组 | 列 | 表达式 | 含义 | 样例 |
| --- | --- | --- | --- | --- |
| `feature_day` | `close0/open0/low0/high0/volume0/vwap0` | `$close`、`$open` 等 | 当日日频 OHLCV/VWAP | close0 直接等于当天日频 close |
| `feature_15min` | 每个字段 16 个桶，共 96 列 | `Ref(Mean($close,15),15)` 到 `Mean($close,15)` 的同类表达式 | 用 1min 数据构造 15 分钟均值桶，并重采样到日频 | `close16 = Mean($close,15)` 表示当前 15 根 1min close 的均值 |
| `label` | `LABEL0` | `Ref($close,-2)/Ref($close,-1)-1` | 日频未来收益 | t+1 close=10、t+2 close=10.2 时为 `0.02` |

当前实现里 `feature_15min` 的列名由 `multi_freq_handler.py` 生成，实际列序以 `loader_config()` 返回的 `(fields, names)` 为准。

## StudyAlpha158 规则趋势因子

`examples/study_yaml_workflow/mylib/handler.py` 定义 `StudyAlpha158`，它继承 Alpha158 后追加一列：

| 因子 | 表达式 | 含义 | 样例 |
| --- | --- | --- | --- |
| `MA_TREND_5_20` | `Mean($close,5) - Mean($close,20)` | 5 日均线与 20 日均线的绝对差，作为简单趋势规则信号 | MA5=10.8、MA20=10.2 时，值为 `0.6` |

`workflow_rule_factor.yaml` 中的 `FactorColumnModel` 直接把 `MA_TREND_5_20` 当作预测分数，不训练机器学习模型。

## A 股突破规则因子

`examples/a_share_breakout/mylib/handler.py` 定义 `AShareBreakoutRuleHandler`。它继承 `Alpha158` 只是为了复用 DataHandler 框架，实际 `get_feature_config()` 完全返回突破规则因子，不返回 Alpha158 的 158 列。

窗口参数当前主要为 `60` 或 `120`，下表用 `N` 表示窗口。

| 因子 | 表达式 / 来源 | 含义 | 样例 |
| --- | --- | --- | --- |
| `CLOSE` | `$close` | 当前收盘价 | close=10.5 时，值为 `10.5` |
| `BREAKOUT_LEVEL_ND` | `Ref(Max($close,N),1)` | 不含当天的过去 N 日最高收盘价 | N=60，过去 60 日最高 close=10.0 时，值为 `10.0` |
| `ATR_14` | `Mean(TrueRange,14)` | 14 日平均真实波幅 | 14 日 TR 均值为 0.45 时，值为 `0.45` |
| `ATR_PCT` | `ATR_14/($close+1e-12)` | ATR 相对当前 close 的比例 | ATR=0.45、close=10.5 时，值为 `0.0429` |
| `ATR_NOISE_RANK_252` | `Rank(ATR_PCT,252)` | ATR_PCT 在过去 252 日中的分位 | 当前波动处在 80% 分位时，值约 `0.8` |
| `BREAKOUT_STRENGTH_ND` | `($close-BREAKOUT_LEVEL_ND)/(ATR_14+1e-12)` | 突破幅度折算成 ATR 倍数 | close=10.5、level=10.0、ATR=0.5 时，值为 `1.0` |
| `CANDIDATE_ND` | `close > level` 且 `close >= level + 0.5*ATR` | 是否满足突破候选条件 | close=10.5、level=10、ATR=0.5 时，值为 `1` |
| `MA20_GT_MA60` | `If(Gt(MA20,MA60),1,0)` | 中期均线是否强于长期均线 | MA20=10.6、MA60=10.1 时，值为 `1` |
| `MA20_SLOPE_20` | `(MA20-Ref(MA20,20))/(Abs(Ref(MA20,20))+1e-12)` | 20 日均线的 20 日变化率 | MA20 当前 10.6、20 日前 10.0 时，值为 `0.06` |
| `REL_STRENGTH_20D` | `stock_return_20d - benchmark_return_20d` | 个股 20 日收益相对基准 20 日收益 | 个股 8%、基准 3% 时，值为 `0.05` |
| `VOL_RATIO_20` | `$volume/(Mean(Ref($volume,1),20)+1e-12)` | 当日量相对过去 20 日均量 | volume=3000、过去均量=2000 时，值为 `1.5` |
| `VOL_RATIO_3D` | `Mean($volume,3)/(Mean(Ref($volume,3),20)+1e-12)` | 近 3 日均量相对更早 20 日均量 | 近 3 日均量 2500、前段均量 2000 时，值为 `1.25` |
| `VOLUME_SPIKE_NO_PERSISTENCE` | `(VOL_RATIO_20-VOL_RATIO_3D)/VOL_RATIO_20` 截断到 `[0,1]` | 当天放量但近 3 日不持续的程度 | 1.5 与 1.25 时，值为 `0.1667` |
| `AMOUNT_RANK_252` | `Rank($amount,252)` | 成交额历史分位 | 当日成交额处于过去一年 90% 分位时，值约 `0.9` |
| `BB_WIDTH_20` | `4*Std($close,20)/(Mean($close,20)+1e-12)` | 20 日布林带宽度 | std=0.25、MA20=10 时，值为 `0.1` |
| `BB_WIDTH_RANK_252` | `Rank(BB_WIDTH_20,252)` | 布林带宽度历史分位 | 布林带宽处于 70% 分位时，值约 `0.7` |
| `LIMIT_DEPENDENCY_SCORE` | `max(1d_return,0)/涨停阈值` 截断到 `[0,1]` | 当日上涨对涨停约束的依赖程度 | 1 日涨幅 8%、涨停阈值 10% 时，值为 `0.8` |
| `ONE_WORD_LIMIT_LIKE` | 高低开收几乎一致且涨幅接近涨停 | 一字板或近似一字板标记 | OHLC 几乎相等且涨幅 9.5% 时，值为 `1` |
| `BARELY_BREAKOUT_SCORE_ND` | `1-BREAKOUT_STRENGTH_ND` 截断到 `[0,1]` | 刚刚越过突破位、突破不充分的程度 | strength=0.2 时，值为 `0.8` |
| `FAKE_PROB_DAILY_T_RAW_ND` | `0.25*量能突刺 + 0.20*涨停依赖 + 0.15*ATR噪声分位 + 0.10*刚好突破` | 日线 T 收盘可见的伪突破原始评分 | 四项分别 0.2、0.8、0.7、0.6 时，值为 `0.375` |

`examples/a_share_breakout/daily_features.py` 还会生成研究用列：

- `next_open_return_research`：`open[t+1]/close[t]-1`，T+1 open 才可见。
- `next_open_reversal_score_research`：T+1 开盘回吐程度。
- `fake_prob_daily_research_Nd`：在 T 收盘评分基础上加入 T+1 开盘回吐，只能用于事后归因。

这些列不能作为 T 日收盘可交易信号输入。

## 高频因子

### examples/highfreq 的 HighFreqHandler

`examples/highfreq/workflow.py` 使用 `examples/highfreq/highfreq_handler.py` 中的本地 handler，并注册了 `DayLast`、`FFillNan`、`BFillNan`、`Select`、`IsNull`、`Cut` 等自定义算子。

| 因子 | 表达式模式 | 含义 | 样例 |
| --- | --- | --- | --- |
| `$open/$high/$low/$close/$vwap` | 当前分钟价格除以前一交易日收盘基准，并 `Cut(...,240,None)` 去掉首日上下文 | 当前日分钟价格标准化 | 当前 open=10.2，前日尾盘 close=10.0 时，`$open=1.02` |
| `$open_1/$high_1/$low_1/$close_1/$vwap_1` | `Ref(price,240)` 的同类表达式 | 上一交易日同分钟价格标准化 | 昨日同分钟 close=9.9，昨日尾盘 close=10.0 时，`$close_1=0.99` |
| `$volume` | 当前 volume 除以前 30 个交易日分钟均量基准 | 当前分钟成交量相对历史水平 | 当前 volume=5000，基准=2500 时，值为 `2.0` |
| `$volume_1` | `Ref($volume,240)` 的同类表达式 | 上一交易日同分钟成交量相对历史水平 | 昨日同分钟 volume=3000，基准=2500 时，值为 `1.2` |

### HighFreqGeneralHandler

`examples/rl_order_execution/scripts/pickle_data_config.yml` 使用 `qlib.contrib.data.highfreq_handler.HighFreqGeneralHandler`，当前配置：

- `freq: 5min`
- `day_length: 240`
- `columns: ["$open", "$high", "$low", "$close"]`

生成列模式：

| 因子 | 表达式模式 | 含义 | 样例 |
| --- | --- | --- | --- |
| `$open/$high/$low/$close` | 当前字段相对前一日收盘基准归一化 | 当前 5min 价格状态 | close=10.1，基准 close=10.0 时，`$close=1.01` |
| `$open_1/$high_1/$low_1/$close_1` | 上一交易日同位置字段相对基准归一化 | 昨日同时间价格状态 | 昨日同 5min close=9.8，基准 close=10.0 时，`$close_1=0.98` |
| `$volume` | 当前 volume 相对 30 日分钟均量 | 当前流动性强弱 | 当前 volume 是历史基准两倍时，值为 `2.0` |
| `$volume_1` | 上一交易日同位置 volume 相对历史基准 | 昨日同时间流动性 | 昨日同位置是基准 0.8 倍时，值为 `0.8` |

`HighFreqGeneralBacktestHandler` 的当前 backtest 配置只取 `columns: ["$close", "$volume"]`，因此主要生成 `$close0` 和 `$volume0`，供订单执行回测使用。

## TFT 手工选列

`examples/benchmarks/TFT/tft.py` 内部从数据集中手工挑选特征列。当前 `workflow_config_tft_Alpha158.yaml` 使用 Alpha158，代码也预留了 Alpha360 的列选择。

Alpha158 手工列样例：

| 列 | 来源 | 含义 | 样例 |
| --- | --- | --- | --- |
| `RESI5` | Alpha158 | 5 日回归残差比例 | 残差 0.1、close=10 时，值为 `0.01` |
| `WVMA5` | Alpha158 | 5 日成交量加权价格波动 | 加权变化 std/mean=0.4 时，值为 `0.4` |
| `KLEN` | Alpha158 | K 线振幅 | high=11、low=9、open=10 时，值为 `0.2` |
| `ROC60` | Alpha158 | 60 日前 close 相对当前 close | 60 日前 8、当前 10 时，值为 `0.8` |

Alpha360 预留列样例：

| 列 | 来源 | 含义 | 样例 |
| --- | --- | --- | --- |
| `HIGH0` | Alpha360 | 当前 high / 当前 close | high=10.4、close=10 时，值为 `1.04` |
| `CLOSE1` | Alpha360 | 昨日 close / 当前 close | 昨日 9.8、当前 10 时，值为 `0.98` |
| `VOLUME8` | Alpha360 | 8 日前 volume / 当前 volume | 8 日前 1200、当前 2000 时，值为 `0.6` |

## 订单簿和逐笔表达式

`examples/orderbook_data/example.py` 不是标准 `DatasetH` workflow，而是直接调用 `D.features(...)` 读取 tick、transaction、order 级别表达式。主要因子族如下。

| 因子族 | 表达式样例 | 含义 | 样例 |
| --- | --- | --- | --- |
| 原始盘口字段 | `$ask1`、`$ask2`、`$bid1`、`$bid2` | 买卖盘档位价格 | ask1=10.02、bid1=10.00 |
| 分钟重采样 | `TResample($ask1,'1min','last')` | tick 级字段重采样到 1min | 取每分钟最后一个 ask1 |
| 深度占比 | `TResample($asize1,'1min','mean') / total_volume` | 某档挂单量占 10 档总量比例 | asize1=100、总量=1000 时，值为 `0.1` |
| 价差 | `2*TResample($ask1-$bid1,'1min','last')/(ask1+bid1)` | 标准化 bid-ask spread | ask1=10.02、bid1=10.00 时，约 `0.002` |
| 档位中价 | `2*TResample(($ask1+$bid1)/2,'1min','last')/(ask1+bid1)` | 档位中价相对一档买卖价和 | ask1=10.02、bid1=10.00 时，约 `1.0` |
| 档位差分 | `2*TResample(Abs($ask2-$ask1),'1min','last')/(ask1+bid1)` | 相邻档位价差形状 | ask2-ask1=0.03、分母约 20.02 时，约 `0.003` |
| 累积价差 | `2*Sub(sum_ask,sum_bid)/(ask1+bid1)` | 10 档卖价合计与买价合计的标准化差 | 卖价合计高于买价合计 0.5 时，约 `0.05` |
| 订单强度 | `Rolling(Eq($function_code,ord('B')) & Eq($order_kind,ord('0')),'3s','sum') / Rolling($function_code,'3s','count')` | 某类订单在短窗口内的出现比例 | 3 秒内 10 笔中 3 笔为该类时，值为 `0.3` |
| 相对强度 | `TResample(Gt(short_intensity,long_intensity),'1min','mean')` | 短窗口订单强度是否高于长窗口 | 1min 内一半时间满足时，值为 `0.5` |
| 强度变化率 | `TResample(Div(Sub(TResample(intensity,'3s','last'),Ref(...,1)),3),'1min','mean')` | 订单强度的短周期变化速度 | 强度从 0.2 到 0.35，3 秒变化率为 `0.05` |
| 滞后价格变化 | `TResample(Ref(TResample($ask1+$bid1,'1s','ffill'),-5)/(ask1+bid1)-1,'1min','mean')` | 未来/滞后盘口价和变化示例 | 5 秒后价和从 20.0 到 20.1 时，约 `0.005` |

## 如何在本地展开因子清单

可以用下面的代码查看 Alpha158/Alpha360 的完整表达式与列名：

```python
from qlib.contrib.data.loader import Alpha158DL, Alpha360DL

for loader in (Alpha158DL, Alpha360DL):
    fields, names = loader.get_feature_config()
    print(loader.__name__, len(names))
    for name, field in zip(names[:10], fields[:10]):
        print(name, field)
```

查看某个自定义 handler：

```python
from examples.a_share_breakout.mylib.handler import build_rule_feature_config

fields, names = build_rule_feature_config(breakout_window=60)
for name, field in zip(names, fields):
    print(name, field)
```

如果新增 examples 配置，优先判断它属于哪一类：

1. `handler.class: Alpha158` 或 `Alpha360`：因子来自官方 loader。
2. `handler.class` 是自定义类：查看该类的 `get_feature_config()`。
3. `DataHandlerLP + QlibDataLoader`：直接查看 YAML 里的 `data_loader.kwargs.config.feature`。
4. `StaticDataLoader`：查看被加载的 pkl/csv 文件来源；配置本身通常无法还原表达式。
