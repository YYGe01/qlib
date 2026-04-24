# A 股 Point-in-Time 实时数据收集层实施方案

> 面向个人量化研究者的长期数据收集手册  
> 更新时间：2026-04-24  
> 本文只描述“数据收集层”：如何从今天开始长期、自动、可审计、不可变地保存 A 股相关原始信息。  
> 事件抽取、实体链接、超图、特征、训练、回测等后处理方法，放在 `unified_event_hypergraph_alpha_research_zh.md` 中讨论。  
> 免责声明：本文是工程与研究方案，不构成投资建议。采集数据时应遵守网站服务条款、robots 协议、版权限制、API 限额和数据供应商授权。

## 0. 核心定位

这份文档的目标不是训练模型，也不是判断哪些新闻利好利空，而是建立一个长期可复用的数据资产：

```text
从今天开始，把当时能看到的 A 股相关信息，按真实可见时间保存下来。
```

这个数据资产应该回答 6 个问题：

```text
什么时候采集的？
从哪里采集的？
当时页面/API/文件返回了什么？
原始内容有没有被保存？
这是第一次看到，还是重复/更新？
未来能否按当时状态完整回放？
```

不要让采集层回答这些问题：

```text
这条新闻影响哪些股票？
这是利好还是利空？
应该生成什么事件？
应该连成什么超图？
应该训练什么模型？
```

这些都属于后处理层。后处理方法会不断升级，采集层必须尽量稳定。

## 1. 最重要原则：采集层和后处理层分离

长期项目应该拆成两个系统。

```text
系统 A：数据收集层
  目标：长期、稳定、低假设、不可变地保存当时看到的事实。
  输出：raw data、metadata、crawl ledger、collection manifest。
  特点：永远有用，尽量不绑定任何模型、事件 schema、特征工程方法。

系统 B：后处理/研究层
  目标：基于收集层反复重算事件、实体、图、超图、特征、模型和策略。
  输出：events、entity links、hyperedges、features、labels、predictions。
  特点：可替换、可重算、可实验。
```

本文只写系统 A。

一句话：

> 数据收集层要像“不可变事实金库”，后处理层要像“可替换研究实验室”。

采集层只负责：

- 发现数据源。
- 定时采集。
- 保存原始响应。
- 保存原始文件。
- 记录时间戳。
- 记录请求参数。
- 记录版本和哈希。
- 做最小去重。
- 做最小字段标准化。
- 记录数据质量。
- 生成每日 manifest。
- 做备份和监控。

采集层不负责：

- LLM 事件抽取。
- 金融情绪打分。
- 实体链接。
- 产业链推断。
- 图/超图构建。
- 特征工程。
- 标签生成。
- 模型训练。
- 回测和交易。

## 2. 为什么个人更应该从采集层开始

个人量化最容易踩的坑不是模型，而是数据：

- 历史新闻库可能回填。
- 历史概念板块可能事后归因。
- 宏观数据可能修订。
- 财报数据可能按报告期误用。
- 公告的报告日期和披露日期可能混淆。
- 舆情热度可能只能拿到当前快照。
- 产业链关系可能是后来整理出来的。
- 很多网站不会保留历史页面状态。

从今天开始自己采集，可以建立一个最干净的时间账本：

```text
我当时确实看到了什么。
```

只要这个账本足够干净，以后无论换什么 LLM、图模型、超图模型、因子模型，都可以从原始数据重新生成后处理结果。

## 3. 项目目标和非目标

### 3.1 目标

数据收集层的目标：

```text
连续多年稳定采集 A 股相关多源信息；
所有原始数据 append-only 保存；
所有数据都有 first_seen_at；
所有采集任务都有 crawl_run 记录；
所有文件都有 content_hash；
所有数据源都有 source_registry；
每天都有 collection_manifest；
任何一天都能回放当时看到的数据集合。
```

### 3.2 非目标

本文件不做：

```text
事件抽取
实体链接
超图构建
特征生成
模型训练
回测
策略评估
```

这些全部放到另一份文档。

### 3.3 第一阶段最小目标

最小可用采集系统不需要复杂：

```text
5 类数据源
  A 股行情快照
  上市公司公告
  政策/监管新闻
  商品/全球市场价格
  GDELT/公开新闻事件

4 张核心表
  source_registry
  crawl_run
  raw_item
  collection_manifest

3 个硬约束
  原始数据不覆盖
  first_seen_at 不伪造
  每日 manifest 可复盘
```

## 4. 总体架构

数据收集层建议分 8 个模块。

```text
Source Registry
  -> Scheduler
  -> Crawler / Connector
  -> Crawl Ledger
  -> Raw Append-Only Store
  -> Minimal Normalizer
  -> Collection Manifest
  -> Monitoring / Backup
```

### 4.1 架构图

```text
+------------------+
| Source Registry  |
| 数据源/授权/频率   |
+--------+---------+
         |
         v
+------------------+       +----------------------+
| Scheduler        | ----> | Crawler / Connector  |
| 定时/重试/限速     |       | API/RSS/Web/File      |
+------------------+       +----------+-----------+
                                      |
                                      v
                            +----------------------+
                            | Crawl Ledger         |
                            | 每次请求和运行留痕     |
                            +----------+-----------+
                                      |
                                      v
                            +----------------------+
                            | Raw Append-Only Store|
                            | 原始响应/文件/快照     |
                            +----------+-----------+
                                      |
                                      v
                            +----------------------+
                            | Minimal Normalizer   |
                            | 最小字段/时间标准化    |
                            +----------+-----------+
                                      |
                                      v
                            +----------------------+
                            | Collection Manifest  |
                            | 每日清单/哈希/质量     |
                            +----------+-----------+
                                      |
                                      v
                            +----------------------+
                            | Backup / Monitoring  |
                            | 备份/告警/健康检查     |
                            +----------------------+
```

### 4.2 最小标准化是什么意思

最小标准化只做这些事：

- 统一时间格式。
- 统一来源 ID。
- 统一证券代码格式。
- 记录原始字段名和标准字段名映射。
- 生成哈希。
- 记录 first_seen_at。
- 判断是否重复。
- 保存原始文件路径。

最小标准化不做这些事：

- 不判断语义。
- 不抽事件。
- 不预测影响方向。
- 不建图。
- 不生成因子。

这样未来可以用更好的方法重新处理。

## 5. 时间账本

时间账本是整个系统最重要的部分。

### 5.1 每条数据至少记录 8 个时间

```text
source_event_time    事件实际发生时间，若来源提供
source_publish_time  来源声称的发布时间
source_update_time   来源声称的更新时间
crawl_start_time     爬虫开始请求时间
crawl_end_time       爬虫拿到响应时间
first_seen_at        系统第一次看到该 item 的时间
stored_at            写入本地存储时间
manifest_time        写入每日 manifest 的时间
```

如果来源没有某些时间字段，就留空，不要猜。

### 5.2 first_seen_at 是硬事实

`first_seen_at` 的含义：

```text
我的系统第一次看到这条内容的时间。
```

它不等于来源发布时间。

例子：

```text
某公告 source_publish_time = 2026-04-24 18:00
你的爬虫 first_seen_at = 2026-04-24 20:05
```

那么对你的数据系统来说，它最早只能证明：

```text
2026-04-24 20:05 之后我见过这条公告。
```

### 5.3 补采数据不能伪装成实时数据

如果爬虫故障，第二天补采前一天数据，必须记录：

```text
source_publish_time = 来源原始发布时间
first_seen_at = 你补采到的时间
is_backfilled = true
backfill_reason = crawler_failure / manual_repair / source_delay
```

后处理层可以决定是否使用，但采集层不能篡改 first_seen_at。

### 5.4 时间统一规范

建议内部统一：

```text
ISO 8601
Asia/Shanghai
同时保存 UTC 可选
```

字段示例：

```text
2026-04-24T20:05:31+08:00
```

对于海外市场和全球新闻：

```text
保留 source timezone；
同时转换成 Asia/Shanghai；
不要丢失原始字符串。
```

## 6. 数据源分层

不要一开始追求“所有信息”。先按优先级做。

### 6.1 P0：第一天就值得采集

| 数据源类别 | 价值 | 采集频率 | 说明 |
| --- | --- | --- | --- |
| A 股行情快照 | 基础市场状态 | 1-5 分钟/盘后 | 先做快照和日线 |
| 上市公司公告 | 公司级事件 | 5-15 分钟 | 巨潮、交易所 |
| 交易所/监管信息 | 规则和监管冲击 | 15-30 分钟 | 证监会、交易所 |
| 政策/部委新闻 | A 股政策驱动 | 30-60 分钟 | 政府网、央行、发改委等 |
| 商品期货/大宗价格 | 周期行业外部变量 | 1-5 分钟/盘后 | 国内期货和国际商品 |
| 全球市场指标 | 外部风险偏好 | 5-30 分钟 | 美股、美元、美债、VIX |
| GDELT/全球新闻 | 地缘、灾害、国际事件 | 15-60 分钟 | 适合个人低成本起步 |

### 6.2 P1：稳定后再接入

| 数据源类别 | 价值 | 难点 |
| --- | --- | --- |
| 财经新闻/RSS | 新闻事件 | 授权、去重、正文版权 |
| 舆情平台公开数据 | 情绪和热度 | 合规、反爬、噪声 |
| 融资融券/北向/龙虎榜 | 资金行为 | 来源稳定性和披露延迟 |
| 基金持仓 | 机构拥挤 | 季度披露滞后 |
| 行业/概念成分 | 关系先验 | 历史版本和事后归因 |
| 天气/灾害 | 气候冲击 | 地理映射 |

### 6.3 P2：长期/付费/高难

| 数据源类别 | 价值 | 为什么后做 |
| --- | --- | --- |
| Level-2 行情 | 高频微观结构 | 成本高，个人不必先做 |
| 全量新闻全文 | 更完整事件覆盖 | 授权和版权复杂 |
| 全网社交媒体 | 舆情覆盖 | 合规和清洗难 |
| 研报全文/电话会纪要 | 机构观点 | 版权和数据成本 |
| 供应链数据库 | 事件传导 | 数据贵，维护重 |
| 另类数据/卫星/遥感 | 非公开视角 | 工程成本高 |

## 7. 具体数据源清单

实际使用前要逐个确认接口稳定性、授权、频率限制和服务条款。

### 7.1 A 股行情

可选来源：

- AkShare。
- Tushare Pro。
- BaoStock。
- 券商 API。
- 付费数据商。

第一阶段建议采集字段：

```text
instrument
exchange
name
snapshot_time
last_price
open
high
low
prev_close
volume
amount
turnover
limit_up
limit_down
halt_status
source_raw_payload
first_seen_at
content_hash
```

注意：

- 免费接口不保证稳定。
- 字段含义可能变。
- 要保留原始 payload。
- 行情快照缺失要记录，不要静默跳过。
- 日线数据和快照数据分开保存。

### 7.2 上市公司公告

优先采集：

- 巨潮资讯网。
- 上交所信息披露。
- 深交所信息披露。
- 北交所信息披露。

采集字段：

```text
announcement_id
source
security_code
security_name
title
category
source_publish_time
source_url
pdf_url
html_url
download_time
first_seen_at
raw_file_path
text_file_path_optional
content_hash
status
```

采集要求：

- PDF 原文必须保存。
- 页面列表原始响应必须保存。
- 附件必须保存。
- 更正公告作为新 item。
- 公告日期、披露时间、下载时间分开。

### 7.3 政策和监管

建议源：

- 中国政府网。
- 中国证监会。
- 上海证券交易所。
- 深圳证券交易所。
- 北京证券交易所。
- 中国人民银行。
- 国家统计局。
- 国家发改委。
- 工信部。
- 财政部。
- 商务部。
- 生态环境部。
- 国家能源局。
- 农业农村部。

采集字段：

```text
doc_id
source_department
title
doc_no
category
source_publish_time
source_update_time
url
raw_html_path
attachment_paths
first_seen_at
content_hash
```

注意：

- 政策页面经常更新，要版本化。
- 附件比网页正文更重要。
- 不要只保存标题。

### 7.4 新闻和全球事件

第一阶段建议先用：

- GDELT。
- 有 RSS 的公开财经新闻源。
- 有公开列表页的监管/交易所新闻。

采集字段：

```text
url
canonical_url
title
summary
source_name
author
source_publish_time
source_update_time
language
country
raw_html_path
raw_api_payload_path
first_seen_at
content_hash
dedup_hash
```

版权策略：

- 能合法保存全文时保存全文。
- 不确定版权时保存 URL、标题、摘要、哈希和元数据。
- 不传播受版权保护的全文库。

### 7.5 商品期货和大宗商品

国内源：

- 上海期货交易所。
- 上海国际能源交易中心。
- 大连商品交易所。
- 郑州商品交易所。
- 广州期货交易所。
- 中国金融期货交易所。

国际源可根据接口条件接入：

- 原油。
- 黄金。
- 铜。
- 美元指数。
- 美债收益率。
- VIX。

采集字段：

```text
symbol
exchange
contract
snapshot_time
last_price
open
high
low
settlement
prev_settlement
volume
open_interest
source_payload
first_seen_at
content_hash
```

注意：

- 主力合约切换要保留规则和当时主力。
- 夜盘和日盘时间要分开。
- 国内期货节假日和 A 股不同。

### 7.6 宏观数据和经济日历

建议采集两类：

```text
发布日历
实际发布值
```

来源：

- 国家统计局。
- 国家数据。
- 中国人民银行。
- 海关总署。
- 财政部。
- 发改委。
- 交易所/财经日历公开源。

采集字段：

```text
indicator_id
indicator_name
period
source_publish_time
first_seen_at
value
unit
previous_value
revision_flag
raw_payload_path
content_hash
```

注意：

- 初值和修订值分版本保存。
- 发布日和统计期分开。
- 不要用后来的修订值覆盖初值。

### 7.7 天气、灾害和地理事件

可选来源：

- Open-Meteo。
- NASA FIRMS。
- NOAA。
- 气象部门公开信息。
- 台风路径公开数据。
- 灾害预警公开数据。

采集字段：

```text
source
region
lat
lon
event_or_observation_time
source_publish_time
first_seen_at
event_type
severity_raw
raw_payload_path
content_hash
```

采集层只保存灾害事实，不判断影响哪些股票。

### 7.8 舆情和公开热度

舆情数据有价值，但合规和噪声问题大。

建议原则：

- 优先官方开放 API。
- 优先公开榜单和指数。
- 控制频率。
- 不绕过登录。
- 不绕过验证码。
- 不采集私人信息。

采集字段：

```text
platform
topic
keyword
rank
heat_value
snapshot_time
url
first_seen_at
raw_payload_path
content_hash
```

第一阶段可以只采集主题热度，不采集大量用户文本。

### 7.9 手工维护数据也要版本化

有些数据个人很难自动采集，例如：

- 产业链关系。
- 商品暴露关系。
- 公司产品。
- 概念别名。
- 公司别名。

可以手工维护，但必须像爬虫数据一样留痕：

```text
manual_dataset_name
version
valid_from
valid_to
created_at
updated_at
source_reference
editor
change_reason
content_hash
```

不要直接改 Excel 覆盖旧版本。

## 8. 核心表设计

本节只设计采集层表，不包含事件、超图、特征、模型表。

### 8.1 source_registry

```sql
source_id
source_name
source_type
base_url
official_level
license_type
terms_url
robots_url
auth_type
rate_limit_rule
expected_update_frequency
priority
enabled
notes
created_at
updated_at
```

### 8.2 crawl_run

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
updated_item_count
duplicate_count
rate_limit_hit
error_message
code_git_commit
```

### 8.3 raw_item

所有采集到的 item 都要进这张统一索引表。

```sql
item_id
source_id
source_item_id
source_url
canonical_url
item_type
title
source_publish_time
source_update_time
crawl_run_id
crawl_start_time
crawl_end_time
first_seen_at
stored_at
raw_storage_path
raw_mime_type
raw_size_bytes
content_hash
dedup_hash
is_backfilled
backfill_reason
status
```

`item_type` 示例：

```text
market_snapshot
announcement
policy_doc
news_article
macro_release
commodity_snapshot
weather_observation
sentiment_snapshot
manual_dataset
```

### 8.4 raw_file

一个 item 可能有多个文件。

```sql
file_id
item_id
source_id
file_role
file_url
storage_path
mime_type
size_bytes
content_hash
download_start_time
download_end_time
first_seen_at
status
```

`file_role` 示例：

```text
html
pdf
attachment
api_json
csv
image
text_extracted_optional
```

### 8.5 market_snapshot_raw

行情类数据可以有专门快照表，但仍然必须保留 raw payload。

```sql
snapshot_id
item_id
source_id
instrument
exchange
source_timestamp
first_seen_at
last_price
open
high
low
prev_close
volume
amount
limit_up
limit_down
halt_status
raw_storage_path
content_hash
```

### 8.6 source_item_state

用于识别更新和重复。

```sql
source_id
source_item_key
first_item_id
latest_item_id
first_seen_at
latest_seen_at
latest_content_hash
seen_count
update_count
```

### 8.7 collection_manifest

每天生成一次。

```sql
manifest_id
manifest_date
generated_at
source_count
run_count
raw_item_count
new_item_count
updated_item_count
duplicate_count
error_count
manifest_path
manifest_hash
```

manifest 文件中应包含：

```json
{
  "date": "2026-04-24",
  "generated_at": "2026-04-24T23:50:00+08:00",
  "sources": [
    {
      "source_id": "cninfo",
      "runs": 96,
      "new_items": 120,
      "errors": 0,
      "latest_success_time": "2026-04-24T23:45:00+08:00"
    }
  ],
  "raw_files": [
    {
      "item_id": "xxx",
      "path": "collection/raw/source=cninfo/dt=2026-04-24/xxx.pdf",
      "content_hash": "sha256:..."
    }
  ]
}
```

### 8.8 source_health

```sql
source_id
check_time
status
freshness_minutes
last_success_time
last_error_time
success_rate_24h
new_items_24h
parse_optional_failure_rate
notes
```

## 9. 存储设计

### 9.1 推荐个人技术栈

简单起步：

```text
元数据：SQLite / DuckDB
结构化快照：Parquet
原始文件：本地文件系统
调度：Windows Task Scheduler / cron / APScheduler
日志：普通文件 + JSONL
备份：移动硬盘 + 云盘/对象存储
```

长期升级：

```text
元数据：PostgreSQL
分析：DuckDB
对象存储：MinIO / S3 兼容存储
调度：Prefect / Dagster / Airflow
监控：Prometheus / Grafana 可选
数据版本：DVC / lakeFS 可选
```

### 9.2 目录结构

```text
data_lake/
  collection/
    registry/
      source_registry.yaml
    metadata/
      crawl_run.parquet
      raw_item.parquet
      raw_file.parquet
      source_item_state.parquet
    raw/
      source=cninfo/
        dt=2026-04-24/
          *.json
          *.pdf
      source=gdelt/
        dt=2026-04-24/
          *.json
      source=ashare_snapshot/
        dt=2026-04-24/
          *.json
    normalized_min/
      market_snapshot_raw/
      announcement_index/
      policy_index/
      macro_release_raw/
      commodity_snapshot_raw/
    manifests/
      dt=2026-04-24/
        collection_manifest.json
        raw_file_manifest.json
        source_health.json
    logs/
      crawler_name=cninfo/
        dt=2026-04-24/
          *.log
    backups/
```

后处理层不放在这里，可以另建：

```text
data_lake/derived/
```

但这份文档不展开。

### 9.3 文件命名

```text
{source_id}_{crawl_time}_{content_hash_prefix}.{ext}
```

示例：

```text
cninfo_20260424T200531+0800_ab12cd34.pdf
gdelt_20260424T201500+0800_ef56aa22.json
ashare_snapshot_20260424T093501+0800_91ac7820.json
```

## 10. 采集器设计

### 10.1 每个采集器必须具备

```text
限速
重试
超时
幂等
断点续采
错误日志
原始响应保存
哈希去重
请求参数保存
响应状态保存
source health 更新
```

### 10.2 采集器类型

```text
API connector
RSS connector
web list crawler
file downloader
market snapshot collector
manual dataset importer
calendar collector
```

### 10.3 不同类型的采集策略

API：

```text
保存 request params
保存 raw JSON
记录 rate limit
记录分页 cursor
```

RSS：

```text
保存 feed XML
保存 item URL
保存 guid
定期重新拉取，识别更新
```

网页列表：

```text
保存列表页 HTML
保存详情页 HTML
保存分页参数
不要只保存详情页
```

PDF/附件：

```text
保存原始文件
记录下载 URL
记录 MIME type
记录 content_hash
```

行情快照：

```text
保存完整 raw payload
不要只保存标准字段
快照频率稳定比极高频更重要
```

### 10.4 推荐采集频率

| 数据 | 频率 |
| --- | --- |
| A 股盘中快照 | 1-5 分钟 |
| A 股盘后日线 | 16:00、20:00 |
| 公告 | 5-15 分钟 |
| 交易所/监管新闻 | 15-30 分钟 |
| 部委政策 | 30-60 分钟 |
| GDELT/国际新闻 | 15-60 分钟 |
| 财经 RSS | 5-15 分钟 |
| 商品期货 | 1-5 分钟/盘后 |
| 全球市场 | 5-30 分钟 |
| 天气灾害 | 1-6 小时 |
| 宏观数据 | 按发布日历 + 每日兜底 |

### 10.5 失败处理

失败不应该静默。

记录：

```text
source_id
run_id
error_type
error_message
http_status
retry_count
last_success_time
```

失败后：

- 短期重试。
- 超过阈值告警。
- 次日补采时标记 `is_backfilled=true`。

## 11. 去重和版本化

### 11.1 两种哈希

```text
content_hash: 原始内容哈希，判断内容是否完全一致。
dedup_hash: 规范化后的弱哈希，判断是否可能是同一条信息。
```

例如新闻转载：

```text
title + source_publish_time + canonical_url
```

可以生成 dedup_hash。

### 11.2 更新不是覆盖

如果同一个 URL 内容变了：

```text
旧版本保留
新版本新增 raw_item
source_item_state 指向 latest_item_id
```

这样才能还原历史。

### 11.3 页面列表也要保存

很多数据源的列表页能证明：

```text
某个时间点这个公告/新闻已经出现在列表里。
```

所以不要只保存详情页，列表页也要保存原始响应。

## 12. 数据质量监控

每天监控：

```text
source_freshness_minutes
crawl_success_rate
new_item_count
duplicate_rate
updated_item_count
raw_file_missing_count
content_hash_missing_count
first_seen_at_missing_count
http_error_rate
file_download_failure_rate
source_schema_change_count
```

异常示例：

- 某公告源 2 小时没有新数据。
- A 股快照行数突然少 50%。
- 某 API 字段名变化。
- PDF 下载成功但大小为 0。
- content_hash 大量重复。
- 爬虫全失败但没有告警。

每日报告建议包含：

```text
每个 source 的成功率
每个 source 的新 item 数
每个 source 的错误数
采集延迟分布
原始文件大小统计
缺失字段统计
需要人工检查的问题
```

## 13. 合规和版权

### 13.1 基本原则

优先使用：

- 官方公开数据。
- 开放 API。
- RSS。
- 授权数据源。
- 付费数据源。
- 交易所/券商接口。

避免：

- 绕过登录。
- 绕过验证码。
- 绕过反爬。
- 高频压测网站。
- 大规模复制付费内容。
- 采集非公开用户数据。
- 传播受版权保护全文。

### 13.2 每个 source 记录授权信息

`source_registry` 中必须记录：

```text
terms_url
robots_url
license_type
allowed_frequency
auth_type
notes
```

### 13.3 新闻全文策略

如果版权不明确：

```text
保存 URL、标题、摘要、发布时间、来源、哈希。
全文只保存可合法保存的内容。
不对外传播全文数据库。
```

后处理层可以基于允许保存的内容做结构化抽取。

## 14. 备份和灾难恢复

采集层是长期资产，必须备份。

### 14.1 备份策略

建议：

```text
每日增量备份 metadata 和 manifest
每周备份 raw 文件
每月做一次完整快照
至少保留一份离线备份
重要 manifest 做多地保存
```

### 14.2 校验策略

定期校验：

```text
文件是否存在
content_hash 是否一致
manifest 是否能读取
metadata 是否能关联 raw 文件
备份是否可恢复
```

### 14.3 不要只备份派生结果

最重要的是：

```text
raw 文件
metadata
manifest
source_registry
crawl logs
```

事件、特征、模型可以重算，原始数据丢了就不能重来。

## 15. 前 30 天实施计划

### 第 1-3 天：搭采集骨架

完成：

```text
source_registry.yaml
data_lake/collection 目录
crawl_run 表
raw_item 表
raw_file 表
日志系统
定时任务
```

接入 1-2 个最简单数据源。

### 第 4-7 天：跑通原始保存

完成：

```text
原始响应保存
content_hash
first_seen_at
每日 manifest
source health
错误日志
```

目标：

```text
任何一条数据都能找到原始文件和采集时间。
```

### 第 2 周：扩展 P0 数据源

接入：

```text
A 股快照
公告
政策/监管
GDELT
商品/全球市场
```

目标：

```text
每天自动采集，不需要人工启动。
```

### 第 3 周：完善质量和备份

完成：

```text
采集质量报告
source freshness 检查
失败告警
备份脚本
文件哈希校验
```

### 第 4 周：稳定运行

目标：

```text
连续 7 天不中断
所有失败都有日志
所有补采都有 is_backfilled
每日 manifest 可复盘
```

第一个月不要急着做模型。只要采集层稳定，就已经在积累最稀缺的数据资产。

## 16. 3 个月实施计划

### 第 1 个月

核心：系统能持续跑。

验收：

```text
P0 数据源稳定采集
first_seen_at 完整
raw 文件完整
manifest 完整
每日质量报告
```

### 第 2 个月

核心：数据源更丰富。

新增：

```text
更多政策源
更多商品源
宏观发布日历
天气/灾害源
公开热度源
手工维护数据版本化
```

### 第 3 个月

核心：采集层可运维。

完成：

```text
source health dashboard
备份恢复演练
schema 变化检测
数据覆盖率统计
采集延迟统计
```

3 个月结束时，你应该能回答：

```text
哪些源最稳定？
哪些源最容易失败？
每天新增多少数据？
原始文件是否完整？
采集延迟是多少？
补采比例是多少？
哪些源有合规风险？
```

## 17. 长期运维原则

### 17.1 稳定比丰富更重要

宁可先稳定采集 10 个源，也不要同时接 100 个不稳定源。

### 17.2 原始数据比解析结果更重要

解析器坏了可以重写，原始页面没保存就没了。

### 17.3 first_seen_at 不能被修正

即使发现来源发布时间更早，也不能把 `first_seen_at` 改早。

### 17.4 手工数据也要留痕

人工维护的产业链、概念、别名、商品暴露表，同样必须版本化。

### 17.5 后处理可以失败，采集不能长期失败

如果时间有限，优先修采集器、manifest、备份和监控。

## 18. 和后处理文档的接口

采集层给后处理层提供这些输入：

```text
source_registry
crawl_run
raw_item
raw_file
market_snapshot_raw
collection_manifest
source_health
manual_versioned_datasets
```

后处理层必须通过这些字段做 point-in-time 过滤：

```text
first_seen_at
source_publish_time
source_update_time
crawl_run_id
content_hash
is_backfilled
```

后处理层可以生成：

```text
parsed_text
events
entity_links
hyperedges
features
labels
models
predictions
```

但这些都不能写回覆盖采集层原始数据。

## 19. 后续可以直接落地的开发任务

V0 只做采集层。

```text
1. 创建 source_registry.yaml
2. 创建 data_lake/collection 目录结构
3. 实现 crawl_run / raw_item / raw_file 元数据表
4. 实现 A 股快照采集器
5. 实现公告采集器
6. 实现政策/监管新闻采集器
7. 实现 GDELT 采集器
8. 实现商品/全球市场快照采集器
9. 实现 content_hash 和 dedup_hash
10. 实现 collection_manifest
11. 实现 source_health
12. 实现每日质量报告
13. 实现备份脚本
14. 实现故障告警
```

V0 验收标准：

```text
连续 30 天采集不断流；
所有 raw item 都有 first_seen_at；
所有 raw file 都有 content_hash；
所有 crawler run 都有日志；
每日 manifest 能还原当天数据清单；
补采数据被明确标记；
源失败会告警。
```

## 20. 初始参考源

以下只作为初始信息源清单，实际接入前应确认授权、频率限制和接口稳定性。

- GDELT Cloud Documentation：https://docs.gdeltcloud.com/
- GDELT Project：https://www.gdeltproject.org/
- AkShare 文档：https://akshare.akfamily.xyz/data/stock/stock.html
- Tushare Pro 文档：https://tushare.pro/document/2
- BaoStock 文档：http://baostock.com/baostock/index.php
- 巨潮资讯网：https://www.cninfo.com.cn/
- 上海证券交易所信息披露：https://www.sse.com.cn/disclosure/listedinfo/announcement/
- 深圳证券交易所信息披露：https://www.szse.cn/disclosure/listed/notice/
- 北京证券交易所信息披露：https://www.bse.cn/disclosure/announcement.html
- 中国证监会：http://www.csrc.gov.cn/
- 中国人民银行：http://www.pbc.gov.cn/
- 国家统计局：https://www.stats.gov.cn/
- 国家数据：https://data.stats.gov.cn/
- 中国政府网政策文件：https://www.gov.cn/zhengce/
- 上海期货交易所：https://www.shfe.com.cn/
- 大连商品交易所：http://www.dce.com.cn/
- 郑州商品交易所：http://www.czce.com.cn/
- 广州期货交易所：https://www.gfex.com.cn/
- 中国金融期货交易所：http://www.cffex.com.cn/
- Open-Meteo API：https://open-meteo.com/en/docs
- NASA FIRMS：https://firms.modaps.eosdis.nasa.gov/
- NOAA Climate Data Online API：https://www.ncdc.noaa.gov/cdo-web/webservices/v2
- Common Crawl：https://commoncrawl.org/
- Caldara & Iacoviello Geopolitical Risk Index：https://www.matteoiacoviello.com/gpr.htm
- AI-GPR Index：https://www.matteoiacoviello.com/ai_gpr.html

