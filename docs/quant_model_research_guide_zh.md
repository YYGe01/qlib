# 量化模型与策略研究路线报告

> 面向对象：刚开始接触量化研究、Qlib、机器学习选股/交易策略的新手。  
> 更新时间：2026-04-24。  
> 范围：基于当前仓库中的 Qlib 模型、官方 benchmark、近年公开论文和行业研究趋势。  
> 重要说明：本文是研究路线和技术学习材料，不构成投资建议。任何策略都必须经过严格的样本外回测、交易成本建模、容量评估和实盘小资金验证。

## 一句话结论

如果你的目标是“直接研究最值得投入的方向”，不要一上来追最新大模型。更稳健的路线是：

1. 先用 `LightGBM / XGBoost / CatBoost + Alpha158 / Alpha360` 复现稳定基线。
2. 再研究 `DoubleEnsemble`，因为它直接针对金融数据的低信噪比、非平稳和特征过多问题。
3. 然后进入 `滚动训练 / DDG-DA / AdaRNN / TRA` 这类市场状态变化建模。
4. 如果你能拿到可靠行业、概念、供应链、持仓、新闻、公告数据，再研究 `HIST / IGMTF / GATs` 和非结构化数据。
5. LLM、Time Series Foundation Model、Agent 自动研究现在很有潜力，但对新手来说应该先作为“辅助研究工具”和“特征生成工具”，不要直接当成可交易策略核心。

## 0. 新手先理解 Qlib 策略链路

Qlib 的典型量化研究流程不是“模型预测价格就赚钱”，而是：

```text
原始数据
  -> 特征工程/数据集
  -> 标签定义
  -> 预测模型
  -> 每只股票每天的预测分数
  -> 组合构建策略
  -> 回测与分析
  -> 滚动更新/线上服务
```

当前仓库的 benchmark 主要是 `alpha seeking`，也就是让模型每天给股票打分，期望分数高的股票未来收益更好。Qlib benchmark 明确用两类方式评价 alpha：预测分数和未来收益的相关性，以及基于预测分数组合后的真实回测表现。见 [examples/benchmarks/README.md](../examples/benchmarks/README.md)。

你需要区分三个概念：

| 概念 | 新手解释 | Qlib 中常见位置 |
|---|---|---|
| 因子/特征 | 模型看到的输入，如价格、成交量、动量、均线、波动率、估值、新闻情绪 | `Alpha158`、`Alpha360`、自定义 handler |
| 标签 | 模型要预测的目标，例如未来 1 天或 2 天收益 | `qlib/contrib/data/handler.py` |
| 策略 | 根据预测分数决定买哪些、卖哪些、仓位多少 | `TopkDropoutStrategy`、优化器、RL 执行策略 |

Qlib 默认的 `Alpha158` 和 `Alpha360` 标签是：

```text
Ref($close, -2) / Ref($close, -1) - 1
```

它表示从 T+1 到 T+2 的收益，而不是 T 到 T+1 的收益。Qlib 文档解释，这是为了贴合中国股票在 T 日收盘后得到信号、T+1 才能买入、T+2 才能卖出的交易约束。见 [docs/component/data.rst](component/data.rst) 和 [qlib/contrib/data/handler.py](../qlib/contrib/data/handler.py)。

## 1. 当前项目中模型怎么分类

当前仓库模型主要分布在：

- [qlib/contrib/model](../qlib/contrib/model)
- [examples/benchmarks](../examples/benchmarks)
- [examples/benchmarks_dynamic](../examples/benchmarks_dynamic)
- [examples/rl_order_execution](../examples/rl_order_execution)
- [qlib/model/riskmodel](../qlib/model/riskmodel)
- [qlib/contrib/strategy](../qlib/contrib/strategy)

可以按研究任务分成六类。

### 1.1 表格/树模型

代表模型：

- `Linear`
- `LightGBM`
- `XGBoost`
- `CatBoost`
- `DoubleEnsemble`
- `HFLGBModel` 高频树模型

适合任务：

- 多因子选股
- 每日截面排序
- 先搭建强基线
- 因子有效性验证

优点：

- 非常稳健，训练快，可解释性比深度模型强。
- 对中小数据、表格特征、人工因子非常友好。
- 容易做特征重要性、分组回测、因子删除实验。

缺点：

- 对复杂时间序列结构、跨股票关系的表达能力有限。
- 如果因子质量差，树模型也救不了。
- 容易在数据泄漏、过度调参、幸存者偏差下产生虚假收益。

结论：

这是最值得新手优先研究的模型族。不是因为它最新，而是因为它最容易验证、复现、迭代，并且在金融表格数据上长期有竞争力。

### 1.2 普通深度时序模型

代表模型：

- `MLP`
- `LSTM`
- `GRU`
- `ALSTM`
- `SFM`
- `TCN`
- `Transformer`
- `Localformer`
- `TFT`
- `TabNet`

适合任务：

- 直接从连续时间窗口中学习模式。
- 使用 `Alpha360` 这类更接近原始价格量数据的输入。
- 研究短期动量、反转、波动聚集、时间依赖。

优点：

- 可以学习非线性时间结构。
- 对 `Alpha360` 这类时间维度强的数据更自然。
- RNN、TCN、Attention 都是经得起时间检验的序列建模基础。

缺点：

- 数据要求更高，调参更难。
- 金融信号低噪声，很容易过拟合。
- 深度模型表现好不等于可交易，必须看交易成本、换手、回撤和跨市场稳定性。

结论：

LSTM、GRU、TCN、ALSTM 值得作为“时序模型基础课”。普通 Transformer 在 Qlib benchmark 里并不突出，研究价值不在于直接复用 vanilla Transformer，而在于理解后续 PatchTST、iTransformer、Localformer、TFT、时间序列基础模型为什么要改造它。

### 1.3 市场状态、分布漂移、动态适应模型

代表模型或模块：

- `Rolling Retraining`
- `DDG-DA`
- `AdaRNN`
- `TRA`
- `TCTS`
- `ADD`

适合任务：

- 市场风格切换。
- 牛熊转换。
- 行业轮动。
- 因子衰减。
- 训练集和测试集分布不一致。

优点：

- 金融市场最核心的问题不是模型容量不足，而是非平稳。
- 这类模型直接针对“过去有效，未来失效”的问题。
- 研究价值很高，能帮助你理解策略为什么会失效。

缺点：

- 实验设计难度高。
- 需要严格按时间切分，不能随机切分。
- 验证方式要用 walk-forward、rolling、不同市场和不同年份。

结论：

这是我认为最有研究价值的方向之一。比单纯换一个更复杂神经网络更重要。

### 1.4 跨股票关系、图模型、概念模型

代表模型：

- `GATs`
- `HIST`
- `IGMTF`
- `KRNN`
- `Sandwich`

适合任务：

- 行业联动。
- 概念板块扩散。
- 供应链、上下游关系。
- 指数成分股联动。
- 机构持仓重合。

优点：

- 股票不是独立样本，图模型能显式建模关系。
- 对 A 股这种行业和主题联动明显的市场很有吸引力。
- `HIST` 这种模型把显式概念和隐含概念一起建模，研究价值较高。

缺点：

- 关系数据很难干净获得。
- 图关系容易引入未来信息，例如后来才知道的概念关系、指数成分变更。
- 模型解释和维护成本高。

结论：

如果只有价格量数据，优先级低于树模型和滚动训练。如果你能拿到点对点的行业、概念、供应链、新闻共现、基金持仓关系，它会变成高潜力方向。

### 1.5 强化学习与订单执行

代表方法：

- `TWAP`
- `PPO`
- `OPDS`
- Qlib RL order execution

适合任务：

- 拆单。
- 减少冲击成本。
- 高频或分钟级执行。
- 有稳定 alpha 后优化交易执行。

优点：

- 能把交易过程建模为连续决策。
- 对大资金、换手高、流动性约束强的策略更有价值。

缺点：

- 不适合新手一开始用来“找 alpha”。
- 环境仿真很难，历史回放不等于真实市场互动。
- 奖励函数稍微设计不好就会学到错误行为。

结论：

先不要把 RL 当作选股 alpha 核心。等你有稳定预测信号和组合逻辑后，再研究 RL 执行和组合调仓。

### 1.6 风险模型与组合优化

代表模块：

- `qlib/model/riskmodel/shrink.py`
- `qlib/model/riskmodel/poet.py`
- `qlib/model/riskmodel/structured.py`
- `EnhancedIndexingOptimizer`

适合任务：

- 控制行业暴露。
- 控制风格暴露。
- 降低波动和回撤。
- 指数增强。

优点：

- 很多策略不是预测不行，而是组合构建和风控不行。
- 风险模型能把“高分股票列表”变成更可控的组合。

缺点：

- 对新手不如先理解 alpha 模型直观。
- 需要理解协方差、约束优化、风险暴露。

结论：

当你的预测信号有稳定 Rank IC 后，下一步必须研究组合优化。只会训练模型，不会构建组合，策略很难走向实盘。

## 2. 哪些模型经得起时间检验

这里的“经得起时间检验”不是说永远赚钱，而是说它们在多领域、多数据集、多年研究中仍然是可靠基线或重要思想。

### 2.1 第一梯队：必须研究

| 模型/方向 | 为什么经得起时间检验 | 你应该怎么研究 |
|---|---|---|
| `Linear` | 简单、可解释，是判断复杂模型是否真的有价值的基线 | 每个新特征都先用线性或分组 IC 检验 |
| `LightGBM` | GBDT 在表格数据长期强势，LightGBM 高效，适合大规模因子 | 先复现 Alpha158/Alpha360，再做因子增删 |
| `XGBoost` | 经典 GBDT 系统，工业和竞赛里长期强基线 | 用来和 LightGBM 交叉验证结论 |
| `CatBoost` | 有序 boosting 和类别特征处理思想重要，防目标泄漏 | 有行业、概念、类别特征时重点研究 |
| `DoubleEnsemble` | 针对金融低信噪比、非平稳、因子过多，思想非常贴合量化 | 研究样本重加权和特征选择 |
| `LSTM / GRU` | 时序建模基本功，很多新模型仍以它们为 backbone | 作为理解深度时序模型的基础 |
| `TCN` | 卷积时序模型简单、训练稳定，长依赖效率好 | 和 RNN 对比，研究窗口长度和换手 |
| 滚动训练 | 市场非平稳下最朴素也最必要的工程方法 | 固定训练窗、扩展训练窗、滚动验证都要做 |

外部证据：

- LightGBM 论文提出 GOSS 和 EFB，并报告训练速度大幅提升，同时保持相近精度。[NeurIPS 2017](https://papers.nips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html)
- XGBoost 论文强调可扩展树 boosting 系统，并在机器学习挑战中广泛使用。[KDD 2016](https://www.kdd.org/kdd2016/subtopic/view/xgboost-a-scalable-tree-boosting-system/670/)
- CatBoost 论文重点解决 ordered boosting 和类别特征中的目标泄漏问题。[NeurIPS 2018](https://papers.nips.cc/paper_files/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html)
- DoubleEnsemble 直接针对金融低信噪比、非平稳和因子过多问题，提出样本重加权和特征选择。[arXiv:2010.01265](https://arxiv.org/abs/2010.01265)

### 2.2 第二梯队：研究价值高，但要有实验能力

| 模型/方向 | 研究价值 | 主要风险 |
|---|---|---|
| `TRA` | 多市场模式、多专家、路由机制，非常贴合风格切换 | 训练复杂，结果依赖数据切分 |
| `AdaRNN / DDG-DA` | 分布漂移和概念漂移是金融核心问题 | 很难证明泛化，容易过拟合验证集 |
| `HIST / IGMTF / GATs` | 显式建模股票关系和概念共享信息 | 关系数据质量和时点一致性很难 |
| `TCTS` | 多任务和预测 horizon 设计有研究意义 | 实现复杂，新手不宜优先 |
| `TFT` | 可解释、多变量、多 horizon 思想重要 | 当前 Qlib TFT 依赖较旧 TensorFlow，工程维护成本高 |
| `Localformer / Transformer 变体` | 时间序列 Transformer 仍是主流研究方向 | vanilla Transformer 在金融中未必稳健 |

外部证据：

- `TRA` 论文认为股票市场存在多种交易模式，提出 Temporal Routing Adaptor 将样本路由到不同预测器。[arXiv:2106.12950](https://arxiv.org/abs/2106.12950)
- `HIST` 论文认为股票间共享信息很重要，并结合预定义概念与隐藏概念。[arXiv:2110.13716](https://arxiv.org/abs/2110.13716)
- `DDG-DA` 论文直接处理可预测概念漂移，通过预测未来数据分布来生成训练样本。[arXiv:2201.04038](https://arxiv.org/abs/2201.04038)

### 2.3 第三梯队：可以了解，但不建议新手先投入

| 模型/方向 | 原因 |
|---|---|
| 直接用 vanilla Transformer 选股 | Qlib benchmark 中普通 Transformer 表现不稳定，且时间序列 Transformer 已经进入 patch、inverted、foundation model 阶段 |
| `TabNet` | 表格深度模型有研究价值，但在 Qlib benchmark 中并不突出 |
| `KRNN / Sandwich` | 当前 benchmark 表现较弱，可作为参考但不宜先研究 |
| 直接用 RL 生成买卖点 | 环境、奖励、滑点、成交建模非常难，新手容易得到虚假结论 |
| 直接让 LLM 预测涨跌 | 容易泄漏、不可控、难复现，应该先做严格事件时点对齐和消融实验 |

## 3. Qlib benchmark 给我们的启发

Qlib benchmark 对 CSI300 的结果显示：

- 在 `Alpha158` 上，`DoubleEnsemble`、`LightGBM`、`MLP`、`TRA`、`XGBoost` 等表现较强。
- 在 `Alpha360` 上，`HIST`、`IGMTF`、`TRA`、`TCTS`、`GATs`、`AdaRNN`、`GRU` 等深度和关系模型表现更强。
- `Alpha158` 是人工设计特征，更像传统多因子表格数据。
- `Alpha360` 更接近原始价格量时间序列，时间维度关系更强。

这说明一个重要事实：

不同数据形态适合不同模型。不是“哪个模型最强”，而是“你的数据结构是什么”。如果你用人工因子，树模型很强。如果你用原始价格量窗口，RNN、TCN、图模型、模式路由模型可能更有优势。

Qlib benchmark 还提醒，官方结果是完整 workflow 的结果，不只是模型本身；并且作者也说明资源有限，部分模型潜力可能没有完全调出来。因此你不能只看表格排名，必须自己在同一数据、同一切分、同一交易成本下复现。

## 4. 业界和学界现在主要研究什么

截至 2026-04-24，量化和时间序列预测领域的主流方向可以概括为八类。

### 4.1 更强但更稳健的表格模型和因子工程

这仍然是大量机构的核心工作。原因很简单：金融 alpha 很弱，很多时候数据质量、特征定义、交易假设、风控比模型名字更重要。

典型研究点：

- 自动因子挖掘。
- 因子去相关和正交化。
- 样本重加权。
- 特征选择。
- 模型集成。
- 因子衰减检测。
- 同一因子跨市场稳定性。

这对应 Qlib 中的：

- `LightGBM`
- `XGBoost`
- `CatBoost`
- `DoubleEnsemble`
- `Alpha158`
- `ExpressionOps`

### 4.2 深度时间序列模型

近年综述显示，深度学习时间序列预测仍围绕 RNN、CNN/TCN、Transformer、混合模型、预处理增强、外生变量建模等方向发展。2025 年金融预测综述总结了 2020-2024 年 187 篇研究，认为 RNN 及 LSTM 仍占主导，CNN-LSTM 等混合结构越来越常见，多模态信号有助于稳健性，但标准化评估和极端行情鲁棒性仍是缺口。[ScienceDirect, 2025](https://www.sciencedirect.com/science/article/pii/S1059056025008822)

适合你研究的落点：

- `LSTM / GRU / ALSTM` 作为基础。
- `TCN` 作为高效序列基线。
- `Transformer / Localformer` 作为注意力模型基线。
- 比较不同 lookback 窗口、预测 horizon、换手和回撤。

### 4.3 时间序列 Transformer 的新结构

普通 Transformer 并不是时间序列的终点，近年主流变化包括：

- patch 化，把连续时间片段变成 token。
- channel independence，把每个变量单独建模。
- inverted Transformer，把变量当 token，让 attention 建模变量间关系。
- RevIN、归一化和去趋势，缓解分布变化。

代表论文：

- `PatchTST` 提出 patching 和 channel independence，减少 attention 成本并能看更长历史。[arXiv:2211.14730](https://arxiv.org/abs/2211.14730)
- `iTransformer` 把变量维度作为 token，用 attention 学变量间关系，并宣称在多个真实数据集上达到强表现。[arXiv:2310.06625](https://arxiv.org/abs/2310.06625)

对你当前项目的启发：

Qlib 里的 vanilla Transformer、Localformer 可以作为理解基础，但如果你要做新研究，应该考虑引入 PatchTST、iTransformer、TimesNet、TSMixer、DLinear/NLinear、RevIN 等更现代的时间序列基线，而不是只改现有 Transformer 层数。

### 4.4 时间序列基础模型

这是 2024 之后非常热的方向。核心思想是像 NLP 训练大模型一样，在大量跨领域时间序列上预训练，然后做 zero-shot 或 few-shot 预测。

代表模型：

- `TimesFM`：Google 的 decoder-only 时间序列基础模型，ICML 2024，强调 zero-shot 在多数据集上接近监督模型。[PMLR](https://proceedings.mlr.press/v235/das24c.html)、[Google Research](https://research.google/pubs/a-decoder-only-foundation-model-for-time-series-forecasting/)
- `Chronos`：Amazon 的 TMLR 2024 工作，把时间序列数值缩放量化为 token，用语言模型式训练做概率预测。[Amazon Science](https://www.amazon.science/publications/chronos-learning-the-language-of-time-series)
- `Lag-Llama`、`Moirai`、`Time-MoE` 等也都属于这一波。

对量化的真实判断：

这些模型对需求预测、能源、流量、运营类时间序列很有吸引力，但对股票 alpha 不一定直接有效。股票收益是高噪声、强竞争、低信噪比数据，公开预训练模型可能学不到可交易边际优势。

你可以研究，但建议作为：

- 时间序列表征提取器。
- 预训练 backbone。
- 数据稀缺市场的迁移学习工具。
- 与传统 alpha 特征融合的辅助模型。

不建议一开始就押注“直接 zero-shot 预测股票收益”。

### 4.5 跨资产关系、图神经网络、超图

市场不是独立同分布样本。现在很多研究都在引入：

- 行业关系。
- 概念关系。
- 供应链关系。
- 指数成分关系。
- 新闻共现关系。
- 基金共同持仓关系。
- 相关系数动态网络。
- 超图关系。

当前项目对应：

- `GATs`
- `HIST`
- `IGMTF`

研究价值：

如果你研究 A 股，主题、概念、行业轮动很重要，这个方向有潜力。但你必须保证关系数据是 point-in-time 的，也就是当时能知道什么，就只能用什么。

### 4.6 非平稳、概念漂移、在线学习

金融市场最难的不是拟合历史，而是历史规律会变。Qlib README 也强调市场环境非平稳，训练数据分布会在未来测试阶段改变，因此要适应 market dynamics。见 [README.md](../README.md) 和 [examples/benchmarks_dynamic/README.md](../examples/benchmarks_dynamic/README.md)。

主流做法：

- rolling retraining。
- expanding window。
- regime detection。
- domain adaptation。
- sample reweighting。
- meta-learning。
- online learning。
- drift-aware validation。

当前项目对应：

- `Rolling Retraining`
- `DDG-DA`
- `AdaRNN`
- `TRA`
- `DoubleEnsemble`
- online serving 组件

这是最值得你长期投入的方向之一。

### 4.7 LLM 与非结构化金融数据

LLM 在金融里的核心价值不是神秘地“预测涨跌”，而是处理文本、公告、新闻、研报、电话会议、社媒、宏观叙事这些结构化模型难以处理的信息。

代表研究：

- `FinBERT` 表明金融领域语言和普通语言不同，领域预训练能改善金融情绪分析。[arXiv:1908.10063](https://arxiv.org/abs/1908.10063)
- `BloombergGPT` 使用大规模金融和通用语料训练 50B 金融语言模型，在金融任务上表现强。[arXiv:2303.17564](https://arxiv.org/abs/2303.17564)
- `FinGPT` 提供开放金融 LLM 方向，强调自动数据清洗、LoRA 和开放金融应用。[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4489826)
- Lopez-Lira 和 Tang 的研究显示，LLM 对新闻标题里的市场反应和后续漂移有一定预测信息，且能力随模型规模增强，但这类结果必须严防时点泄漏和交易可行性问题。[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788)

当前结论：

非结构化数据很可能提高策略上限，但它不是新手第一步。你要先有结构化基线，再用文本数据做增量实验。

### 4.8 自动化量化研究 Agent

这是 2025 后很新的方向。Microsoft Research 的 `R&D-Agent-Quant` 把量化研发拆成研究、开发、反馈等阶段，做因子和模型联合优化，并报告相对经典因子库有明显收益提升。[Microsoft Research](https://www.microsoft.com/en-us/research/publication/rd-agent-quant-a-multi-agent-framework-for-data-centric-factors-and-model-joint-optimization/)

这类方向很有潜力，但对新手来说更适合用来：

- 自动生成候选因子。
- 自动跑消融实验。
- 自动总结实验日志。
- 自动发现哪些方向值得继续。

不要直接把 Agent 生成的策略当作可交易策略。它仍需要人类设定约束、验证数据、检查泄漏和复现实验。

## 5. 是否需要引入非结构化数据

答案是：最终大概率需要，但不是一开始就需要。

### 5.1 什么时候值得引入

满足以下条件时，非结构化数据值得做：

1. 你的结构化基线已经稳定，例如 LightGBM 的 Rank IC、分组收益、换手、回撤都能复现。
2. 你要预测的 horizon 足够长，让新闻、公告、情绪有时间反映，例如日频到周频。
3. 你能拿到准确发布时间，且能保证模型只使用当时已经公开的信息。
4. 你能做消融实验，证明加入文本后相比纯价格量、纯因子有稳定增益。
5. 你能处理实体对齐，例如新闻里的公司名、股票代码、子公司、供应链公司。

### 5.2 可用的非结构化数据

| 数据 | 可能贡献 | 难点 |
|---|---|---|
| 新闻标题/正文 | 事件冲击、情绪、政策、行业变化 | 时间戳、重复新闻、媒体偏差 |
| 公司公告 | 财报、分红、并购、处罚、增减持 | 发布时间和可交易时间对齐 |
| 研报 | 盈利预期、评级变化、目标价 | 版权、发布时间、覆盖偏差 |
| 社交媒体/股吧 | 散户情绪、注意力 | 噪声极高，容易过拟合 |
| 电话会议纪要 | 管理层语气、业务变化 | 数据成本高，英文市场更成熟 |
| 宏观文本 | 政策、利率、监管、地缘风险 | 映射到个股很难 |
| 图像/音频 | 财报会语音、K 线图像、卫星图等另类数据 | 成本高，不适合新手 |

### 5.3 最推荐的新手做法

第一阶段不要微调大模型，先做轻量特征：

```text
新闻/公告
  -> 时间戳清洗
  -> 股票实体匹配
  -> FinBERT/LLM 情绪分数
  -> 每只股票每天聚合
  -> lag 处理，避免未来函数
  -> 合并到 Alpha158/Alpha360
  -> LightGBM/DoubleEnsemble 消融
```

你要回答的问题不是“LLM 准不准”，而是：

```text
在同一回测框架、同一交易成本、同一股票池、同一时间切分下，
加入文本特征后，Rank IC、分组收益、信息比率、最大回撤是否稳定改善？
```

### 5.4 非结构化数据最大风险

| 风险 | 例子 | 防范 |
|---|---|---|
| 未来函数 | 用到 T 日收盘后甚至 T+1 才发布的新闻预测 T+1 收益 | 按发布时间和交易日严格对齐 |
| 数据覆盖偏差 | 大公司新闻多，小公司新闻少 | 加入覆盖率特征，分市值测试 |
| 情绪误判 | 负面词不一定对应负面股价影响 | 用金融领域模型，不只用通用情绪词典 |
| 重复计数 | 同一新闻被多家媒体转载 | 去重、聚类、来源权重 |
| 幸存者偏差 | 只保留当前仍上市股票 | 使用历史成分和退市数据 |
| 实盘不可得 | 回测用了付费终端历史库，但实盘没有 | 先确认实盘数据源 |

## 6. 每类策略的优劣

### 6.1 传统因子策略

例子：

- 动量。
- 反转。
- 波动率。
- 成交量。
- 换手。
- 估值。
- 盈利质量。
- 成长。

优点：

- 可解释。
- 容易验证。
- 容易做组合约束。
- 是机器学习策略的基础。

缺点：

- 单个因子容易拥挤。
- 公开因子衰减明显。
- 需要持续维护。

适合研究：

新手必须先学。没有因子理解，直接研究深度模型很容易变成黑箱拟合。

### 6.2 机器学习多因子策略

例子：

- `LightGBM`
- `XGBoost`
- `CatBoost`
- `DoubleEnsemble`

优点：

- 能学习非线性和因子交互。
- 对表格特征很强。
- 训练和实验效率高。

缺点：

- 仍依赖特征质量。
- 容易过拟合训练窗口。
- 需要严格的时间序列验证。

适合研究：

最推荐作为你的主线。

### 6.3 深度时序策略

例子：

- `GRU`
- `LSTM`
- `ALSTM`
- `TCN`
- `Transformer`
- `PatchTST`
- `iTransformer`

优点：

- 能处理时间窗口。
- 能从较原始数据中学习模式。
- 适合高频、分钟级或更长历史窗口实验。

缺点：

- 对数据量和算力更敏感。
- 解释性弱。
- 容易在金融噪声中学到偶然模式。

适合研究：

在你掌握树模型后，再做深度时序对比。

### 6.4 图关系策略

例子：

- `GATs`
- `HIST`
- `IGMTF`
- 行业/概念/供应链图

优点：

- 能建模股票联动。
- 对主题投资、行业轮动、风险传导有价值。
- 适合结合非结构化数据。

缺点：

- 数据工程重。
- 时点一致性很难。
- 图构建方式会强烈影响结果。

适合研究：

当你有可靠关系数据时优先级很高。

### 6.5 市场状态适应策略

例子：

- rolling retraining。
- `DDG-DA`
- `AdaRNN`
- `TRA`
- regime detection。

优点：

- 正面处理市场变化。
- 和实盘维护最相关。
- 比单纯换模型更接近真实痛点。

缺点：

- 验证复杂。
- 容易把验证集调成训练集。
- 需要长期、多市场回测。

适合研究：

中长期最值得投入。

### 6.6 强化学习交易执行

例子：

- TWAP。
- PPO。
- OPDS。
- FinRL 相关框架。

优点：

- 适合连续决策。
- 可用于拆单和降低冲击成本。
- 对有规模资金的策略重要。

缺点：

- 环境模拟难。
- 奖励函数难。
- 对新手不友好。

适合研究：

等你已经有 alpha 后再研究。FinRL 论文也强调 DRL 交易有较高开发曲线，框架的目标之一是降低入门难度。[SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3955949)

## 7. 我建议你的研究优先级

### 7.1 最推荐路线

```text
第 1 阶段：LightGBM 基线
第 2 阶段：因子理解和消融
第 3 阶段：DoubleEnsemble
第 4 阶段：滚动训练和市场状态适应
第 5 阶段：HIST/TRA/AdaRNN 选一个深入
第 6 阶段：加入新闻/公告/LLM 文本特征
第 7 阶段：组合优化和交易执行
```

原因：

- 这条路线从最稳健、最容易验证的部分开始。
- 每一步都能产生可比较结果。
- 后续复杂模型可以和前面基线公平比较。
- 不会被“最新模型名字”带偏。

### 7.2 如果你只选一个主线

选：

```text
LightGBM / DoubleEnsemble + 滚动训练 + 少量高质量外部特征
```

这是最现实、最稳健、最适合新手走向研究深水区的组合。

### 7.3 如果你偏研究论文

选：

```text
TRA / HIST / DDG-DA / PatchTST / iTransformer
```

研究问题可以是：

- 多市场状态是否真的存在？
- 图关系是否能提高跨市场泛化？
- 概念漂移能否提前预测？
- Patch 或 inverted Transformer 是否优于 Qlib 现有 Transformer？
- 文本情绪能否给 Alpha158 增量？

### 7.4 如果你偏实盘工程

选：

```text
LightGBM + online serving + rolling retrain + 风险模型 + TopkDropout/优化器
```

你需要关注：

- 每天什么时候更新数据。
- 每天什么时候生成信号。
- 股票停牌、涨跌停、交易成本、滑点。
- 模型多久重训。
- 信号衰减多久。
- 单票、行业、风格暴露限制。

## 8. 具体实验清单

### 实验 1：复现 LightGBM

目标：

- 跑通 `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`
- 理解完整流程。

记录：

- IC。
- Rank IC。
- 年化收益。
- 信息比率。
- 最大回撤。
- 换手。
- 分组收益。

### 实验 2：Alpha158 vs Alpha360

目标：

- 同一个模型分别跑 `Alpha158` 和 `Alpha360`。
- 理解人工因子和原始价格量特征的差异。

问题：

- 哪个 Rank IC 更高？
- 哪个回撤更小？
- 哪个换手更高？
- 哪个对训练窗口更敏感？

### 实验 3：LightGBM vs XGBoost vs CatBoost

目标：

- 比较树模型。

注意：

- 同一股票池。
- 同一切分。
- 同一交易成本。
- 同一特征。
- 不要只看一次结果。

### 实验 4：DoubleEnsemble

目标：

- 验证样本重加权和特征选择是否提高稳定性。

观察：

- 是否提高 ICIR。
- 是否降低回撤。
- 是否降低不同 seed 的波动。
- 是否减少无效特征。

### 实验 5：滚动训练

目标：

- 比较一次训练、固定窗口滚动、扩展窗口滚动。

核心问题：

- 模型多久过期？
- 最近数据是否更重要？
- 牛市、熊市、震荡市表现是否不同？

### 实验 6：TRA 或 AdaRNN

目标：

- 研究市场状态和分布漂移。

不要只问：

```text
收益有没有更高？
```

还要问：

```text
在哪些年份更高？
在哪些市场环境更高？
换手是否变高？
是否只是更激进？
是否跨股票池仍有效？
```

### 实验 7：加入文本情绪

目标：

- 检验非结构化数据是否提供增量。

最小可行流程：

```text
新闻标题
  -> 股票代码匹配
  -> 发布时间对齐
  -> FinBERT/LLM 情绪分数
  -> 每日聚合
  -> 加入 Alpha158
  -> LightGBM 消融
```

对照组：

- 无文本。
- 只有新闻数量。
- 只有情绪。
- 新闻数量 + 情绪。
- 情绪按市值分组。
- 情绪按行业分组。

## 9. 常见误区

### 误区 1：模型越新越好

金融里不是这样。很多新模型在公开数据上表现好，但换市场、换交易成本、换时间段就失效。树模型和线性模型仍然是必须打败的基线。

### 误区 2：预测价格比预测排序重要

量化选股更常见的是预测相对排序，不是预测绝对价格。Rank IC 往往比 MSE 更接近组合收益。

### 误区 3：回测收益高就说明模型好

不一定。可能是：

- 换手太高。
- 交易成本低估。
- 使用了未来数据。
- 某一年行情特殊。
- 单票集中。
- 行业暴露过大。

### 误区 4：非结构化数据一定更高级

文本、新闻、研报很有价值，但也更容易引入泄漏和噪声。如果结构化基线都不稳定，直接上 LLM 只会增加不确定性。

### 误区 5：LLM 可以直接替代量化研究员

LLM 更适合做信息抽取、代码辅助、实验总结、因子灵感生成。真正的收益来自数据、验证、风控、执行和持续迭代。

## 10. 90 天学习和研究计划

### 第 1-2 周：Qlib 和多因子基础

目标：

- 理解 `Alpha158`、`Alpha360`。
- 跑通 LightGBM。
- 看懂 IC、Rank IC、IR、MDD。
- 理解 `TopkDropoutStrategy`。

输出：

- 一份 baseline 实验记录。
- 一张因子/标签/策略流程图。

### 第 3-4 周：树模型和因子消融

目标：

- 比较 LightGBM、XGBoost、CatBoost。
- 做特征组删除实验。
- 做不同股票池、不同年份测试。

输出：

- 哪些因子组贡献最大。
- 模型稳定性比较。

### 第 5-6 周：DoubleEnsemble

目标：

- 理解样本重加权和特征选择。
- 复现并比较 LightGBM baseline。

输出：

- DoubleEnsemble 是否提升 ICIR 和回撤。
- 哪些特征被筛掉。

### 第 7-8 周：滚动训练和市场状态

目标：

- 做 rolling retraining。
- 比较不同训练窗口。
- 分年份、分行情分析。

输出：

- 模型衰减曲线。
- 最合适的重训频率。

### 第 9-10 周：TRA、AdaRNN 或 DDG-DA 三选一

目标：

- 深入一个动态适应模型。
- 不只看收益，还看稳定性和失效场景。

输出：

- 一份模型机制解读。
- 一份和 LightGBM/DoubleEnsemble 的公平对比。

### 第 11-12 周：非结构化数据小实验

目标：

- 只加入一个简单文本特征，例如公告数量、新闻情绪、新闻热度。
- 做严格时间对齐。

输出：

- 文本是否有增量。
- 哪些股票、行业、时间段增量更明显。

## 11. 推荐阅读顺序

### Qlib 项目内

1. [README.md](../README.md)
2. [examples/benchmarks/README.md](../examples/benchmarks/README.md)
3. [examples/benchmarks/LightGBM](../examples/benchmarks/LightGBM)
4. [qlib/contrib/data/handler.py](../qlib/contrib/data/handler.py)
5. [qlib/contrib/strategy/signal_strategy.py](../qlib/contrib/strategy/signal_strategy.py)
6. [examples/benchmarks_dynamic/README.md](../examples/benchmarks_dynamic/README.md)
7. [examples/rl_order_execution/README.md](../examples/rl_order_execution/README.md)

### 经典基线

1. LightGBM, NeurIPS 2017: https://papers.nips.cc/paper_files/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html
2. XGBoost, KDD 2016: https://www.kdd.org/kdd2016/subtopic/view/xgboost-a-scalable-tree-boosting-system/670/
3. CatBoost, NeurIPS 2018: https://papers.nips.cc/paper_files/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html
4. DoubleEnsemble, ICDM 2020: https://arxiv.org/abs/2010.01265

### 金融时序与动态市场

1. TRA, KDD 2021: https://arxiv.org/abs/2106.12950
2. HIST: https://arxiv.org/abs/2110.13716
3. DDG-DA, AAAI 2022: https://arxiv.org/abs/2201.04038
4. Deep learning for financial forecasting review, 2025: https://www.sciencedirect.com/science/article/pii/S1059056025008822

### 前沿时间序列模型

1. PatchTST: https://arxiv.org/abs/2211.14730
2. iTransformer: https://arxiv.org/abs/2310.06625
3. TimesFM, ICML 2024: https://proceedings.mlr.press/v235/das24c.html
4. Chronos, TMLR 2024: https://www.amazon.science/publications/chronos-learning-the-language-of-time-series

### LLM 和金融非结构化数据

1. FinBERT: https://arxiv.org/abs/1908.10063
2. BloombergGPT: https://arxiv.org/abs/2303.17564
3. FinGPT: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4489826
4. Can ChatGPT Forecast Stock Price Movements?: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788
5. R&D-Agent-Quant: https://www.microsoft.com/en-us/research/publication/rd-agent-quant-a-multi-agent-framework-for-data-centric-factors-and-model-joint-optimization/

## 12. 最终建议

如果你是小白，最好的策略不是“找一个最强模型”，而是建立一套可复现、可比较、可迭代的研究流程。

我建议你的第一条主线是：

```text
LightGBM 基线
  -> Alpha158/Alpha360 对比
  -> 特征消融
  -> DoubleEnsemble
  -> rolling retraining
  -> TRA 或 DDG-DA
  -> 少量文本特征增量
  -> 风险模型和组合优化
```

你真正要追求的不是单次回测最高收益，而是：

- 跨年份有效。
- 跨股票池有效。
- 换 seed 稳定。
- 交易成本后有效。
- 回撤可控。
- 换手可接受。
- 逻辑能解释。
- 数据没有未来函数。

能满足这些条件的策略，才有继续深入研究的价值。

