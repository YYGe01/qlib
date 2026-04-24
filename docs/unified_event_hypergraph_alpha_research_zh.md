# 数据中心的事件-超图统一 Alpha 研究路线

> 面向 A 股多源结构化/非结构化信息的研究建议  
> 更新时间：2026-04-24  
> 适用读者：已经理解机器学习、深度学习、NLP/LLM、Qlib 基本流程，希望尽快找准研究方向的工程师  
> 免责声明：本文是研究路线与工程方案，不构成投资建议。

## 0. 一句话结论

你的想法是对的，而且很有研究价值：**数据比模型更重要，尤其是在金融预测里，谁能更早、更准、更稳定地把现实世界事件转成 point-in-time 的可训练信号，谁就更接近长期优势。**

但我不建议一开始做一个“把所有信息都塞进一个巨型模型，然后直接预测股票涨跌”的大一统黑盒。更可行、也更符合当前业界和学术趋势的“大一统”是：

```text
统一数据底座
  -> 统一事件表示
  -> 统一关系网络/超图
  -> 统一特征与样本生成
  -> 多模型/多专家动态融合
  -> 排序/组合/风险控制
```

也就是：

```text
Event-Centric Data Lake
+ Event Ontology
+ Entity Linking
+ Heterogeneous Graph / Hypergraph
+ Point-in-Time Feature Store
+ LightGBM / Ranking Model / Dynamic MoE / Hypergraph Neural Network
```

如果必须给一个最值得研究的方向，我会推荐：

**LLM 辅助的事件抽取 + A 股实体链接 + 动态异构超图 + 横截面收益排序模型。**

这条路线兼顾了你的 NLP/LLM 能力、Qlib 现有框架、A 股实际可交易目标，以及当前研究前沿。

## 1. 你的想法是否成立

你提出的核心假设是：

> 不只看股票自身价格、成交量、财务指标，还要尽量收集当时世界上所有可能影响 A 股的信息，包括战争冲突、气候变化、世界局势、经济水平、政策变化、情绪舆论、产业链变化等，然后用模型训练预测。

这个方向成立，而且不是空想。已有研究已经在多个子方向验证过类似思路：

- **事件驱动预测**：早期研究已经从新闻中抽取事件，再建模事件对股价的短期和长期影响。例如 Ding 等人在 IJCAI 2015 的事件驱动股票预测工作，以及 COLING 2016 的知识驱动事件嵌入工作，明确把新闻事件和知识图谱引入股票预测。
- **多源异构数据融合**：已有研究把交易数据、新闻文本、图形指标、关系图等融合到图神经网络中，证明多源信息和关系语义可以提升预测。
- **知识图谱/异构图**：金融文本不是孤立文本，事件背后有公司、行业、供应链、政策、地区、商品、汇率等实体关系。异构图适合建模多类型节点和多类型边。
- **超图关系**：很多金融冲击不是二元关系，而是“一件事同时影响一组股票/行业/商品/国家”。超图用一条超边连接多个节点，比普通图更适合表达高阶群体关系。
- **LLM 金融信息抽取和情绪建模**：FinBERT、BloombergGPT、FinGPT、LLM 金融新闻情绪研究都说明，金融 NLP 已经从简单情绪分类走向结构化事件理解、领域知识注入和数据中心化。
- **宏观/地缘政治/政策不确定性指标**：GPR、EPU、GDELT、AI-GPR 这类数据说明“用新闻构建宏观风险指标”已经是严肃研究路线，不是民间猜想。

所以，你的方向有前景。真正的难点不在“有没有模型”，而在：

- 如何保证数据是当时可见的，不能有未来函数。
- 如何把非结构化信息转成稳定、可回测、可解释的结构化事件。
- 如何把事件传导到 A 股具体标的，而不是停留在笼统的“今天战争风险高”。
- 如何处理不同事件的影响方向、滞后、衰减、行业差异和市场状态差异。
- 如何证明新增数据带来的是真实增量信号，而不是过拟合。

## 2. 是否存在真正的大一统模型

### 2.1 不建议追求单一黑盒大模型

理论上，可以做一个模型：

```text
价格序列 + 财务数据 + 新闻 + 研报 + 政策 + 宏观 + 舆情 + 图关系 + 图像
  -> 巨型多模态 Transformer
  -> 未来收益预测
```

但在金融场景里，这种路线一开始并不合适，原因很现实：

- 金融标签噪声极大，收益率信号弱，巨型模型很容易学习到伪相关。
- A 股历史有效样本没有看起来那么多，日频横截面样本虽然多，但时间维度仍然有限。
- 非结构化信息存在发布时间、转载时间、交易时段、披露延迟、修订版本等复杂问题。
- 模型越黑盒，越难判断到底是事件信息有效，还是泄漏、幸存者偏差、行业暴露在起作用。
- 真实投研更关心增量 IC、换手、回撤、容量、风险暴露，而不是单纯预测准确率。

所以，**单一大模型不是目前最优起点**。

### 2.2 更现实的大一统是“统一表示 + 分层模型”

我建议的大一统不是一个模型，而是一个架构：

```text
现实世界信息
  -> 原始数据湖
  -> 事件抽取
  -> 实体链接
  -> 事件-实体-关系超图
  -> point-in-time 特征库
  -> 预测模型
  -> 组合与风控
```

这套架构里，真正统一的是：

- **统一时间轴**：所有数据都按“当时何时可见”对齐。
- **统一事件表示**：所有非结构化信息最终转成事件、情绪、风险、主题、影响范围。
- **统一实体体系**：公司、股票、行业、商品、国家、政策、人物、机构、地区都能被链接。
- **统一关系表达**：二元关系用图，高阶群体关系用超图。
- **统一评估方式**：所有新增数据和模型都必须通过相同的回测和消融验证。

这样你可以持续增加数据，而不必每次推倒重来。

## 3. 当前研究已经做到哪里

### 3.1 事件驱动股票预测

事件驱动预测是你的想法中最核心的一支。

早期代表路线：

- 从新闻文本中抽取结构化事件。
- 把事件表示成向量。
- 建模事件对市场或个股的短期、长期影响。
- 结合历史行情做预测。

相关研究包括：

- Ding, Zhang, Liu, Duan 的 **Deep Learning for Event-Driven Stock Prediction**，提出从新闻文本抽取事件，并用深度模型学习事件对股票走势的影响。
- Ding 等人的 **Knowledge-Driven Event Embedding for Stock Prediction**，进一步把知识图谱信息加入事件嵌入，解决单纯文本事件缺少实体背景知识的问题。

这说明：**“新闻 -> 事件 -> 表征 -> 预测”这条路线经得起时间检验。**

但早期事件驱动方法有局限：

- 事件类型和抽取质量有限。
- 主要面向英文新闻和美股数据。
- 对 A 股政策、产业链、监管、概念炒作等机制适配不足。
- 对事件传播关系建模较弱。
- 很多方法没有足够严格处理 point-in-time。

这正是你可以研究的空间。

### 3.2 知识图谱和异构图

金融市场不是简单的时间序列系统，而是一个关系网络。

典型节点包括：

- 股票
- 上市公司
- 行业
- 概念板块
- 产品
- 原材料
- 供应商
- 客户
- 地区
- 国家
- 政策部门
- 基金
- 券商
- 分析师
- 新闻事件
- 宏观指标
- 商品期货
- 汇率
- 利率

典型边包括：

- 属于同一行业
- 属于同一概念
- 上下游供应链
- 同一实际控制人
- 股权持有
- 基金共同持仓
- 客户/供应商
- 同地区生产基地
- 同商品价格暴露
- 同政策暴露
- 新闻共现
- 舆情共振
- 收益相关性
- 波动相关性

异构图适合表达这种多类型节点、多类型关系。已有研究表明，金融文本中的多粒度信息可以构成异构图，异构神经网络可以聚合不同粒度的语义信息，用于市场预测。

但普通图的限制是：它主要表达二元边，即 `A -> B`。现实中很多关系不是二元的。

### 3.3 超图关系：你补充的点非常关键

你提到“超图关系”，这非常重要。

普通图：

```text
股票 A -- 股票 B
股票 B -- 股票 C
```

超图：

```text
超边 E1 = {股票 A, 股票 B, 股票 C, 行业 X, 商品 Y, 事件 Z}
```

超图的一条边可以连接多个节点，适合表达高阶群体关系。

金融里的很多关系天然是超图：

- 一个政策同时影响多个行业。
- 一场战争同时影响能源、航运、军工、黄金、汇率、通胀。
- 一次极端天气同时影响农业、电力、煤炭、物流、保险。
- 一个基金组合同时持有多个股票。
- 一个概念题材同时覆盖一组上市公司。
- 一个供应链链条连接原材料、设备商、制造商、品牌商、渠道商。
- 一个地区疫情/自然灾害同时影响当地多个企业。
- 一个海外制裁事件同时影响若干公司、技术路线和替代产业。

所以，如果你的目标是“收集所有可能影响 A 股的事件和关系”，超图不是锦上添花，而是很可能成为核心表达。

### 3.4 动态超图是当前非常值得研究的方向

静态超图只能表达长期稳定关系，比如行业、概念、基金持仓。

但市场关系会变：

- 热门题材会变。
- 产业链关注点会变。
- 同一政策对不同行业的影响会变。
- 不同市场状态下，资金偏好的关系会变。
- 同一事件在牛市、熊市、震荡市的传导方式会不同。

因此更有价值的是：

```text
动态超图 = 静态关系 + 动态事件 + 动态市场共振 + 动态注意力权重
```

相关研究已经出现：

- **DHSTN** 使用动态超图时空网络建模股票高阶关系，并在 CSI300 和 NASDAQ100 数据集上实验，论文指出传统图只考虑成对关系，而超图可以捕捉多股票高阶关系。
- **TD-HCN** 把先验约束关系学习、局部动态关系和全局静态关系结合，用于股票收益排序。
- 多关系超图方法开始把行业关系、供应链关系、异常波动检测、层次注意力结合起来。

这说明：**超图关系已经从“可以想”变成“正在被验证”。**

## 4. 数据比模型重要，但数据不能只是“越多越好”

### 4.1 金融数据的核心不是量，而是可用性

在大语言模型训练里，数据量很重要。但在量化预测里，数据的价值取决于：

- 是否 point-in-time。
- 是否有清晰发布时间。
- 是否能映射到具体标的。
- 是否能在交易决策前可见。
- 是否能跨历史周期稳定复现。
- 是否能通过消融验证有增量 IC。
- 是否不会引入幸存者偏差、未来函数和修订泄漏。

很多看起来很强的数据，其实不能直接用：

- 宏观数据常有发布日期和修订版本问题。
- 财报数据有公告时间，不是报告期结束日就可见。
- 新闻有首发、转载、聚合、翻译、摘要生成等时间差。
- 社交媒体有删除、热度回填、平台推荐偏差。
- 产业链数据可能是后来整理出来的，不代表历史当时可见。
- 概念板块成分经常是事后归因，容易泄漏。

所以，你的“数据中心化”方向必须加一个约束：

> 只使用当时可见的数据，并记录每条数据的可见时间。

### 4.2 非结构化数据要引入，但不要直接裸喂

非结构化数据非常值得引入，包括：

- 新闻
- 公告
- 研报
- 政策文件
- 监管问询
- 社交媒体
- 论坛讨论
- 电话会纪要
- 公司互动平台问答
- 图片/视频新闻
- 天气灾害报道
- 地缘政治新闻

但不建议一开始把原文直接塞给模型预测收益。更稳的做法是：

```text
原文
  -> 去重、溯源、时间对齐
  -> LLM/信息抽取模型
  -> 结构化事件
  -> 实体链接
  -> 影响方向/强度/置信度
  -> 事件特征
  -> Qlib Dataset
```

也就是说，非结构化数据最好先变成：

- 事件类型
- 事件主体
- 事件客体
- 影响对象
- 情绪方向
- 风险强度
- 主题标签
- 地区标签
- 行业标签
- 商品标签
- 影响链路
- 发布时间
- 可见时间
- 来源可信度
- 新颖度
- 重复度
- 热度变化

这样才能进入稳定的量化回测。

## 5. 推荐的大一统架构

我建议你把整个系统抽象成 8 层。

```text
Layer 1: Raw Data Lake
Layer 2: Point-in-Time Timeline
Layer 3: Event Extraction
Layer 4: Entity Linking
Layer 5: Heterogeneous Graph + Hypergraph
Layer 6: Feature Store
Layer 7: Prediction Models
Layer 8: Portfolio & Risk
```

### 5.1 Layer 1: 原始数据湖

目标：保存一切原始信息，不急着决定哪些有用。

数据类别：

| 类别 | 示例 | 价值 |
| --- | --- | --- |
| 行情 | OHLCV、复权、停牌、涨跌停 | 基础价格行为 |
| 基本面 | 财报、估值、盈利预测 | 中长期价值 |
| 资金 | 北向、融资融券、ETF、龙虎榜 | 资金流和交易拥挤 |
| 公告 | 定增、并购、减持、回购、处罚 | 公司级事件 |
| 新闻 | 财经新闻、国际新闻、行业新闻 | 事件和情绪 |
| 政策 | 国常会、部委文件、地方政策 | A 股政策敏感性 |
| 宏观 | GDP、CPI、PPI、PMI、社融、利率 | 市场状态和风格 |
| 海外 | 美债、美元、VIX、原油、黄金、海外指数 | 外部冲击 |
| 地缘 | 战争、制裁、外交冲突、恐袭 | 风险偏好和供应链 |
| 气候 | 极端天气、洪水、干旱、台风、温度 | 农业、电力、物流、保险 |
| 舆情 | 股吧、雪球、微博、新闻评论 | 散户情绪和关注度 |
| 产业链 | 供应商、客户、产品、技术路线 | 事件传导 |
| 持仓 | 基金持仓、机构调研、共同持仓 | 资金拥挤与机构信息 |

关键字段：

```text
source_id
source_name
raw_text / raw_value
publish_time
ingest_time
visible_time
language
url
source_reliability
dedup_hash
revision_id
```

其中最重要的是 `visible_time`。

### 5.2 Layer 2: Point-in-Time 时间轴

所有数据必须对齐到交易决策时间。

A 股尤其要注意：

- 盘前可见信息
- 盘中可见信息
- 午间公告
- 盘后公告
- 夜间海外事件
- 节假日期间事件
- 涨跌停导致无法成交
- 停牌和复牌
- 指数成分历史变化
- 财报公告日而不是报告期

建议统一成几个可训练切片：

```text
T日开盘前可见信息 -> 预测 T日 open-to-close / close-to-close
T日收盘后可见信息 -> 预测 T+1 日收益
周末/节假日累计信息 -> 预测下一交易日或下一周
```

如果你先做日频，最稳的是：

```text
截至 T 日收盘后可见的信息 -> 预测 T+1 到 T+5 的横截面收益
```

这样可以先避开盘中时间戳细节。

### 5.3 Layer 3: 事件抽取

目标：把非结构化文本变成结构化事件。

推荐事件结构：

```json
{
  "event_id": "event_20260424_001",
  "event_time": "2026-04-24T10:32:00+08:00",
  "visible_time": "2026-04-24T10:35:00+08:00",
  "source": "news",
  "event_type": "geopolitical_conflict",
  "event_subtype": "sanction",
  "subject_entities": ["country:US"],
  "object_entities": ["country:CN", "industry:semiconductor"],
  "mentioned_companies": ["stock:688981.SH"],
  "affected_entities": [
    {"entity": "industry:semiconductor", "direction": -1, "strength": 0.82},
    {"entity": "industry:domestic_substitution", "direction": 1, "strength": 0.64}
  ],
  "topics": ["sanction", "chip", "supply_chain"],
  "sentiment": -0.71,
  "risk_score": 0.88,
  "novelty": 0.76,
  "uncertainty": 0.65,
  "confidence": 0.78
}
```

你作为 NLP/LLM 工程师，优势就在这里：

- 设计事件 ontology。
- 做金融实体识别。
- 做实体消歧。
- 用 LLM 生成候选事件。
- 用规则/小模型/人工校验提高稳定性。
- 用 RAG 注入行业和公司知识。
- 把事件影响拆成结构化字段。

### 5.4 Layer 4: 实体链接

事件必须落到可交易标的，否则无法变成 Alpha。

实体链接要覆盖：

```text
新闻实体 -> 公司主体 -> 股票代码
公司实体 -> 行业/概念/地域
公司实体 -> 产品/原材料/客户/供应商
政策实体 -> 监管部门/政策主题/受益行业
国家实体 -> 贸易关系/商品供需/汇率风险
气候实体 -> 地区/农业品/电力/交通/保险
人物实体 -> 公司高管/监管人物/央行官员
```

例子：

```text
“稀土出口管制”
  -> 商品: 稀土
  -> 行业: 小金属、军工、新能源材料
  -> A股公司: 北方稀土、盛和资源等
  -> 海外冲击: 中美贸易摩擦
  -> 事件类型: 政策/贸易/供应链
```

实体链接质量通常比模型结构更重要。

### 5.5 Layer 5: 异构图 + 超图

这是本文最核心的一层。

#### 普通异构图

适合表达二元关系：

```text
公司 -> 属于 -> 行业
公司 -> 位于 -> 地区
公司 -> 供应 -> 公司
基金 -> 持有 -> 股票
新闻 -> 提到 -> 公司
政策 -> 影响 -> 行业
```

#### 超图

适合表达高阶群体关系：

```text
事件超边: 一条事件连接多个受影响公司/行业/商品/国家
主题超边: 一个概念连接一组股票
行业超边: 一个行业连接行业内所有股票
供应链超边: 一条产业链连接上中下游企业
基金持仓超边: 一个基金组合连接所有持仓股票
地域超边: 一个地区连接当地企业、天气、政策、港口、电力
商品暴露超边: 一个商品连接生产商、消费商、替代品、期货价格
宏观因子超边: 一个宏观变量连接利率敏感、汇率敏感、出口敏感股票
舆情主题超边: 一个热议主题连接被共同讨论的一组股票
动态共振超边: 一段时间内收益/成交/情绪共振的一组股票
```

#### 为什么超图适合你的想法

因为你关注的是“任何事件可能影响 A 股的任何方向”。这种影响往往不是一对一，而是：

```text
事件 -> 一组行业 -> 一组公司 -> 一组资金行为 -> 一组风格因子
```

比如：

```text
俄乌冲突升级
  -> 能源价格
  -> 化工成本
  -> 农产品价格
  -> 军工关注度
  -> 黄金避险
  -> 全球通胀预期
  -> 美债利率
  -> 人民币汇率
  -> A股风险偏好
```

普通图可以表达很多边，但会丢失“这是同一个事件引发的一组联动”。超图可以保留这个高阶上下文。

## 6. 超图关系应该如何设计

### 6.1 超图基本对象

定义：

```text
节点 V:
  stock, company, industry, concept, commodity, country, region,
  policy, event, fund, macro_indicator, sentiment_topic

超边 E:
  industry_membership, supply_chain_group, event_impact_group,
  fund_holding_group, concept_group, geography_group,
  commodity_exposure_group, macro_sensitivity_group,
  sentiment_topic_group, dynamic_comovement_group
```

一条超边可以写成：

```text
e = {
  type: "event_impact_group",
  timestamp: "2026-04-24",
  nodes: [event_x, industry_a, stock_1, stock_2, commodity_y, country_z],
  weight: 0.83,
  direction: mixed,
  decay_half_life: 5 trading days
}
```

### 6.2 静态超边

静态超边相对稳定，可低频更新。

| 超边类型 | 例子 | 更新频率 |
| --- | --- | --- |
| 行业超边 | 申万一级/二级/三级行业 | 月度/季度 |
| 概念超边 | 人形机器人、低空经济、AI 算力 | 周度/事件驱动 |
| 地域超边 | 长三角、粤港澳、成渝 | 低频 |
| 供应链超边 | 光伏硅料-硅片-电池-组件 | 季度/事件驱动 |
| 商品暴露超边 | 原油、铜、锂、煤、稀土 | 月度/事件驱动 |
| 基金持仓超边 | 某基金季报持仓 | 季度 |
| 股权控制超边 | 同一实控人、集团系 | 季度/公告 |

静态超边的作用：

- 提供长期结构先验。
- 帮助事件扩散。
- 帮助模型识别行业/主题联动。
- 降低纯数据驱动关系的噪声。

### 6.3 动态超边

动态超边由数据实时生成。

| 超边类型 | 生成方式 | 价值 |
| --- | --- | --- |
| 事件影响超边 | LLM 抽取受影响实体 | 直接表达新闻/政策冲击 |
| 新闻共现超边 | 同一时间窗口共同出现 | 表达媒体叙事 |
| 舆情主题超边 | 社交平台 topic clustering | 表达市场关注度 |
| 收益共振超边 | rolling correlation / clustering | 表达价格联动 |
| 成交拥挤超边 | 放量、换手、龙虎榜、ETF 流入 | 表达资金一致行为 |
| 异常波动超边 | 同期极端收益/波动 | 表达冲击传播 |
| 宏观敏感超边 | rolling beta to rate/fx/commodity | 表达状态变化 |

动态超边的作用：

- 适应市场风格切换。
- 捕捉短期主题炒作。
- 捕捉事件扩散。
- 捕捉隐含关系。

### 6.4 超边权重

每条超边需要权重。权重来源可以是：

```text
事件强度
新闻来源可信度
新闻传播热度
实体相关性
LLM 置信度
历史敏感度
市场反应强度
行业暴露程度
供应链收入占比
共同持仓比例
rolling correlation
attention learned weight
```

建议先用可解释规则，再逐步引入学习式权重。

例子：

```text
event_hyperedge_weight =
  source_reliability
  * event_novelty
  * event_severity
  * entity_link_confidence
  * historical_sensitivity
```

### 6.5 超边方向

超图不一定只是无向关系。金融里方向很重要。

例子：

```text
原油上涨:
  利好: 油气开采、油服
  利空: 航空、化工下游、物流
  中性/复杂: 煤化工、新能源
```

所以需要：

```text
hyperedge_direction:
  positive_nodes
  negative_nodes
  uncertain_nodes
```

这比简单地把一组股票连在一起更有价值。

## 7. 关系类型清单：建议全部考虑，但分阶段做

你说“还有这些关系，也考虑”。我建议把关系分成 12 类。

### 7.1 公司基本关系

- 行业分类
- 概念板块
- 主营产品
- 地区
- 上市板块
- 市值分层
- 国企/民企/央企
- 实控人
- 子公司/母公司

价值：基础结构先验。

优点：容易拿到，稳定。  
缺点：很多人都用，边际 alpha 不一定高。

### 7.2 供应链关系

- 上游原材料
- 中游制造
- 下游客户
- 关键设备
- 关键零部件
- 替代品
- 进口依赖
- 出口依赖

价值：事件传导最重要的关系之一。

优点：解释性强，适合事件扩散。  
缺点：数据清洗难，历史版本难。

### 7.3 商品暴露关系

- 原油
- 天然气
- 煤炭
- 铜
- 铝
- 锂
- 镍
- 稀土
- 黄金
- 农产品

价值：连接全球事件和 A 股行业。

优点：商品价格高频、客观、可回测。  
缺点：对不同公司影响方向不同，需要区分生产者和消费者。

### 7.4 宏观敏感关系

- 利率敏感
- 汇率敏感
- 信用敏感
- 通胀敏感
- 出口敏感
- 地产敏感
- 消费敏感
- 财政政策敏感
- 货币政策敏感

价值：决定市场风格和风险偏好。

优点：可以解释大级别行情。  
缺点：日频个股 alpha 弱，滞后和状态依赖强。

### 7.5 政策关系

- 监管政策
- 产业政策
- 财政补贴
- 反腐/集采
- 环保限产
- 安全生产
- 出口管制
- 进口替代
- 地方政策

价值：A 股特别重要。

优点：A 股政策驱动明显。  
缺点：政策语义复杂，市场经常预期先行。

### 7.6 地缘政治关系

- 战争冲突
- 制裁
- 贸易摩擦
- 外交冲突
- 军事演习
- 恐怖袭击
- 供应链封锁
- 能源运输风险

价值：影响风险偏好、资源品、军工、出口链、汇率。

优点：外部冲击强，适合事件研究。  
缺点：低频、极端、样本少，容易过拟合。

### 7.7 气候与自然灾害关系

- 高温
- 寒潮
- 干旱
- 洪水
- 台风
- 地震
- 火灾
- 疫病
- 运输中断

价值：农业、电力、煤炭、保险、交通、建筑、消费。

优点：数据可观测，有地理维度。  
缺点：影响链条长，需要地域和产业映射。

### 7.8 舆情和情绪关系

- 新闻情绪
- 社交媒体情绪
- 股吧热度
- 搜索指数
- 研报语气
- 评论分歧度
- 情绪极化
- 叙事扩散速度

价值：捕捉短期关注度和交易拥挤。

优点：对 A 股短线题材可能有用。  
缺点：噪声大、平台偏差大、容易反身性。

### 7.9 资金关系

- 北向资金
- 融资融券
- ETF 申赎
- 公募持仓
- 私募调研
- 龙虎榜
- 机构共同持仓
- 基金风格暴露

价值：资金行为本身就是价格驱动因素。

优点：比文本更接近交易。  
缺点：有些数据披露滞后，不能误用事后数据。

### 7.10 市场共振关系

- 收益相关
- 波动相关
- 成交相关
- 跳空共振
- 共同涨停
- 共同破位
- 板块联动

价值：捕捉隐含关系和市场实际交易结构。

优点：完全基于市场数据，可 point-in-time。  
缺点：容易追涨杀跌，关系变化快。

### 7.11 文本共现关系

- 同一新闻提到多个公司
- 同一主题下多个行业
- 同一政策文件涉及多个部门
- 同一舆情话题下多个股票

价值：连接非结构化信息与超图。

优点：适合 LLM/NLP。  
缺点：共现不等于因果，需要置信度和过滤。

### 7.12 因果/传导关系

- 事件 -> 商品 -> 行业 -> 公司
- 政策 -> 需求 -> 盈利 -> 估值
- 战争 -> 油价 -> 通胀 -> 利率 -> 风格
- 天气 -> 供给 -> 价格 -> 利润
- 舆情 -> 关注度 -> 资金流 -> 短期收益

价值：最接近真正可解释 alpha。

优点：研究价值最高。  
缺点：最难，需要长期积累。

## 8. 模型层怎么选

### 8.1 第一阶段不要放弃 LightGBM

你已经跑过 LightGBM，这很好。不要急着换掉它。

原因：

- LightGBM 对表格特征非常强。
- 对小样本、弱信号、噪声标签更稳。
- 训练快，适合做大量消融。
- 特征重要性和分组实验容易解释。
- Qlib 里落地成本低。

第一阶段最佳方案不是上复杂模型，而是：

```text
Alpha158 / Alpha360 基线
  + 事件特征
  + 情绪特征
  + 宏观特征
  + 超图聚合特征
  -> LightGBM / XGBoost / CatBoost / Linear Ranker
```

目标是证明：

```text
新增事件-超图数据能提高 Rank IC、ICIR、组合收益、回撤表现。
```

只要这个证明成立，后面再上深度模型才有意义。

### 8.2 第二阶段：动态融合/门控模型

市场不是一个状态。

常见状态：

- 牛市
- 熊市
- 震荡市
- 高波动
- 低波动
- 政策驱动
- 资金驱动
- 业绩驱动
- 题材驱动
- 外部风险冲击

不同状态下，数据权重不同：

- 政策行情：政策事件权重大。
- 资源品行情：商品和地缘权重大。
- 成长风格：利率和风险偏好权重大。
- 小票题材：舆情和热度权重大。
- 业绩期：财报和预告权重大。

所以可以做：

```text
Regime Detector
  -> gate weights
  -> combine experts
```

专家模型包括：

- price expert
- fundamental expert
- event expert
- sentiment expert
- macro expert
- graph/hypergraph expert

这比一个固定权重模型更符合金融市场。

### 8.3 第三阶段：图神经网络/超图神经网络

当你已经有稳定关系数据后，再上图模型：

- GCN
- GAT
- Heterogeneous GNN
- R-GCN
- HAN
- Hypergraph Convolution
- Hypergraph Attention
- Dynamic Hypergraph Network

推荐优先级：

```text
异构图特征聚合
  -> 超图特征聚合
  -> 动态超图注意力
  -> 端到端图时序模型
```

不要一开始就端到端，因为调试困难。

### 8.4 第四阶段：金融事件基础模型

等你积累了足够多事件数据，可以考虑预训练：

```text
Masked event modeling
Next event prediction
Entity-event contrastive learning
Stock-event alignment
Event impact prediction
Temporal graph contrastive learning
```

预训练目标示例：

```text
给定历史事件序列，预测下一个事件类型。
给定事件文本，预测受影响行业。
给定事件和公司，预测影响方向。
给定事件超边，预测被遮蔽的受影响实体。
给定事件前后市场反应，学习事件冲击 embedding。
```

这才是真正可能走向“金融世界模型”的方向。

## 9. 如何把事件变成 Qlib 可训练特征

Qlib 里最终需要的是类似：

```text
datetime, instrument, feature_1, feature_2, ..., label
```

你的事件数据需要聚合到：

```text
date x stock
```

### 9.1 个股事件特征

```text
stock_event_count_1d
stock_event_count_5d
stock_pos_event_count_5d
stock_neg_event_count_5d
stock_event_sentiment_mean_5d
stock_event_risk_max_5d
stock_event_novelty_max_5d
stock_policy_event_count_20d
stock_geopolitical_exposure_20d
stock_climate_event_count_20d
```

### 9.2 行业事件扩散特征

```text
industry_event_count_1d
industry_neg_sentiment_5d
industry_policy_support_score_20d
industry_geopolitical_risk_20d
industry_news_heat_rank_5d
industry_event_dispersion_5d
```

### 9.3 超图聚合特征

```text
hyper_event_exposure_score
hyper_policy_support_score
hyper_supply_chain_shock_score
hyper_commodity_exposure_score
hyper_sentiment_topic_heat
hyper_fund_holding_crowding
hyper_dynamic_comovement_score
hyper_neighbor_return_1d
hyper_neighbor_sentiment_5d
hyper_neighbor_volume_surprise_5d
```

### 9.4 事件衰减特征

事件影响会衰减。

```text
decayed_event_score(t) =
  sum_i event_score_i * exp(-(t - event_time_i) / half_life)
```

不同事件半衰期不同：

| 事件 | 半衰期 |
| --- | --- |
| 突发新闻 | 1-3 天 |
| 政策文件 | 5-60 天 |
| 财报公告 | 5-20 天 |
| 地缘冲突 | 5-120 天 |
| 气候灾害 | 3-30 天 |
| 产业趋势 | 20-250 天 |

### 9.5 事件新颖度特征

市场最关心“超预期”。

```text
novelty = 1 - similarity(current_event, recent_event_cluster)
```

同样一句话，如果市场已经反复交易过，价值会下降。

特征：

```text
event_novelty
topic_novelty
entity_news_surprise
sentiment_change
heat_change
risk_change
```

### 9.6 事件分歧度特征

分歧可能比平均情绪更有用。

```text
sentiment_std
source_disagreement
analyst_disagreement
social_media_polarization
news_vs_market_divergence
```

例子：

```text
新闻强利好，但股价不涨 -> 可能低于预期
新闻一般，但成交和热度突然放大 -> 可能有未充分反映的信息
```

## 10. 训练目标怎么设计

### 10.1 不建议预测绝对价格

不建议：

```text
预测明天收盘价是多少
```

更建议：

```text
预测未来 N 日横截面超额收益排名
```

例如：

```text
label_1d = Ref($close, -2) / Ref($close, -1) - 1
label_5d = Ref($close, -6) / Ref($close, -1) - 1
label_10d = Ref($close, -11) / Ref($close, -1) - 1
```

再做行业/市值/风格中性化：

```text
excess_return = stock_return - industry_return
```

### 10.2 推荐多 horizon

事件影响有不同时间尺度：

| Horizon | 适合事件 |
| --- | --- |
| 1 天 | 舆情、突发新闻、龙虎榜、隔夜海外 |
| 3-5 天 | 政策、行业新闻、资金流 |
| 10-20 天 | 财报、产业趋势、商品价格 |
| 60 天以上 | 宏观、政策周期、地缘长期影响 |

建议同时训练：

```text
1d rank
5d rank
20d rank
```

然后比较不同事件特征在哪个 horizon 最有效。

### 10.3 推荐先做横截面排序

模型目标：

```text
每天给全市场/沪深300/中证500/中证1000股票打分
买 top quantile
卖/避开 bottom quantile
```

评估：

```text
Rank IC
ICIR
Top-bottom return
Annual return
Sharpe
Max drawdown
Turnover
Cost-adjusted return
Industry exposure
Size exposure
```

## 11. 评估方式：必须用消融证明数据有效

你要研究“数据比模型重要”，就必须做数据消融。

### 11.1 基线实验

```text
Baseline A: Alpha158 + LightGBM
Baseline B: Alpha360 + LightGBM
Baseline C: price/volume only
Baseline D: industry neutral baseline
```

### 11.2 数据增量实验

```text
Baseline
+ news sentiment
+ structured events
+ macro
+ geopolitical
+ climate
+ policy
+ graph relation
+ hypergraph relation
+ dynamic hypergraph relation
```

每次只加一组，观察增量。

### 11.3 模型增量实验

```text
LightGBM
LightGBM + hypergraph features
MLP
Transformer
GNN
Hypergraph NN
MoE / regime gating
```

如果复杂模型没有明显超过 LightGBM，说明还不是上复杂模型的时候。

### 11.4 时间切片实验

必须分市场环境：

```text
牛市
熊市
震荡市
高波动
低波动
政策密集期
地缘冲突期
商品大行情
成长风格
价值风格
```

很多事件数据只在特定时期有效。平均结果不明显，不代表没价值。

### 11.5 反泄漏检查

检查清单：

- 使用公告实际披露时间，而不是报告期。
- 使用指数/行业历史成分，而不是当前成分。
- 使用历史概念成分，避免事后概念归因。
- 使用新闻首发时间和可见时间。
- 使用宏观数据首次发布日期和修订版本。
- 使用基金持仓披露时间，而不是持仓截止日。
- 使用停牌、涨跌停、交易成本和滑点。
- 不把未来实体关系回填到过去。

## 12. 当前业界/学术主流在研究什么

截至 2026-04-24，和你方向最相关的主流趋势包括：

### 12.1 金融 LLM 从“问答”走向“数据工程”

BloombergGPT 证明了金融领域大模型需要大规模金融语料和领域数据。FinGPT 强调数据中心化、自动数据整理、轻量适配。这与你的判断一致：金融 LLM 的护城河不是简单模型结构，而是高质量、时效性强、领域化的数据。

### 12.2 LLM 更多作为特征抽取器，而不是直接交易员

目前更稳的用法：

```text
LLM -> 事件抽取/情绪打分/影响方向/实体链接/摘要/RAG
```

不稳的用法：

```text
LLM -> 直接预测明天买哪只股票
```

LLM 适合把非结构化世界转成结构化信号，再交给量化模型回测。

### 12.3 多源异构融合持续升温

研究越来越多地融合：

- 价格
- 基本面
- 新闻
- 社交媒体
- 图关系
- 宏观
- 市场状态

核心挑战是：

- 模态对齐
- 缺失模态
- 噪声控制
- 时效对齐
- 不同市场泛化
- 可解释性

### 12.4 图和超图越来越重要

股票不是独立样本。行业、供应链、共同持仓、市场共振、事件扩散都要求关系建模。

普通 GNN 已经比较常见，超图和动态超图更适合你的“全事件影响网络”想法。

### 12.5 宏观/地缘/政策事件正在被 AI 化

GPR、EPU、GDELT 这类数据说明，用新闻构建宏观和地缘风险指标已经成熟。AI-GPR 进一步用 LLM 读取新闻并生成地缘风险强度，说明“LLM 事件风险指数”是明确趋势。

### 12.6 真正稀缺的是 A 股本土化事件数据

美股英文数据很多，A 股真正难的是：

- 中文金融实体链接
- 政策文本理解
- 产业链映射
- 概念题材历史版本
- 社交舆情噪声处理
- 涨跌停和交易制度处理
- 北向/融资/龙虎榜等本土资金数据

这也是你的机会。

## 13. 最推荐的具体研究方向

我建议你不要分散精力研究所有模型，而是把方向定为：

```text
A 股事件-超图 Alpha 引擎
```

全称可以是：

```text
Event-Hypergraph Alpha Engine for China A-shares
```

核心问题：

> 如何把全球事件、中文新闻、政策、舆情、宏观、产业链和市场行为，转成 point-in-time 的事件超图，并证明它能提升 A 股横截面收益预测？

### 13.1 为什么这个方向最好

原因：

- 和你的 NLP/LLM 背景高度匹配。
- 和 Qlib 的横截面回测框架匹配。
- 有清晰学术前沿：event-driven、knowledge graph、heterogeneous graph、hypergraph、LLM financial NLP。
- 有清晰工程壁垒：数据、实体链接、时间对齐、事件 schema。
- 不依赖你从零发明模型。
- 可以从 LightGBM 小步验证，逐步升级到超图神经网络。
- A 股本土化数据有差异化价值。

### 13.2 最小可行研究问题

不要一开始做“所有世界信息”。先做一个明确问题：

```text
结构化事件和超图扩散特征，是否能在 Alpha158/Alpha360 之外提升 A 股 Rank IC？
```

如果答案是肯定的，再扩展。

### 13.3 第一篇可做的实验题目

可以设定为：

```text
基于 LLM 事件抽取与动态超图扩散的 A 股横截面收益预测
```

研究对象：

- 沪深300
- 中证500
- 中证1000
- 全 A 股可交易股票

预测目标：

- 未来 1 日、5 日、20 日横截面超额收益排名

基线：

- Alpha158 + LightGBM
- Alpha360 + LightGBM
- Transformer/MLP

新增模块：

- LLM 事件抽取
- 事件实体链接
- 事件影响超图
- 行业/概念/供应链超图
- 超图邻居聚合特征

核心指标：

- Rank IC uplift
- ICIR uplift
- top-bottom return uplift
- cost-adjusted Sharpe
- max drawdown
- turnover
- neutralized performance

## 14. 分阶段路线

### 阶段 0：先不要上复杂模型

时间：1-2 周

目标：

- 搭好研究评价框架。
- 固定数据切分。
- 固定基线模型。
- 固定评估指标。

产出：

```text
Baseline leaderboard:
  Alpha158 + LightGBM
  Alpha360 + LightGBM
  market/industry/size neutral metrics
```

没有这个基线，后面所有研究都无法判断是否有效。

### 阶段 1：做事件数据表

时间：2-4 周

先选一种数据源：

- 财经新闻
- 公告
- 政策新闻
- GDELT 全球事件
- 新闻 RSS

建立事件表：

```text
event_id
publish_time
visible_time
event_type
event_subtype
entities
affected_industries
affected_stocks
sentiment
risk_score
novelty
confidence
source
```

第一版不追求完美，但必须能回测。

### 阶段 2：事件特征进入 LightGBM

时间：2-4 周

把事件聚合为 `date x stock` 特征：

```text
event_count_1d/5d/20d
sentiment_mean_5d
risk_score_max_20d
policy_support_score_20d
negative_event_count_5d
news_heat_change_5d
```

跑：

```text
Alpha158
Alpha158 + event features
```

判断是否有增量。

### 阶段 3：加入关系扩散

时间：1-2 个月

先做普通图：

```text
行业邻居事件均值
概念邻居事件均值
供应链邻居事件均值
商品暴露邻居事件均值
```

再做超图：

```text
同一事件超边内其他股票的收益/情绪/热度
同一主题超边内其他股票的异常成交
同一供应链超边内上游/下游事件冲击
```

目标：

```text
证明“关系传播”比“个股自身事件”有增量。
```

### 阶段 4：动态超图模型

时间：2-3 个月

当超图特征有效后，再做模型：

```text
Temporal Encoder:
  GRU / Transformer / TCN

Hypergraph Encoder:
  Hypergraph Convolution / Hypergraph Attention

Fusion:
  attention / gate / MoE

Output:
  cross-sectional rank score
```

这个阶段再参考 DHSTN、TD-HCN、HGTAN 等方法。

### 阶段 5：LLM 事件基础模型

时间：长期

当你积累足够事件数据后，做预训练：

```text
event embedding
entity-event alignment
event impact prediction
hyperedge completion
masked affected entity prediction
```

这才是“大一统金融事件模型”的方向。

## 15. 最小实现架构

建议先这样落地：

```text
data/raw/
  news/
  announcements/
  macro/
  gdelt/

data/intermediate/
  events.parquet
  entities.parquet
  event_entity_links.parquet
  hyperedges.parquet

data/features/
  event_features.parquet
  hypergraph_features.parquet

qlib workflow:
  DataHandler
  DatasetH
  LightGBMModel
  Recorder
  Backtest
```

事件表：

```text
events
  event_id
  publish_time
  visible_time
  event_type
  event_subtype
  title
  summary
  sentiment
  risk_score
  novelty
  uncertainty
  confidence
  source
```

实体链接表：

```text
event_entity_links
  event_id
  entity_id
  entity_type
  relation_type
  impact_direction
  impact_strength
  confidence
```

超边表：

```text
hyperedges
  hyperedge_id
  hyperedge_type
  timestamp
  visible_time
  node_ids
  node_types
  weight
  direction
  decay_half_life
  source
```

特征表：

```text
features
  datetime
  instrument
  feature_name
  feature_value
```

## 16. 具体实验设计

### 16.1 实验 1：事件自身是否有用

```text
模型 A: Alpha158
模型 B: Alpha158 + event_count/sentiment/risk/novelty
```

如果 B 没有提升，不要急着上超图，先检查：

- 事件时间是否对齐。
- 实体链接是否准确。
- 情绪方向是否可靠。
- 事件是否过度重复。
- 标签 horizon 是否合适。

### 16.2 实验 2：关系扩散是否有用

```text
模型 A: Alpha158 + own_event_features
模型 B: Alpha158 + own_event_features + industry_event_features
模型 C: Alpha158 + own_event_features + concept_event_features
模型 D: Alpha158 + own_event_features + supply_chain_event_features
模型 E: Alpha158 + own_event_features + hypergraph_event_features
```

目标：

```text
证明超图扩散 > 简单行业聚合。
```

### 16.3 实验 3：事件类型差异

按事件类型分别测试：

```text
policy
earnings
geopolitical
climate
commodity
regulatory
sentiment
fund_flow
```

你会发现不同事件有不同 horizon。

### 16.4 实验 4：市场状态差异

```text
高波动 vs 低波动
牛市 vs 熊市
大盘风格 vs 小盘风格
政策密集期 vs 普通时期
风险偏好上行 vs 下行
```

如果某类事件只在某状态有效，就适合进入 gating model。

### 16.5 实验 5：反事实/安慰剂测试

为了证明不是伪相关：

```text
随机打乱事件日期
随机打乱股票实体链接
随机打乱超边成员
使用未来事件做 sanity check
只保留高置信事件
只保留首发新闻
去掉重复转载新闻
```

如果真实事件有效，随机打乱后效果应该明显下降。

## 17. 这个方向的优势和风险

### 17.1 优势

- 数据护城河强。
- 和 LLM/NLP 能力匹配。
- 研究问题清晰。
- 可从简单模型验证。
- 可扩展到复杂模型。
- 有 A 股本土特色。
- 容易形成长期系统，而不是一次性策略。

### 17.2 风险

- 数据工程量很大。
- 事件抽取错误会污染特征。
- 实体链接是硬骨头。
- 事件影响方向很难判断。
- 极端事件样本少，容易过拟合。
- 舆情数据噪声很大。
- 历史概念和供应链数据容易未来泄漏。
- 回测提升不等于实盘可交易。

### 17.3 最大风险

最大风险不是模型不够强，而是：

```text
你以为模型在学习事件影响，
实际上它在学习未来数据、重复新闻、行业暴露或幸存者偏差。
```

所以一定要把数据时间轴和消融实验放在第一优先级。

## 18. 不建议做的事情

### 18.1 不要直接让 LLM 预测股票

不建议：

```text
把新闻贴给 LLM，问它明天哪只股票涨。
```

原因：

- 不可稳定回测。
- 容易受提示词影响。
- 输出不一致。
- 不容易处理交易成本和风险暴露。
- 很难判断信息泄漏。

建议：

```text
LLM 负责结构化事件，量化模型负责预测和回测。
```

### 18.2 不要一开始做全市场所有数据

不要一开始就收集所有东西。

更好的顺序：

```text
先选一个事件类别
  -> 做干净
  -> 证明有效
  -> 再扩展
```

例如先做：

```text
政策事件 + 行业/概念超图 + LightGBM
```

或者：

```text
全球地缘/商品事件 + 商品暴露超图 + 周期股预测
```

### 18.3 不要过早训练金融基础模型

预训练很诱人，但前提是：

- 事件数据足够大。
- 事件 schema 稳定。
- 实体链接质量高。
- 下游任务已经证明事件有用。

否则就是成本很高的自嗨工程。

## 19. 我给你的最终建议

你的方向可以收敛为：

```text
数据中心化的 A 股事件-超图预测系统
```

最值得先做的是：

```text
用 LLM 把新闻/政策/宏观/全球事件转成结构化事件；
用实体链接把事件映射到 A 股公司、行业、概念、商品和地区；
用超图表达“一件事影响一组对象”的高阶关系；
把事件和超图聚合成 point-in-time 特征；
先用 LightGBM 在 Qlib 中证明增量收益；
再逐步升级到动态超图神经网络和 MoE。
```

具体路线：

1. 固定 Qlib 基线：Alpha158/Alpha360 + LightGBM。
2. 建事件表：先做政策/新闻/公告中的一种。
3. 建实体链接：新闻实体 -> A 股股票/行业/概念。
4. 建超图：行业、概念、事件影响、供应链、商品暴露。
5. 做事件特征和超图聚合特征。
6. 跑消融：证明事件数据和超图关系有增量。
7. 再上动态超图模型。
8. 最后才考虑金融事件基础模型。

我的判断是：

> 未来 2-3 年，金融预测里最有潜力的不是再发明一个普通时序模型，而是建立高质量 point-in-time 多源事件数据，并用图/超图表达事件传导关系。模型可以逐步升级，但数据和关系表达会成为真正壁垒。

## 20. 参考资料

以下是本报告检索和参考的代表性资料：

- GDELT Project：全球事件、语言和情绪数据库，覆盖全球新闻并持续更新。https://www.gdeltproject.org/
- GDELT Cloud 文档：结构化 Events、Stories、Entities、API 等。https://docs.gdeltcloud.com/
- Caldara & Iacoviello, **Measuring Geopolitical Risk**, American Economic Review, 2022。https://www.aeaweb.org/articles?id=10.1257/aer.20191823
- Baker, Bloom & Davis, **Measuring Economic Policy Uncertainty**, NBER, 2015。https://www.nber.org/papers/w21633
- AI-GPR Index：用 LLM 生成日频地缘政治风险指数。https://www.matteoiacoviello.com/ai_gpr.html
- Ding et al., **Deep Learning for Event-Driven Stock Prediction**, IJCAI 2015。https://ocs.aaai.org/ocs/index.php/IJCAI/IJCAI15/paper/viewPaper/11031
- Ding et al., **Knowledge-Driven Event Embedding for Stock Prediction**, COLING 2016。https://aclanthology.org/C16-1201/
- Darwish et al., **Stock Market Forecasting: From Traditional Predictive Models to Large Language Models**, Computational Economics, 2025。https://link.springer.com/article/10.1007/s10614-025-11024-w
- Wu et al., **BloombergGPT: A Large Language Model for Finance**, arXiv, 2023。https://arxiv.org/abs/2303.17564
- Yang et al., **FinGPT: Open-Source Financial Large Language Models**, arXiv, 2023/2025 revision。https://arxiv.org/abs/2306.06031
- Araci, **FinBERT: Financial Sentiment Analysis with Pre-trained Language Models**, arXiv, 2019。https://arxiv.org/abs/1908.10063
- Chen et al., **Leveraging large language model as news sentiment predictor in stock markets**, Discover Computing, 2025。https://link.springer.com/article/10.1007/s10791-025-09573-7
- Xiong et al., **Heterogeneous graph knowledge enhanced stock market prediction**, AI Open, 2021。https://www.sciencedirect.com/science/article/pii/S2666651021000243
- Li et al., **A graph neural network-based stock forecasting method utilizing multi-source heterogeneous data fusion**, Multimedia Tools and Applications, 2022。https://pubmed.ncbi.nlm.nih.gov/35668823/
- Liao et al., **Stock trend prediction based on dynamic hypergraph spatio-temporal network**, Applied Soft Computing, 2024。https://www.sciencedirect.com/science/article/abs/pii/S1568494624001030
- Cui et al., **Temporal-Relational Hypergraph Tri-Attention Networks for Stock Trend Prediction**, arXiv/RePEc, 2021/2022。https://ideas.repec.org/p/arx/papers/2107.14033.html
- Fang et al., **TD-HCN: A trend-driven hypergraph convolutional network for stock return prediction**, Neural Networks, 2025。https://www.sciencedirect.com/science/article/abs/pii/S0893608025006094
- Yi et al., **Robust stock trend prediction via volatility detection and hierarchical multi-relational hypergraph attention**, Knowledge-Based Systems, 2025。https://www.sciencedirect.com/science/article/abs/pii/S0950705125013243
- Zhang et al., **A multifactor model using large language models and multimodal investor sentiment**, International Review of Economics & Finance, 2025。https://www.sciencedirect.com/science/article/pii/S1059056025004447

