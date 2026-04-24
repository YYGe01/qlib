# 从今天开始构建 Point-in-Time A 股多源实时数据系统

> 面向个人量化研究者的长期实施方案  
> 更新时间：2026-04-24  
> 目标：从现在开始持续、自动、可审计地收集 A 股相关结构化与非结构化信息，避免历史数据未来函数，逐步训练和迭代事件/超图/排序模型。  
> 免责声明：本文是工程与研究方案，不构成投资建议；涉及爬虫和数据使用时，应遵守网站服务条款、robots 协议、版权限制和数据供应商授权。

## 0. 最终结论

你的思路**可行，而且对个人研究者很现实**：

> 不再强行拼接无法验证 point-in-time 的历史新闻、舆情、宏观、事件数据，而是从今天开始建立一个完全由自己采集、自己留痕、自己审计的实时数据账本。

这条路线的最大价值不是短期立刻赚钱，而是建立长期数据资产：

```text
从今天开始持续采集
  -> 每条数据记录 first_seen_at / visible_time
  -> 原始内容不可变保存
  -> 每日生成 point-in-time 特征
  -> 每日生成未来标签
  -> 每月/每季滚动训练
  -> 每次模型只使用当时已看到的数据
```

这样做可以最大程度避免：

- 新闻历史回填导致未来函数
- 财报/公告按报告期误用
- 宏观数据修订泄漏
- 概念板块事后归因
- 产业链关系事后整理
- 舆情热度事后采样
- 事件影响事后解释

但也要接受几个现实：

1. **几个月数据不足以训练复杂大模型**。几个月可以训练 LightGBM、线性排序、简单融合模型，并验证事件特征是否有增量。
2. **个人无法低成本覆盖“全世界所有信息”**。正确做法是分层覆盖，先抓高信噪比、低合规风险、低成本的数据源。
3. **实时不是越高频越好**。如果你做日频/隔夜/数日持有策略，1 分钟行情、5-15 分钟新闻轮询、盘后统一特征快照已经足够起步。
4. **数据工程比模型更重要**。最核心的是 append-only 原始数据湖、时间账本、数据血缘、可回放特征生成，而不是一开始上复杂模型。
5. **未来价值很大**。如果连续采集 1-3 年，你将拥有个人很难买到的干净事件-市场联动数据集，这是研究事件驱动、超图关系、动态市场状态的核心资产。

我建议把这个长期项目命名为：

```text
PIT-AShare Event Lake
```

或者：

```text
A 股 Point-in-Time 多源事件数据湖
```

更准确地说，这个长期项目应该拆成两个互相独立的系统：

```text
系统 A：数据收集层
  目标：长期、稳定、低假设、不可变地保存当时看到的原始事实。
  特点：永远有用，尽量不绑定任何模型、事件 schema、特征工程方法。

系统 B：后处理/研究层
  目标：基于数据收集层反复重算事件、实体、超图、特征、模型和策略。
  特点：随时可以推倒重来，允许今天用规则，明天用 LLM，后天用更强的多模态/超图方法。
```

这是整份方案最重要的工程原则：

> 数据收集层要像“不可变事实金库”，后处理层要像“可替换研究实验室”。

不要让某一版 LLM prompt、某一版事件分类、某一版超图关系、某一版模型结构决定你原始数据怎么存。原始数据只负责回答：

```text
我在什么时候，从哪里，看到了什么，原文是什么，原始响应是什么。
```

后处理层才负责回答：

```text
这条信息意味着什么，影响谁，如何结构化，如何生成特征，如何训练模型。
```

## 1. 你这个思路为什么有价值

### 1.1 个人量化最大的问题不是没有模型

现在有大模型、有开源框架、有 Qlib、有 LightGBM、有各种深度学习模型。个人真正难的是：

- 没有干净数据。
- 没有真实发布时间。
- 没有长期可回放的数据快照。
- 不知道某条信息在当时是否已经可见。
- 不知道数据是否被后来修订。
- 很难证明模型不是学到了未来函数。

所以，你提出“从今天开始自己采集”的思路，本质上是在解决个人量化最致命的问题：

```text
数据可信度 > 模型复杂度
```

### 1.2 从今天开始采集，是最干净的 point-in-time 方案

历史数据最大的问题是：

```text
你拿到的是现在数据库里的历史版本，不一定是历史当时可见的版本。
```

例如：

- 某公司 2023 年财报数据，数据库里是修订后的最终值。
- 某公告按报告期归档，但实际披露在几个月后。
- 某概念板块是在 2025 年热门后才回填到过去。
- 某新闻库后来清洗合并了重复新闻，丢失了首发时间。
- 某宏观指标后来修订，原始初值已不可得。
- 某事件影响行业是事后分析师总结，不代表当时市场认知。

你从今天起采集，则可以做到：

```text
我什么时候看到的
我当时看到的原文是什么
我当时解析出了什么事件
我当时生成了什么特征
我当时模型做出了什么预测
```

这就是量化研究里最重要的可审计性。

### 1.3 这不是放弃历史，而是拒绝不可信历史

你可以把数据分成三类：

| 类型 | 是否建议用 | 用法 |
| --- | --- | --- |
| 自己从今天起采集的数据 | 强烈建议 | 主研究数据，最干净 |
| 官方可验证发布时间的历史数据 | 可以谨慎用 | 只用于市场行情/公告/财报等可审计数据 |
| 无法验证当时可见性的历史新闻/舆情/概念/产业链 | 不建议直接训练 | 可以做预训练、词表、实体库、先验关系，不做监督标签训练 |

也就是说，不是所有历史都不能用，而是：

> 不能把不可信历史当成 point-in-time 监督训练数据。

## 2. 可行性评估

### 2.1 总体可行

个人可以做成以下范围：

```text
日频/分钟级行情
官方公告
交易所/监管政策
财经新闻/RSS/GDELT
商品期货/大宗商品价格
宏观数据发布
全球市场指数
天气/灾害/地缘风险数据
有限舆情数据
行业/概念/供应链半自动维护
LLM 事件抽取
超图关系构建
Qlib 回测与滚动训练
```

个人不适合一开始做：

```text
全市场 Level-2 高频数据
全网社交媒体实时舆情
全量付费新闻源全文
所有研报和电话会纪要
全球供应链实时数据库
毫秒级交易策略
从零训练金融大模型
```

### 2.2 最现实的策略周期

如果你是个人，我建议先做：

```text
盘后/隔夜决策
T 日收盘后生成特征
预测 T+1 到 T+5 的横截面收益
每日或每周调仓
```

原因：

- 对实时性要求低。
- 对数据延迟容忍度高。
- 更容易避免未来函数。
- 更适合 Qlib。
- 更适合事件和新闻的滞后影响。
- 更适合个人算力和数据成本。

不建议一开始做：

```text
盘中秒级事件交易
高频盘口预测
新闻毫秒级套利
```

这些需要专业实时行情、低延迟链路和更高数据授权成本。

### 2.3 几个月后能训练什么

假设你覆盖 5000 只 A 股，采集 3 个月，约 60 个交易日：

```text
样本行数 = 5000 * 60 = 300000
```

看起来很多，但要注意：

- 时间维度只有 60 天。
- 市场状态可能很单一。
- 事件类型不均衡。
- 20 日标签只有约 40 个有效交易日。
- 极端事件样本非常少。
- 横截面样本高度相关，不等于 30 万个独立样本。

所以 3 个月适合：

```text
训练 LightGBM / Ridge / Logistic Ranker
做特征消融
验证数据链路
做 paper trading
```

不适合：

```text
训练大型 Transformer
训练复杂超图神经网络
下结论某类地缘事件长期有效
实盘重仓
```

更合理的节奏：

| 时间 | 能做什么 |
| --- | --- |
| 0-1 个月 | 搭采集系统、数据湖、基线、监控 |
| 1-3 个月 | 做事件特征、LightGBM 小实验、paper trading |
| 3-6 个月 | 做滚动训练、特征消融、行业/概念超图 |
| 6-12 个月 | 做动态超图、市场状态分层、初步策略组合 |
| 1-3 年 | 研究地缘/气候/宏观等低频事件 |
| 3 年以上 | 做真正有价值的事件基础模型/世界模型 |

## 3. 总体架构

建议设计成 10 层：

```text
Layer 0: Source Registry
Layer 1: Raw Append-Only Data Lake
Layer 2: Crawl Ledger
Layer 3: Normalized Data Tables
Layer 4: Entity Master
Layer 5: Event Extraction
Layer 6: Entity Linking
Layer 7: Graph / Hypergraph
Layer 8: Point-in-Time Feature Store
Layer 9: Model Training / Backtest / Paper Trading
Layer 10: Monitoring / Audit / Backup
```

核心原则：

```text
原始数据永不覆盖
解析结果可以重算
特征必须按 cutoff_time 生成
模型只能看到 cutoff_time 之前 first_seen 的数据
所有数据都有来源、时间、版本、哈希
```

### 3.0 先拆成两条管线

从工程上不要把“采集”和“后处理”写成一条强耦合流水线，而要拆成两条管线。

#### 管线 A：数据收集层

数据收集层只做事实保存：

```text
Source Registry
  -> Crawler / Connector
  -> Crawl Ledger
  -> Raw Append-Only Data Lake
  -> Minimal Normalization
  -> Collection Manifest
```

它的职责：

- 发现数据源。
- 定时访问数据源。
- 保存原始响应、原始文件、原始字段。
- 记录 first_seen_at、crawl_time、source_publish_time。
- 做最小必要去重。
- 记录哈希、请求参数、响应状态。
- 保存数据源授权、robots、访问频率。
- 生成每日采集质量报告。

它不应该负责：

- 判断新闻利好还是利空。
- 判断事件影响哪些股票。
- 生成复杂事件 schema。
- 构建超图。
- 生成模型特征。
- 做训练和回测。

原因很简单：

> 采集层的目标是让数据资产长期有效，不要被当前研究方法污染。

#### 管线 B：后处理/研究层

后处理层从采集层读取数据，再反复加工：

```text
Raw Data Lake
  -> Parser / OCR / Cleaner
  -> LLM Event Extractor
  -> Entity Linking
  -> Graph / Hypergraph Builder
  -> PIT Feature Generator
  -> Model Training
  -> Backtest / Paper Trading
```

它的职责：

- 解析网页、PDF、JSON、CSV。
- 抽取事件。
- 做实体识别和实体链接。
- 构建普通图、异构图、超图。
- 生成 point-in-time 特征。
- 训练模型。
- 回测和模拟交易。
- 做消融实验。

它必须满足：

```text
所有产物都可以从采集层原始数据重算。
所有产物都有 processor_version / prompt_version / model_version。
任何后处理结果都不能覆盖原始数据。
```

#### 两条管线的关系

```text
数据收集层：稳定、保守、少假设、长期积累
后处理层：激进、可变、可实验、持续升级
```

你可以今天用简单规则抽事件，明天换成 FinBERT，后天换成金融 LLM，再之后换成多模态模型。只要原始数据收集层干净，后处理方法可以无限迭代。

### 3.1 架构图

```text
                         +--------------------+
                         | Source Registry    |
                         | 数据源清单/频率/授权 |
                         +---------+----------+
                                   |
                                   v
+-----------+     +-------------------------------+     +------------------+
| Scheduler | --> | Crawlers / Connectors          | --> | Crawl Ledger     |
| 定时任务    |     | 行情/公告/新闻/政策/宏观/天气     |     | 每次请求留痕       |
+-----------+     +-------------------------------+     +------------------+
                                   |
                                   v
                         +--------------------+
                         | Raw Data Lake      |
                         | append-only 原文保存 |
                         +---------+----------+
                                   |
                                   v
                         +--------------------+
                         | Minimal Normalizer |
                         | 最小标准化/不做语义判断 |
                         +---------+----------+
                                   |
                                   v
             +---------------------+---------------------+
             |                                           |
             v                                           v
   +--------------------+                      +--------------------+
   | Structured Tables  |                      | Text Documents     |
   | 行情/宏观/商品       |                      | 新闻/公告/政策/舆情   |
   +---------+----------+                      +---------+----------+
             |                                           |
             v                                           v
   +--------------------+                      +--------------------+
   | Collection Vault   |                      | Collection Manifest|
   | 采集层稳定资产       |                      | 数据版本/血缘/质量     |
   +---------+----------+                      +---------+----------+
             |                                           |
             +---------------------+---------------------+
                                   |
                                   v
                         +--------------------+
                         | Post-processing    |
                         | 可替换研究管线       |
                         +---------+----------+
                                   |
                                   v
   +--------------------+                      +--------------------+
   | Entity Master      | <------------------- | LLM Event Extractor |
   | 股票/公司/行业/商品   |                      | 事件/情绪/风险/主题    |
   +---------+----------+                      +---------+----------+
             |                                           |
             +---------------------+---------------------+
                                   v
                         +--------------------+
                         | Event-Hypergraph   |
                         | 事件/实体/超边       |
                         +---------+----------+
                                   |
                                   v
                         +--------------------+
                         | PIT Feature Store  |
                         | date x instrument  |
                         +---------+----------+
                                   |
                                   v
                         +--------------------+
                         | Qlib / Models      |
                         | 训练/回测/模拟交易    |
                         +--------------------+
```

## 4. 第一优先级：时间账本

### 4.1 每条数据必须有 8 个时间

建议所有原始数据都尽量记录：

```text
source_event_time    事件实际发生时间
source_publish_time  来源声称的发布时间
source_update_time   来源声称的更新时间
crawl_start_time     你的爬虫开始请求时间
crawl_end_time       你的爬虫拿到响应时间
first_seen_at        你的系统第一次看到该内容的时间
visible_time         你允许模型使用该内容的最早时间
stored_at            写入数据库/对象存储时间
```

其中最关键的是：

```text
first_seen_at
visible_time
```

### 4.2 first_seen_at 和 visible_time 的区别

`first_seen_at`：

```text
你的系统第一次采集到这条信息的时间。
```

`visible_time`：

```text
模型可以使用这条信息的时间。
```

有些数据采集到后不能立即用：

- PDF 公告需要解析。
- 新闻需要去重。
- LLM 需要抽取事件。
- 宏观数据需要确认发布日期。
- 盘中消息可能只能用于盘后模型。

所以可以定义：

```text
visible_time = max(first_seen_at, parse_completed_at, source_publish_time)
```

如果你做盘后策略，还可以更严格：

```text
visible_trade_date = next_decision_cut_after(visible_time)
```

### 4.3 决策切点

建议先固定几个决策切点：

```text
09:20  盘前
11:35  午盘后
15:10  收盘后
20:00  晚间公告/新闻后
23:30  海外市场/夜间事件后
```

第一阶段只做一个：

```text
每天 20:00 生成 T 日特征，预测 T+1 到 T+5
```

这样最干净。

### 4.4 永远不要覆盖历史

如果一条新闻后续更新，不要覆盖原记录。

应该新增版本：

```text
doc_id
version_id
first_seen_at
content_hash
raw_content
```

如果宏观数据修订，也新增版本：

```text
indicator_id
period
value
release_time
revision_no
first_seen_at
```

训练时按：

```text
first_seen_at <= cutoff_time
```

选择可用版本。

## 5. 数据源分层

### 5.1 P0：必须先做的数据

P0 是低成本、高价值、个人可以启动的数据。

| 数据 | 用途 | 频率 | 备注 |
| --- | --- | --- | --- |
| A 股日线/分钟行情 | 标签、价格因子、成交量 | 1-5 分钟/盘后 | 先做 1 分钟或 5 分钟即可 |
| 股票基础信息 | instrument master | 每日 | 上市、退市、停牌、名称变更 |
| 官方公告 | 公司事件 | 5-15 分钟 | 巨潮、交易所、北交所 |
| 交易所/监管新闻 | 政策/监管事件 | 15-60 分钟 | 证监会、交易所 |
| 重要部委政策 | 政策事件 | 15-60 分钟 | 国务院、发改委、工信部、财政部、央行 |
| 主要商品期货 | 商品暴露 | 1-5 分钟/盘后 | 原油、铜、铝、煤、锂、黄金等 |
| 全球市场指标 | 外部风险 | 5-60 分钟 | 美股指数、美债、美元、VIX、原油、黄金 |
| GDELT/国际新闻事件 | 全球事件 | 15-60 分钟 | 地缘、战争、灾害、政策 |
| 财经新闻 RSS/公开源 | 新闻事件 | 5-15 分钟 | 遵守授权和 robots |
| 天气/灾害 | 气候冲击 | 1-6 小时 | 天气、火灾、洪水、台风 |

### 5.2 P1：第二阶段数据

| 数据 | 用途 | 难点 |
| --- | --- | --- |
| 社交媒体舆情 | 情绪和关注度 | 合规、反爬、噪声 |
| 股吧/论坛/雪球 | 个股热度 | 授权、噪声、重复 |
| 研报标题/摘要 | 机构观点 | 版权和数据源 |
| 基金持仓 | 资金拥挤 | 披露滞后 |
| 龙虎榜 | 短线资金 | 适合短周期 |
| 融资融券 | 杠杆情绪 | 日频即可 |
| 北向资金 | 外资流 | 日频/分钟级看数据源 |
| 行业产业链 | 事件传导 | 需要人工维护/付费源 |
| 概念题材 | 主题超图 | 历史版本难 |

### 5.3 P2：长期/付费/高难数据

| 数据 | 用途 | 为什么后做 |
| --- | --- | --- |
| Level-2 行情 | 高频微观结构 | 数据贵，策略复杂 |
| 全网新闻全文 | 全局事件覆盖 | 授权和版权复杂 |
| 全量社交媒体 | 情绪舆情 | 合规和噪声难 |
| 电话会纪要 | 基本面预期 | 授权昂贵 |
| 供应链数据库 | 传导关系 | 数据贵且需维护 |
| 卫星/遥感 | 另类数据 | 工程成本高 |
| 企业招聘/招投标 | 经营变化 | 清洗难 |

## 6. 推荐数据源清单

下面是第一版源清单。实际落地时需要逐个确认接口稳定性、授权、访问频率和服务条款。

### 6.1 A 股行情

可选路线：

| 路线 | 优点 | 缺点 | 建议 |
| --- | --- | --- | --- |
| AkShare | 免费、覆盖广、上手快 | 多为非官方接口，稳定性需监控 | 个人研究可先用 |
| Tushare Pro | 接口规范、数据丰富 | 需要 token，部分权限积分/付费 | 中期可用 |
| BaoStock | 免费、适合日频历史 | 实时能力有限 | 可做补充 |
| 券商/数据商 API | 授权更清晰、实时性好 | 费用/开户/接口限制 | 实盘前优先 |
| 交易所授权行情 | 最正规 | 个人成本高 | 长期再考虑 |

第一阶段建议：

```text
AkShare/Tushare 获取盘中快照和盘后行情
同时保存每次请求的原始结果、时间戳、哈希
```

注意：

- 免费接口可能失效。
- 字段含义可能变化。
- 不要依赖单一来源。
- 行情数据要和交易日历、停牌、涨跌停对齐。

### 6.2 官方公告

优先级很高。

建议覆盖：

- 巨潮资讯网
- 上海证券交易所信息披露
- 深圳证券交易所信息披露
- 北京证券交易所信息披露

公告是个人最应该采集的数据之一：

- 官方来源。
- 时间戳明确。
- 公司级事件密度高。
- 可通过 LLM 抽取结构化事件。
- 对 A 股影响直接。

需要采集：

```text
公告标题
证券代码
证券简称
公告类别
公告日期
披露时间
PDF/HTML 原文
附件
下载时间
content_hash
```

注意：

- 公告日期不一定等于市场可见时间。
- 晚间公告一般用于下一交易日。
- PDF 解析要保存解析版本。
- 更正公告要作为新事件处理。

### 6.3 政策和监管

A 股政策驱动明显，政策数据必须做。

建议覆盖：

| 来源 | 用途 |
| --- | --- |
| 中国政府网 | 国务院政策、常务会议、重要文件 |
| 中国证监会 | 资本市场监管、处罚、政策 |
| 上交所/深交所/北交所 | 市场制度、监管动态 |
| 中国人民银行 | 货币政策、利率、社融、M2 |
| 国家统计局 | GDP、CPI、PPI、PMI、工业、消费 |
| 国家发改委 | 产业政策、价格、能源 |
| 工信部 | 制造业、科技、产业政策 |
| 财政部 | 财政政策、税收、专项资金 |
| 商务部 | 外贸、消费、制裁、出口管制 |
| 生态环境部 | 环保、碳、限产 |
| 国家能源局 | 电力、煤炭、油气、新能源 |
| 农业农村部 | 农产品、种业、养殖 |

政策事件要抽取：

```text
政策主体
政策对象
政策方向
影响行业
支持/限制/监管/处罚
力度
时间范围
地理范围
```

### 6.4 新闻和全球事件

#### GDELT

GDELT 是很适合个人起步的全球事件源：

- 覆盖全球新闻。
- 有事件、地理、主题、情绪等结构化字段。
- 可按关键词、国家、主题查询。
- 适合做地缘风险、战争冲突、灾害、国际政策、全球舆情。

建议采集：

```text
China related
Asia related
geopolitical conflict
sanction
trade war
energy
semiconductor
climate disaster
commodity
supply chain
```

GDELT 不是直接的 A 股数据，但适合做外部事件层。

#### 财经新闻

建议优先采集有 RSS 或公开列表页的来源。不要绕过付费墙，不要高频抓取受保护内容。

第一阶段可采集：

```text
标题
摘要
发布时间
URL
来源
正文片段/公开正文
关键词
```

如果版权不确定，可以只保存：

```text
URL + 标题 + 摘要 + 哈希 + 抽取出的结构化事件
```

全文只用于本地研究且不传播，也要遵守来源条款。

### 6.5 商品期货和大宗商品

A 股很多行业受商品价格影响：

- 石油
- 天然气
- 煤炭
- 铜
- 铝
- 锌
- 镍
- 锂
- 铁矿石
- 螺纹钢
- 黄金
- 白银
- 农产品

建议覆盖：

| 市场 | 用途 |
| --- | --- |
| 上海期货交易所 | 有色、贵金属、能源化工 |
| 上海国际能源交易中心 | 原油、低硫燃料油等 |
| 大连商品交易所 | 农产品、化工、铁矿等 |
| 郑州商品交易所 | 农产品、能源化工等 |
| 广州期货交易所 | 新能源金属、工业硅等 |
| 中国金融期货交易所 | 股指、国债、期权 |
| 国际市场 | WTI、Brent、LME、COMEX 等 |

个人可先做：

```text
主力合约日线
主力合约 1min/5min 快照
夜盘涨跌
近月/远月价差
期限结构
波动率
```

商品特征进入股票时，要区分：

```text
生产商受益
消费商受损
库存高低
价格传导能力
行业竞争格局
```

### 6.6 宏观数据

宏观不是高频 alpha，但对市场状态很重要。

建议采集：

```text
GDP
CPI
PPI
PMI
工业增加值
社零
固定资产投资
进出口
社融
M2
利率
汇率
财政收支
地方债
房地产销售
```

关键不是数值本身，而是：

```text
发布时间
市场预期
实际值
前值
修订值
超预期程度
```

如果拿不到市场一致预期，可以先做：

```text
actual - previous
actual percentile
rolling surprise proxy
```

### 6.7 天气和灾害

气候和自然灾害影响：

- 农业
- 电力
- 煤炭
- 水泥
- 交通
- 物流
- 保险
- 食品
- 旅游
- 港口

可用源：

- Open-Meteo
- NOAA
- NASA FIRMS 火点/火灾
- 中国天气/气象部门公开信息
- 台风路径和灾害公告

事件抽取：

```text
灾害类型
地区
强度
持续时间
影响行业
影响公司所在地/产能
```

### 6.8 舆情数据

舆情有价值，但一定要谨慎。

可采集：

```text
热度
提及量
情绪
分歧度
转发/评论/点赞
关键词共现
主题聚类
```

建议优先使用：

- 官方开放 API
- 授权数据源
- 低频公开页面
- 搜索指数/热榜类公开数据

不建议：

- 绕过登录权限
- 绕过反爬机制
- 高频抓取用户内容
- 抓取并传播大量全文

舆情最容易带来噪声和合规问题，建议 P1 阶段再做。

## 7. “从今天开始采集”的核心表设计

这一节要明确分层：

```text
7.1 - 7.6：数据收集层/主数据层
  目标：保存事实、来源、时间、版本、原始内容。
  原则：尽量稳定，长期不变。

7.7 - 7.11：后处理/研究层
  目标：保存事件、实体链接、超图、特征、标签等派生产物。
  原则：可以反复重算，必须带版本。
```

最重要的边界：

> 采集层表不能依赖后处理层表；后处理层表可以随时删除重建，但采集层表不能丢。

### 7.1 source_registry

记录所有数据源。

```sql
source_id
source_name
source_type
base_url
license_type
terms_url
robots_url
allowed_frequency
priority
enabled
owner
notes
created_at
updated_at
```

### 7.2 crawl_run

每次爬虫运行都留痕。

```sql
run_id
source_id
crawler_name
crawler_version
start_time
end_time
status
request_count
success_count
error_count
new_item_count
duplicate_count
rate_limit_hit
error_message
code_git_commit
```

### 7.3 raw_document

所有新闻、公告、政策、网页、PDF 的原始记录。

```sql
doc_id
source_id
source_url
canonical_url
title
author
source_publish_time
source_update_time
crawl_time
first_seen_at
visible_time
language
content_type
raw_storage_path
text_storage_path
content_hash
dedup_hash
status_code
parse_status
parse_version
license_note
```

### 7.4 market_snapshot

行情快照。

```sql
snapshot_id
source_id
instrument
exchange
source_timestamp
first_seen_at
visible_time
last_price
open
high
low
prev_close
volume
amount
bid1
ask1
limit_up
limit_down
halt_status
raw_storage_path
content_hash
```

### 7.5 instrument_master

股票主数据。

```sql
instrument
company_id
exchange
name
list_date
delist_date
board
industry_sw_l1
industry_sw_l2
industry_sw_l3
concepts
region
is_st
status
first_seen_at
valid_from
valid_to
source_id
```

注意：行业、概念、ST 状态都要有历史版本。

### 7.6 entity_master

实体库。

```sql
entity_id
entity_type
canonical_name
aliases
external_ids
description
first_seen_at
valid_from
valid_to
source_id
```

实体类型：

```text
stock
company
industry
concept
commodity
country
region
policy_body
person
fund
product
technology
event_topic
```

### 7.7 event_table

LLM/规则抽取后的事件。

从这里开始属于**后处理层**，不是原始采集层。`event_table` 可以随着事件分类体系、LLM、prompt、抽取规则变化而重算，所以必须保存抽取器版本。

```sql
event_id
doc_id
event_time
publish_time
first_seen_at
visible_time
event_type
event_subtype
title
summary
sentiment
risk_score
novelty
uncertainty
importance
confidence
extractor_name
extractor_version
prompt_version
model_name
created_at
```

### 7.8 event_entity_link

事件和实体的关系。

这是后处理层表。实体链接方法未来一定会升级，所以不要把它当成不可变事实；它只是在某个版本方法下的解释结果。

```sql
event_id
entity_id
entity_type
relation_type
impact_direction
impact_strength
confidence
evidence
created_at
```

关系类型：

```text
mentioned
subject
object
affected_positive
affected_negative
supplier
customer
competitor
substitute
policy_target
geography_exposure
commodity_exposure
sentiment_target
```

### 7.9 hyperedge_table

超图关系。

这是后处理层表。超图关系非常有研究价值，但它不是原始事实本身，而是对原始数据和主数据关系的一种建模方式。未来可能有更好的超图构建、权重学习、动态关系发现方法，因此必须版本化。

```sql
hyperedge_id
hyperedge_type
timestamp
first_seen_at
visible_time
node_ids
node_types
weight
direction
decay_half_life
source_type
source_id
confidence
version
```

超边类型：

```text
industry_membership
concept_membership
supply_chain_group
commodity_exposure_group
policy_impact_group
event_impact_group
fund_holding_group
geography_group
sentiment_topic_group
dynamic_comovement_group
macro_sensitivity_group
```

### 7.10 feature_snapshot

每天生成的模型特征。

这是后处理层表。特征永远是可替换的，不要把特征当成数据资产的核心；真正的核心是能重新生成特征的原始数据、时间账本和处理版本。

```sql
feature_date
cutoff_time
instrument
feature_set_name
feature_version
features_path
source_max_visible_time
generation_time
code_git_commit
data_manifest_hash
```

不要只保存最终特征值，还要保存：

```text
这批特征使用了哪些原始数据版本。
```

### 7.11 label_table

标签也必须从今天开始生成。

标签比特征更稳定，但仍然属于研究层产物，因为不同策略会定义不同收益区间、交易价格、复权方式、行业中性方式和成本假设。标签也要版本化。

```sql
label_date
instrument
label_name
horizon
start_price_time
end_price_time
return
excess_return
industry_neutral_return
created_at
```

## 8. 存储方案

### 8.1 个人推荐架构

不建议一开始上很重的分布式系统。

个人起步推荐：

```text
PostgreSQL / DuckDB / SQLite 负责元数据
Parquet 负责结构化大表
本地文件系统或 MinIO 负责原文/PDF/HTML
Git 负责代码版本
DVC 或 lakeFS 可选，负责数据版本
```

如果你想简单：

```text
metadata: SQLite 或 DuckDB
tables: Parquet
raw files: data/raw/
features: data/features/
```

如果你想更长期：

```text
metadata: PostgreSQL
time series: TimescaleDB 可选
object storage: MinIO
analytics: DuckDB
features: Parquet + Qlib
workflow: Prefect / Dagster / Airflow
```

### 8.2 目录结构

建议：

```text
data_lake/
  raw/
    source=cninfo/
      dt=2026-04-24/
        *.json
        *.pdf
    source=gdelt/
      dt=2026-04-24/
        *.json
    source=akshare_spot/
      dt=2026-04-24/
        *.json
  normalized/
    documents/
    market_snapshots/
    announcements/
    macro/
    commodities/
  collection_manifests/
    dt=2026-04-24/
      source_status.json
      raw_file_manifest.json
      crawl_quality_report.json
  postprocess/
    parser_runs/
    extractor_runs/
    entity_linking_runs/
  events/
    event_table/
    event_entity_link/
  graph/
    entity_master/
    hyperedges/
  features/
    feature_set=event_v1/
    feature_set=hypergraph_v1/
  labels/
  manifests/
  logs/
```

更推荐从第一天就按“采集资产”和“后处理产物”分开：

```text
data_lake/
  collection/
    raw/              # 原始响应、PDF、HTML、JSON、CSV，永不覆盖
    normalized_min/   # 最小标准化，只做字段和时间统一，不做语义判断
    manifests/        # 每日采集清单、哈希、数据质量
    metadata/         # source_registry、crawl_run、raw_document

  derived/
    parsed/           # 文本解析、PDF OCR、正文抽取
    events/           # 事件抽取结果
    entities/         # 实体识别和链接结果
    graph/            # 图/超图关系
    features/         # PIT 特征
    labels/           # 标签
    models/           # 模型和预测结果
```

判断一个文件应该放哪里：

```text
如果它是“当时看到的事实”，放 collection。
如果它是“后来某个方法解释出来的结果”，放 derived。
```

### 8.3 文件命名

```text
{source_id}_{crawl_time}_{content_hash}.{ext}
```

例如：

```text
cninfo_20260424T201530+0800_ab12cd34.pdf
gdelt_20260424T201500+0800_ef56aa22.json
```

## 9. 爬虫和采集系统

### 9.1 采集原则

每个 crawler 必须做到：

```text
幂等
限速
重试
超时
日志
原始响应保存
哈希去重
异常报警
不覆盖历史
```

### 9.2 推荐任务频率

第一阶段：

| 数据 | 频率 |
| --- | --- |
| A 股盘中快照 | 1-5 分钟 |
| A 股盘后日线 | 每日 16:00、20:00 |
| 公告 | 5-15 分钟 |
| 交易所/监管新闻 | 15-30 分钟 |
| 部委政策 | 30-60 分钟 |
| GDELT/国际新闻 | 15-60 分钟 |
| 财经 RSS | 5-15 分钟 |
| 商品期货 | 1-5 分钟/盘后 |
| 全球市场 | 5-30 分钟 |
| 天气灾害 | 1-6 小时 |
| 宏观数据 | 每日/按日历 |

### 9.3 不同时间级别怎么对齐

不要强行把所有数据对齐到秒级。

建议统一成：

```text
raw_time: 原始时间
visible_time: 可见时间
decision_cut: 决策时间
feature_date: 训练日期
```

例如：

```text
2026-04-24 21:15 采集到某政策新闻
visible_time = 2026-04-24 21:15
decision_cut = 2026-04-24 23:30
feature_date = 2026-04-24
用于预测 2026-04-27 或下一交易日
```

### 9.4 断点和补采

如果爬虫断了，后来补采历史数据，必须标记：

```text
is_backfilled = true
backfill_time = now()
```

训练时：

```text
如果某数据 first_seen_at > cutoff_time，则不能用于该 cutoff_time 的训练样本。
```

即使内容发布时间早，也不能使用，因为你的系统当时没看到。

## 10. LLM 事件抽取

### 10.1 LLM 的正确角色

LLM 不应该直接预测股票涨跌。

LLM 应该做：

```text
文本清洗
事件抽取
实体识别
实体链接候选
情绪判断
影响方向判断
风险评分
主题归类
摘要
证据句提取
```

然后把结构化结果交给量化模型。

### 10.2 事件 JSON Schema

建议固定输出：

```json
{
  "event_type": "policy",
  "event_subtype": "industry_support",
  "event_time": "2026-04-24T20:15:00+08:00",
  "summary": "某部门发布支持新能源产业链政策",
  "entities": [
    {
      "name": "新能源",
      "entity_type": "industry",
      "relation": "policy_target",
      "impact_direction": "positive",
      "impact_strength": 0.76,
      "confidence": 0.82
    }
  ],
  "sentiment": 0.68,
  "risk_score": 0.12,
  "novelty": 0.54,
  "uncertainty": 0.31,
  "importance": 0.72,
  "evidence": [
    "政策文件中提到..."
  ]
}
```

### 10.3 抽取质量控制

每个事件都要有：

```text
confidence
evidence
extractor_version
prompt_version
model_name
```

建议做三层校验：

1. JSON schema 校验。
2. 实体库匹配校验。
3. 规则校验，例如情绪和影响方向不能自相矛盾。

低置信事件不删除，打标：

```text
confidence < 0.5 -> low_confidence
```

训练时可以比较：

```text
all events
high confidence only
source reliable only
```

### 10.4 事件类型初版

建议先覆盖：

```text
company_announcement
earnings
merger_acquisition
shareholder_change
buyback
reduction
regulatory_penalty
policy_support
policy_restriction
industry_policy
geopolitical_conflict
sanction
trade_policy
commodity_price_shock
climate_disaster
macro_release
fund_flow
sentiment_spike
technology_breakthrough
supply_chain_disruption
```

## 11. 实体链接与 A 股映射

### 11.1 为什么实体链接最重要

新闻本身不能交易，股票代码才能交易。

你需要把：

```text
新闻/政策/事件
```

映射到：

```text
股票
行业
概念
商品
地区
供应链
宏观暴露
```

### 11.2 实体链接流程

```text
文本实体识别
  -> 别名匹配
  -> 公司/股票候选
  -> 行业/概念/产品扩展
  -> LLM 或 reranker 消歧
  -> 置信度打分
  -> 人工抽查
```

### 11.3 别名库

必须维护：

```text
股票简称
公司全称
曾用名
品牌名
产品名
英文名
控股股东
子公司
常见错别字
行业别名
概念别名
商品别名
```

例子：

```text
“宁德”
  -> 可能是 宁德时代
  -> 也可能是福建宁德地区
```

所以要结合上下文消歧。

## 12. 超图关系从第一天就要设计

你前面提到超图关系，这里仍然是核心。

### 12.1 从今天采集的数据如何生成超图

普通图表达：

```text
公司 A -> 属于 -> 行业 X
公司 A -> 使用 -> 商品 Y
公司 A -> 位于 -> 地区 Z
```

超图表达：

```text
事件 E 同时影响 {行业 X, 商品 Y, 公司 A, 公司 B, 地区 Z}
```

你从今天起采集的数据，天然可以生成动态超边：

```text
同一事件影响的一组股票
同一政策影响的一组行业
同一商品价格冲击影响的一组公司
同一舆情主题覆盖的一组股票
同一自然灾害影响的一组地区公司
同一国际事件影响的一组出口链企业
```

### 12.2 第一版超图不用复杂模型

先做特征，不做神经网络：

```text
某股票所在事件超边的平均情绪
某股票所在事件超边的最大风险
某股票所在商品超边的商品涨跌
某股票所在行业超边的新闻热度
某股票所在概念超边的资金共振
某股票所在供应链超边的上游冲击
```

这些都可以喂给 LightGBM。

### 12.3 超图节点

```text
stock
company
industry
concept
commodity
country
region
policy_body
event
topic
fund
macro_indicator
```

### 12.4 超图超边

```text
industry_membership
concept_membership
event_impact
policy_impact
commodity_exposure
supply_chain
region_exposure
fund_holding
sentiment_topic
dynamic_comovement
macro_sensitivity
```

### 12.5 超图特征例子

```text
hyper_event_sentiment_mean_1d
hyper_event_risk_max_5d
hyper_policy_support_sum_20d
hyper_commodity_price_change_5d
hyper_neighbor_return_mean_1d
hyper_neighbor_volume_surprise_5d
hyper_topic_heat_rank_3d
hyper_supply_chain_shock_score_10d
hyper_geopolitical_exposure_20d
hyper_climate_disaster_exposure_20d
```

## 13. Point-in-Time 特征生成

### 13.1 特征生成规则

每次生成特征时必须传入：

```text
cutoff_time
universe
feature_version
```

并且所有输入数据满足：

```text
visible_time <= cutoff_time
```

### 13.2 特征不要回填

如果今天才发现某股票属于某概念，不要把这个关系回填到过去训练。

正确做法：

```text
relationship_first_seen_at = today
```

只有今天之后的样本可使用。

### 13.3 特征 Manifest

每批特征生成后保存 manifest：

```json
{
  "feature_date": "2026-04-24",
  "cutoff_time": "2026-04-24T20:00:00+08:00",
  "feature_version": "event_hypergraph_v1",
  "data_sources": [
    {"source_id": "cninfo", "max_visible_time": "2026-04-24T19:58:00+08:00"},
    {"source_id": "gdelt", "max_visible_time": "2026-04-24T19:45:00+08:00"}
  ],
  "code_git_commit": "abc123",
  "row_count": 5200,
  "feature_count": 120
}
```

这样以后才能复盘。

## 14. 训练和回测方案

### 14.1 第一阶段模型

先用：

```text
LightGBM
Ridge
ElasticNet
Logistic ranker
CatBoost 可选
```

不要急着上：

```text
Transformer
GNN
Hypergraph NN
大型 MoE
```

原因：

- 数据时间太短。
- 复杂模型更容易过拟合。
- 简单模型更适合验证数据是否有效。

### 14.2 标签设计

建议：

```text
label_1d: T+1 日收益
label_5d: T+1 到 T+5 收益
label_20d: T+1 到 T+20 收益
```

做横截面排序：

```text
每天预测股票相对收益排名
```

不建议预测：

```text
绝对价格
明天一定涨/跌
```

### 14.3 训练窗口

从今天起采集，初期建议：

| 数据积累 | 训练方式 |
| --- | --- |
| 0-1 个月 | 不训练，只做数据质量和纸面因子 |
| 1-3 个月 | 简单模型，小心验证 |
| 3-6 个月 | expanding window 训练 |
| 6-12 个月 | rolling + expanding 对比 |
| 12 个月以上 | 市场状态分层和超图模型 |

### 14.4 Walk-forward 流程

```text
每天 20:00 生成特征
T+N 收益成为标签后写入 label_table
每周/每月重新训练模型
新模型先进入 paper trading
达到指标后再替换生产模型
```

### 14.5 消融实验

必须做：

```text
Baseline: price/volume only
Baseline + announcement events
Baseline + policy events
Baseline + global events
Baseline + commodity features
Baseline + hypergraph features
Baseline + sentiment features
```

判断：

```text
Rank IC 是否提升
ICIR 是否提升
top-bottom 收益是否提升
换手是否可接受
回撤是否下降
行业/市值暴露是否可控
```

## 15. 反泄漏制度

这是整个项目成败关键。

### 15.1 硬规则

训练样本在 `cutoff_time` 只能使用：

```text
visible_time <= cutoff_time
first_seen_at <= cutoff_time
relationship_first_seen_at <= cutoff_time
feature_generation_time <= cutoff_time 之后生成但输入数据不能越界
```

### 15.2 禁止事项

禁止：

```text
用当前概念板块回填过去
用当前行业分类回填过去
用后来修订的宏观数据覆盖初值
用公告报告期当作披露日
用新闻发布时间但不记录采集时间
用补采数据伪装成当时已见
用未来几天走势判断事件影响方向
用全样本标准化
用全样本选择特征
用全样本调参
```

### 15.3 数据延迟处理

如果 2026-04-24 的新闻在 2026-04-25 才被你采集到：

```text
source_publish_time = 2026-04-24
first_seen_at = 2026-04-25
visible_time = 2026-04-25
```

它不能用于 2026-04-24 的决策。

### 15.4 数据修订处理

如果宏观数据后来修订：

```text
version 1: first_seen_at = 初次发布
version 2: first_seen_at = 修订发布
```

训练时按 cutoff_time 取当时最新版本。

## 16. 监控与告警

每天必须监控：

```text
每个 source 是否按时更新
每个 crawler 是否失败
新文档数量是否异常
重复率是否异常
解析失败率是否异常
LLM 抽取失败率是否异常
行情缺失率是否异常
特征行数是否异常
模型输入缺失率是否异常
```

建议指标：

```text
source_freshness_minutes
crawl_success_rate
parse_success_rate
dedup_rate
new_doc_count
event_extraction_success_rate
entity_link_confidence_mean
feature_missing_rate
label_missing_rate
```

告警方式：

```text
本地日志
邮件
企业微信/钉钉/Telegram
每日自动报告
```

## 17. 合规与版权边界

### 17.1 基本原则

你可以做个人研究，但要遵守：

- 网站服务条款
- robots.txt
- 数据授权协议
- 版权限制
- API rate limit
- 个人信息保护要求
- 不绕过登录和反爬
- 不传播受版权保护全文

### 17.2 推荐合规策略

优先使用：

```text
官方公开数据
开放 API
RSS
授权数据源
付费数据源
交易所/券商接口
```

避免：

```text
绕过登录
绕过验证码
高频抓取
大规模复制付费内容
采集非公开用户数据
传播全文数据库
```

### 17.3 新闻全文策略

如果新闻版权不明确，建议保存：

```text
URL
标题
发布时间
摘要/公开片段
内容哈希
LLM 抽取出的结构化事件
```

结构化事件通常比全文更适合量化训练，也更节省存储。

## 18. 立即启动方案：前 30 天

前 30 天建议严格拆成两个目标：

```text
第一目标：采集层稳定运行
第二目标：后处理层最小闭环
```

如果时间不够，优先保证第一目标。因为采集层每天都在积累不可逆的数据资产，而后处理方法以后可以随时升级。

### 第 1-3 天：搭基础框架

完成：

```text
source_registry
crawl_run
raw_document
market_snapshot
data_lake 目录
日志系统
定时任务
```

先接入：

```text
A 股快照
公告
GDELT
财经 RSS
商品期货日线/快照
```

### 第 4-7 天：跑通数据留痕

目标：

```text
每天稳定采集
每条数据有 first_seen_at
原始文件保存
内容哈希去重
每日生成采集报告
```

不要急着做模型。

### 第 2 周：做事件抽取

目标：

```text
公告事件抽取
政策事件抽取
新闻事件抽取
实体识别
股票/行业映射
```

输出：

```text
event_table
event_entity_link
```

### 第 3 周：做第一版特征

特征：

```text
stock_event_count_1d
stock_event_sentiment_1d
stock_event_risk_5d
industry_event_count_5d
policy_support_score_20d
commodity_change_1d/5d
global_risk_score_1d
```

生成：

```text
date x instrument
```

### 第 4 周：接入 Qlib

目标：

```text
把采集到的特征转成 Qlib DataHandler 可用格式
跑 price/volume baseline
跑 baseline + event features
生成 paper trading 信号
```

### 采集优先级高于后处理

第一个月的优先级应该是：

```text
P0: 采集不断流、原始数据不丢、时间戳可信
P1: 最小解析和去重
P2: 简单事件抽取
P3: 简单特征和 Qlib 接入
P4: 模型效果
```

如果某天只能做一件事，优先修采集器、补日志、补 manifest，而不是调模型。

第一个月不要追求收益，追求：

```text
数据不断流
时间不泄漏
特征可复现
回测流程可跑
```

## 19. 3 个月计划

### 第 1 个月

核心：采集稳定性。

交付：

```text
稳定爬虫
原始数据湖
时间账本
公告/新闻/政策事件抽取
第一版特征
Qlib baseline
```

### 第 2 个月

核心：数据质量。

交付：

```text
实体链接优化
去重优化
事件类型扩展
商品暴露表
行业/概念超图
数据质量 dashboard
```

### 第 3 个月

核心：初步模型。

交付：

```text
LightGBM baseline
事件特征消融
超图聚合特征
paper trading
每周训练/评估流程
```

3 个月结束时，你应该能回答：

```text
哪些数据源最稳定？
哪些事件类型最多？
实体链接准确率如何？
事件特征有没有 Rank IC？
超图聚合有没有增量？
数据延迟和缺失是否可控？
```

## 20. 6-12 个月计划

### 6 个月

重点：

```text
扩大数据源
做动态超图
做市场状态分层
做 walk-forward paper trading
```

模型：

```text
LightGBM
CatBoost
简单 MLP
简单 gating
```

### 12 个月

重点：

```text
更可靠的事件统计
更稳定的模型评估
行业/风格分层
不同 horizon 模型
初步图/超图神经网络实验
```

可以开始研究：

```text
事件半衰期
事件新颖度
事件拥挤度
事件扩散路径
市场状态门控
```

## 21. 长期方向：1-3 年

当你积累 1-3 年干净数据后，真正有价值的研究会出现：

```text
地缘政治事件对 A 股行业轮动的影响
政策事件对行业收益的滞后结构
商品价格冲击对供应链公司的非线性传导
气候灾害对地区和行业的影响
舆情热度与短期反转/动量
事件超图中的资金共振
动态市场状态下的事件权重变化
```

这时可以做：

```text
动态超图神经网络
事件基础模型
金融事件 embedding
事件-股票对比学习
事件冲击预测
多专家 MoE
```

## 22. 最推荐的最小闭环

如果只做一个最小闭环，我建议：

```text
数据源:
  A 股日线/快照
  巨潮公告
  政策新闻
  GDELT
  商品期货

抽取:
  LLM 抽取事件
  实体链接到股票/行业/商品

关系:
  行业超图
  概念超图
  商品暴露超图
  事件影响超图

特征:
  事件计数
  情绪
  风险
  新颖度
  超图邻居聚合

模型:
  LightGBM

目标:
  T+1/T+5 横截面收益排名

评估:
  Rank IC
  ICIR
  top-bottom
  成本后收益
  回撤
```

这个闭环最适合个人启动，而且能自然扩展。

## 23. 我对你思路的最终判断

你的思路是可行的，而且是个人量化里很值得长期投入的方向。

但需要把目标从：

```text
收集世界上一切信息，然后训练一个大模型预测股票
```

改成：

```text
从今天开始建立可审计的 point-in-time 多源事件数据湖，
持续把现实世界事件转成结构化信号和超图关系，
先用简单模型证明数据增量，
再逐步升级到动态超图和大模型辅助的事件基础模型。
```

最重要的原则：

```text
宁可少收集，也要干净。
宁可低频，也要可审计。
宁可简单模型，也要消融有效。
宁可慢慢积累，也不要混入不可验证历史。
```

这件事如果坚持做 2-3 年，价值会越来越大。短期它是数据工程，中期它是事件 Alpha 系统，长期它可能变成你自己的金融事件世界模型。

## 24. 后续可以直接落地的开发任务

下一步可以从代码层面实现 V0，但必须拆成两个 milestone。

### V0-A：只做数据收集层

这是最高优先级。它的目标不是赚钱，也不是预测，而是每天稳定产生干净、可审计、不可变的数据资产。

```text
1. 创建 source_registry.yaml
2. 创建 data_lake 目录结构
3. 实现 crawl_run 和 raw_document 元数据表
4. 实现 AkShare A 股快照采集器
5. 实现公告/新闻 RSS/GDELT 采集器
6. 实现 content_hash 去重
7. 实现每日采集报告
8. 实现 collection_manifest
9. 实现 crawler health check
10. 实现原始数据备份
```

V0-A 的验收标准：

```text
连续 30 天采集不断流
所有原始数据都有 first_seen_at
所有原始文件都有 content_hash
所有 crawler run 都有日志
任何一天的数据都能按 manifest 复盘
```

### V0-B：再做后处理最小闭环

后处理层可以晚一点做，也可以不断推倒重来。

```text
1. 实现第一版 parser
2. 实现第一版 event_table schema
3. 实现 LLM 事件抽取占位接口
4. 实现 entity_link 候选匹配
5. 实现第一版 hyperedge schema
6. 实现 Qlib 特征导出模板
7. 实现 LightGBM baseline
8. 实现 paper trading 信号记录
```

建议先实现最小版本，不要一开始写复杂平台。

## 25. 参考资料与初始信息源

以下资料用于本方案的信息源梳理。实际采集前仍需逐个确认授权、访问频率和接口稳定性。

- GDELT Cloud Documentation：GDELT 数据、API、事件和新闻查询文档。https://docs.gdeltcloud.com/
- GDELT Project：全球新闻、事件、地理和情绪数据项目。https://www.gdeltproject.org/
- AkShare 文档：A 股实时行情接口示例，包括东方财富实时行情相关函数。https://akshare.akfamily.xyz/data/stock/stock.html
- Tushare Pro 文档：A 股、基金、期货、宏观等数据接口。https://tushare.pro/document/2
- BaoStock 文档：证券宝开源量化数据接口。http://baostock.com/baostock/index.php
- 巨潮资讯网：上市公司公告和信息披露核心来源。https://www.cninfo.com.cn/
- 上海证券交易所信息披露。https://www.sse.com.cn/disclosure/listedinfo/announcement/
- 深圳证券交易所信息披露。https://www.szse.cn/disclosure/listed/notice/
- 北京证券交易所信息披露。https://www.bse.cn/disclosure/announcement.html
- 中国证监会。http://www.csrc.gov.cn/
- 中国人民银行。http://www.pbc.gov.cn/
- 国家统计局。https://www.stats.gov.cn/
- 国家数据。https://data.stats.gov.cn/
- 中国政府网政策文件。https://www.gov.cn/zhengce/
- 上海期货交易所行情数据。https://www.shfe.com.cn/
- 大连商品交易所。http://www.dce.com.cn/
- 郑州商品交易所。http://www.czce.com.cn/
- 广州期货交易所。https://www.gfex.com.cn/
- 中国金融期货交易所。http://www.cffex.com.cn/
- Open-Meteo API：开放天气预报和历史天气接口。https://open-meteo.com/en/docs
- NASA FIRMS：全球火点/火灾近实时数据。https://firms.modaps.eosdis.nasa.gov/
- NOAA Climate Data Online API。https://www.ncdc.noaa.gov/cdo-web/webservices/v2
- Common Crawl News / Crawl 数据：开放网页抓取数据，可用于研究公开网页历史语料。https://commoncrawl.org/
- Caldara & Iacoviello Geopolitical Risk Index。https://www.matteoiacoviello.com/gpr.htm
- AI-GPR Index：LLM 生成的日频地缘政治风险指数。https://www.matteoiacoviello.com/ai_gpr.html
