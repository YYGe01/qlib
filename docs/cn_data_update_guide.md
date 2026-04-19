# Qlib 中国区数据（`cn_data`）更新指南

本文说明如何维护与更新本地 Qlib 中国区行情数据目录（常见路径：`~/.qlib/qlib_data/cn_data`）。内容基于 Qlib 仓库内脚本与文档整理，便于自建数据流水线或定期增量更新。

---

## 1. 背景：`cn_data` 是什么

- **含义**：`cn_data` 通常指 **`provider_uri` 指向的 Qlib 二进制数据根目录**，其中 `region` 为中国（A 股等），频率多为日频 `day`。
- **典型路径**：`~/.qlib/qlib_data/cn_data`（与 `scripts/get_data.py`、`scripts/README.md` 中的示例一致）。
- **与代码的关系**：初始化时使用例如：

  ```python
  import qlib
  from qlib.constant import REG_CN

  qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)
  ```

- **官方预置包的特点**：通过 `get_data.py qlib_data` 下载的压缩包**不会按交易日持续更新**；若需要「最新交易日」数据，需自行采集并写入 Qlib 格式，或使用下文 **Yahoo 增量流程**。

---

## 2. Qlib 数据目录应满足的格式（必须一致）

无论数据来自官方下载、社区包还是自建 CSV，**最终落在磁盘上的结构需符合 Qlib LocalProvider 约定**，否则 `qlib.init` / `D.features` 会异常或读不到字段。

### 2.1 目录结构（数据根目录下）

常见子目录包括（与 `scripts/data_collector/README.md` 一致）：

| 子目录 | 作用 |
|--------|------|
| `features/` | 按标的、按字段存储的二进制特征（核心行情） |
| `calendars/` | 交易日历，如日频 `day.txt` |
| `instruments/` | 标的列表与时间范围，如 `all.txt`、`csi300.txt` 等 |
| `features_cache/`、`dataset_cache/` | 运行期缓存（可选；整包替换时可能被删除重建） |

### 2.2 特征字段（Features）

- 日频示例字段：**开高低收、成交量、复权因子** 等，在 Qlib 表达式中对应如 `$open`、`$high`、`$low`、`$close`、`$volume`、`$factor`。
- **未复权处理**：文档约定若价格未做复权调整，则 **`factor = 1`**。
- 健康检查脚本 `scripts/check_data_health.py` 会按 `$open/$high/$low/$close/$volume/$factor` 等检查完整性（可作更新后自检参考）。

### 2.3 日历与标的（Calendar / Instruments）

- **日历**：`calendars/day.txt`（日频）等，需与 `features` 中实际有数据的交易日对齐。
- **标的**：`instruments/all.txt` 等为常用全集；指数成分如 `csi300.txt` 等可按需更新（Yahoo 增量命令末尾会尝试刷新部分指数成分，见下文）。

### 2.4 从 CSV 转为 Qlib 二进制

- 标准工具：**`scripts/dump_bin.py`**（`dump_all`全量重建 / `dump_update` 增量追加需配合已有日历与 instruments 逻辑，一般用户更推荐 Yahoo 脚本封装的 `update_data_to_bin`）。
- CSV 中时间、代码列名需与参数一致（默认 **`date`**、**`symbol`**），详见下文命令示例。

### 2.5 重要限制：不要在「精简官方包」上盲目做增量

官方发布的离线包为减小体积**可能去掉部分字段**。文档明确：**不能指望仅基于该离线包做可靠的增量更新**；若要长期增量维护，应使用 **Yahoo 采集链路从零构建**，或始终用自己完整字段的 CSV 再 `dump_bin`。

### 2.6 各文件形态与数据样例（可对照磁盘上的真实文件）

以下样例中的**日期、代码、数值均为演示用途**；实际数据以你本机目录为准。格式说明与 `scripts/dump_bin.py`、`qlib/data/storage/file_storage.py` 中的读写逻辑一致。

---

#### 2.6.1 `calendars/day.txt`（日频交易日历）

- **编码**：UTF-8。
- **格式**：纯文本，**一行一个交易日**；**无表头**；日期字符串与 `dump_bin` 中日频格式一致，为 **`YYYY-MM-DD`**（见 `DumpDataBase.DAILY_FORMAT`）。
- **样例**（文件：`calendars/day.txt`）：

```text
2005-01-04
2005-01-05
2005-01-06
```

- **说明**：全市场日历通常取并集；各标的 `.bin` 中的时间下标与**本文件行号（从 0 起算）**对应。

---

#### 2.6.2 `calendars/1min.txt`（分钟频日历，若使用分钟线数据）

- **格式**：同样**一行一个时间戳**，**无表头**；时间为 **`YYYY-MM-DD HH:MM:SS`**（见 `DumpDataBase.HIGH_FREQ_FORMAT`）。
- **样例**：

```text
2020-01-02 09:31:00
2020-01-02 09:32:00
2020-01-02 09:33:00
```

---

#### 2.6.3 `instruments/all.txt`、`instruments/csi300.txt` 等（标的列表）

- **分隔符**：**制表符** `\t`（`DumpDataBase.INSTRUMENTS_SEP` / `FileInstrumentStorage.INSTRUMENT_SEP`）。
- **列（无表头，共 3 列）**：

| 列序 | 字段名（逻辑） | 含义 |
|------|----------------|------|
| 1 | `instrument` / `symbol` | 标的代码，如 A 股 `SH600000`、`SZ000001` |
| 2 | `start_datetime` | 该标的在数据中的起始时间（含） |
| 3 | `end_datetime` | 结束时间（含） |

- **样例**（文件：`instruments/all.txt`）：

```text
SH600000	2005-01-04	2020-09-25
SZ000001	2005-01-04	2020-09-25
```

- **样例**（文件：`instruments/csi300.txt`，成分股列表，格式相同）：

```text
SH600000	2010-01-04	2020-09-25
SZ300750	2018-06-11	2020-09-25
```

- **注意**：代码在写入时经 `fname_to_code` /大小写规则处理；在 **Linux** 下 `features/` 子目录名需与约定一致（全小写等），否则可能加载失败（参见 `check_data_health.py` 中的说明）。

---

#### 2.6.4 `features/` 目录与 `*.day.bin` / `*.1min.bin`（特征二进制）

- **目录层级**：`features/<instrument小写>/`，例如浦发银行常为 `features/sh600000/`（与 `FileFeatureStorage.file_name` 中 `instrument.lower()` 一致）。
- **文件名**：`<字段名小写>.<频率小写>.bin`，例如日频收盘价为 **`close.day.bin`**，成交量为 **`volume.day.bin`**。
- **文件内容（重要）**：**小端 `float32`（`dtype="<f"`）** 数组。
  - **首元素**：该标的特征序列在**全局日历**（如 `day.txt`）中的**起始下标**（`start_index`，浮点存储）。
  - **后续元素**：与日历上连续下标对齐的特征取值；缺失处可为 NaN 对应的 float 位型。
- **逻辑示意**（非文件内容，便于理解）：

```text
# 若某标的 close 从日历第 100 天开始有 3 个有效 float 值 v0,v1,v2：
# 文件中 float32 序列为: [100.0, v0, v1, v2]
```

- **与 `dump_bin` 的关系**：全量模式 `dump_all` 会写入 `[date_index, ...values]`；增量模式 `DumpDataUpdate` 对已有文件采用 **追加** 方式写入新段（见 `DumpDataBase._data_to_bin`）。

---

#### 2.6.5 归一化后的 CSV（`dump_bin.py` 的输入，`data_path`）

- **常见约定**：每标的一个 `.csv`，或目录下多个 `.csv`；列名默认 **`date`**、**`symbol`**与 `dump_bin` 参数一致。
- **Yahoo 日频链路**在归一化、增量扩展后，核心字段包括（与 `YahooNormalize1dExtend.column_list` 等一致）：`open`、`high`、`low`、`close`、`volume`、`factor`、`change`，以及 `date`、`symbol`（dump 时常用 `--exclude_fields date,symbol` 排除后二者）。
- **样例**（单标的、多行；数值仅为演示；Yahoo 管线中价格常按「首日 close 缩放」做过标准化，故 close 不一定等于原始报价）：

```text
date,symbol,open,high,low,close,volume,factor,change
2020-09-23,SH600000,0.998,1.002,0.997,1.000,125000000,0.987,0.001
2020-09-24,SH600000,1.001,1.005,0.999,1.003,118000000,0.987,0.003
2020-09-25,SH600000,1.002,1.006,1.000,1.004,121000000,0.987,0.001
```

- **字段与 Qlib 表达式**：写入 bin 后，加载时字段名映射为 **`$open`、`$high`、`$low`、`$close`、`$volume`、`$factor`** 等（`$change` 若已 dump 亦可使用，视你是否排除该列而定）。

---

#### 2.6.6 Yahoo 采集的原始 CSV（`collector.py download_data` 输出，`source_dir`，归一化前）

- **说明**：原始列与数据源有关；中国区日频在 `collector.py` 中会整理为包含 **`date`**、**`open`、`close`、`high`、`low`、`volume`**、`money`、`change` 等（具体见脚本内列赋值逻辑）。
- **样例**（演示用）：

```text
date,symbol,open,close,high,low,volume,money,change
2020-09-23,SH600000,10.50,10.55,10.58,10.48,125000000,1312500000.0,0.0048
```

- **下一步**：需经 `normalize_data`（或增量时的 `normalize_data_1d_extend`）再进入 `dump_bin`。

---

#### 2.6.7 官方 `get_data.py qlib_data` 下载的 Zip解压结果

- **说明**：解压到 `target_dir` 后，应呈现与上文一致的 **`calendars/`、`features/`、`instruments/`** 结构；**不包含**「人类可读的全市场一张大表」，行情均在 **`features/*/ *.day.bin`** 中。
- **可选缓存目录**：`features_cache/`、`dataset_cache/` 多为运行 `qlib` 后生成或缓存，**不必**手工维护；整包覆盖下载时可能被 `delete_old` 一并删除。

---

#### 2.6.8 其它常见文件（按需）

| 路径 | 说明 |
|------|------|
| `instruments/*.txt` | 除 `all.txt`、指数成分外，还可能有 `csi100.txt` 等，格式均为 **3 列制表符分隔、无表头**。 |
| PIT 相关 | 若使用 Point-in-Time 财报等，另有 `scripts/data_collector/pit/` 等流程，目录结构与纯行情不完全相同，需单独参考对应 README。 |
| 社区 `qlib_bin.tar.gz` | 解压后同样应对齐 `calendars`、`instruments`、`features` 结构；顶层目录层级需按发布方说明使用 `tar` 的 `--strip-components` 等调整。 |

---

## 3. 方式 A：整包重新下载官方 `qlib_data`（全量替换）

适用于：**不介意覆盖/重建目录**、希望与当前 Qlib 版本匹配的官方打包数据。

### 3.1 命令入口

项目根目录下执行（需已安装本仓库对应版本的 `qlib`）：

```bash
# 日频中国区数据 → 默认目标目录可显式写出
python scripts/get_data.py qlib_data \
  --target_dir ~/.qlib/qlib_data/cn_data \
  --region cn \
  --interval 1d
```

### 3.2 常用参数说明（`GetData.qlib_data`）

| 参数 | 含义 | 典型取值 |
|------|------|----------|
| `name` | 数据集名称 | `qlib_data`（全量）、`qlib_data_simple`（精简） |
| `target_dir` | 解压目标根目录 | `~/.qlib/qlib_data/cn_data` |
| `region` | 区域 | `cn` / `us` 等 |
| `interval` | 频率 | `1d`；分钟线为 `1min`（会下载到另一目录如 `cn_data_1min`） |
| `version` | 远程版本目录 | 如 `v1`、`v2`；默认由脚本按 qlib 版本拼文件名 |
| `delete_old` | 是否删除目标下旧 qlib 数据子目录 | 默认 `True`（删除前可能有交互确认，见源码） |
| `exists_skip` | 若已存在合法 qlib 数据则跳过下载 | `True` 时适合「已有数据不重复下」 |

### 3.3 注意

- **`delete_old=True`** 时可能删除 `features`、`calendars`、`instruments`、缓存等；生产环境请先**备份** `target_dir`。
- 下载 URL 随 `qlib` 版本与 `name/region/interval` 组合变化，具体逻辑见 `qlib/tests/data.py` 中 `qlib_data()`。

---

## 4. 方式 B：社区或其它渠道提供的 `qlib_bin` 压缩包

适用于：使用**非微软官方 `get_data.py` 下载链路**、但仍是 **Qlib 二进制目录结构**（`features/`、`calendars/`、`instruments/` 等）的第三方打包数据。

### 4.1 文档与仓库中明确提到的「社区」渠道

本仓库 README、`scripts/README.md` 与 `scripts/data_collector/crowd_source/README.md` 中指向的社区数据为：

| 说明 | 链接 |
|------|------|
| **GitHub Releases（crowd-sourced qlib bin）** | [https://github.com/chenditc/investment_data/releases](https://github.com/chenditc/investment_data/releases) |
| 常用资产名 | `qlib_bin.tar.gz`（见各 Release 附件；也可用 `releases/latest/download/qlib_bin.tar.gz` 取最新） |
| 维护说明 | 上述仓库内文档与 Docker 构建说明（`crowd_source/README.md`） |

以下为与 `scripts/README.md` 一致的示例（**解压层数以压缩包实际顶层为准**）：

```bash
mkdir -p ~/.qlib/qlib_data/cn_data
wget -O qlib_bin.tar.gz https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz
# 若解压后多套一层目录，常见为 strip-components=2；若解压后已是数据根，则可能为 1 —— 以 ls 结果为准
tar -zxvf qlib_bin.tar.gz -C ~/.qlib/qlib_data/cn_data --strip-components=2
rm -f qlib_bin.tar.gz
```

### 4.1.1 一键脚本：下载社区版并解压到 `cn_data`

下面脚本等价于上一节的分步命令，便于保存为 `download_community_cn_data.sh` 后执行，或通过 `bash -s` 管道运行。默认目标目录为 `~/.qlib/qlib_data/cn_data`；可将**第一个参数**设为其它路径。

**说明**：`tar` 的 `--strip-components` 取决于 Release 包内顶层目录层数。本仓库根目录 `README.md` 的「Data Preparation」示例使用 **`1`**；`scripts/data_collector/crowd_source/README.md` 使用 **`2`**。解压后请在 `target` 下确认已出现 `calendars/`、`features/`、`instruments/`；若多一层空壳目录，请调整该数值后删除错误内容再重新解压。

```bash
#!/usr/bin/env bash
# 从社区 investment_data Release 下载 Qlib 二进制包并解压为中国区数据根目录（cn_data）
set -euo pipefail

TARGET="${1:-${HOME}/.qlib/qlib_data/cn_data}"
# 与 crowd_source/README.md 一致；若解压后结构不对可改为 1（见项目根 README 示例）
STRIP_COMPONENTS="${STRIP_COMPONENTS:-2}"
URL="https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz"
ARCHIVE="${TMPDIR:-/tmp}/qlib_bin_community_$$.tar.gz"

mkdir -p "${TARGET}"
wget -O "${ARCHIVE}" "${URL}"
tar -zxvf "${ARCHIVE}" -C "${TARGET}" --strip-components="${STRIP_COMPONENTS}"
rm -f "${ARCHIVE}"

echo "完成。请检查: ls \"${TARGET}\" 是否包含 calendars features instruments"
```

使用示例：

```bash
# 默认 ~/.qlib/qlib_data/cn_data
bash download_community_cn_data.sh

# 指定目录
bash download_community_cn_data.sh /data/qlib/cn_data

# 需要与根目录 README 相同的 strip 层数时
STRIP_COMPONENTS=1 bash download_community_cn_data.sh
```

### 4.2 「其它渠道」指什么

指**任意发布方**提供的、与本文第 2 节目录约定一致的 Qlib 二进制包或同步目录（例如论坛网盘、机构内部分享、个人镜像等）。**微软不背书这些包的内容与更新节奏**；使用前请自行核对字段、日期范围与 `strip-components`。

解压后请确认**数据根目录**下直接（或经一层子目录）出现 `features/`、`calendars/`、`instruments/` 等。不同发布包 `tar` 的 `--strip-components` 可能为 `1` 或 `2`，需按实际包内路径调整。

---

## 5. 方式 C：Yahoo Finance 全量自建（下载 → 归一化 → `dump_all`）

适用于：**需要从零构建**、或要与官方包字段/口径一致地重建整库。数据源为 Yahoo（**中国大陆网络常无法直接访问**，需自备可用网络环境）。

**官方说明位置**：`scripts/data_collector/yahoo/README.md`。

### 5.1 环境与依赖

```bash
cd scripts/data_collector/yahoo
pip install -r requirements.txt
```

若使用 **Conda** 管理 Python：建议环境名为 **`ai-trade`**（与作为 **ai-trading-coach** 子模块时的父仓库 `environment.yml` 一致）。第 6 节的一键增量脚本 `run_cn_incremental_update.sh` 默认也会 `conda activate` 该名；若你使用其它环境名，运行脚本前设置环境变量 **`CONDA_ENV`** 即可。

后续命令若在仓库根目录执行，注意 `collector.py` 的路径为 `scripts/data_collector/yahoo/collector.py`。

### 5.2 步骤 1：下载原始 CSV

```bash
cd /path/to/qlib/scripts/data_collector/yahoo

# 示例：中国区日频，时间区间按需求修改
python collector.py download_data \
  --source_dir ~/.qlib/stock_data/source/cn_data \
  --start 2000-01-01 \
  --end 2026-12-31 \
  --delay 1 \
  --interval 1d \
  --region CN
```

**参数要点**：

- `region`：`CN` / `US` / `IN` / `BR` 等。
- `interval`：`1d` 或 `1min`（**1 分钟数据**受 Yahoo API 限制，通常仅最近约一个月）。
- `max_workers`：默认 `1`，为保证单标的数据完整性，**不建议随意调大**（下载阶段）。
- `start`：**闭区间**（含起点）；`end`：**开区间**（不含终点），默认约为「当前时间 + 1 天」。

### 5.3 步骤 2：归一化（价格与 adjclose 等处理）

日频中国区示例：

```bash
python collector.py normalize_data \
  --source_dir ~/.qlib/stock_data/source/cn_data \
  --normalize_dir ~/.qlib/stock_data/source/cn_1d_nor \
  --region CN \
  --interval 1d
```

**1 分钟数据**归一化时**必须**提供已有日频 Qlib 目录（`qlib_data_1d_dir`），因脚本需与日线对齐处理。

### 5.4 步骤 3：写入 Qlib 二进制（全量 `dump_all`）

在 **`scripts` 目录**下执行（因 `dump_bin` 模块路径历史原因，常与文档一致在 `scripts` 下调用）：

```bash
cd /path/to/qlib/scripts

python dump_bin.py dump_all \
  --data_path ~/.qlib/stock_data/source/cn_1d_nor \
  --qlib_dir ~/.qlib/qlib_data/cn_data \
  --freq day \
  --exclude_fields date,symbol \
  --file_suffix .csv
```

**参数要点**：

- `data_path`：归一化后的 CSV 目录。
- `qlib_dir`：Qlib 数据根目录（可与官方示例同为 `~/.qlib/qlib_data/cn_data`）。
- `freq`：日频为 `day`；分钟线为 `1min`（与 README 中 `freq_map` 一致）。
- `exclude_fields`：排除非特征列（常见 `symbol,date`）。

### 5.5 数据质量提示

Yahoo 数据可能存在缺失、异常跳点；README 中列举了部分异常标的示例。生产使用建议配合 **`scripts/check_data_health.py`** 或自有校验规则。

---

## 6. 方式 D：Yahoo 日频增量更新（推荐用于「每日追加」）

适用于：**你已经用 Yahoo 流程建好了完整的 `qlib_dir`**，只需在每个交易日之后把新数据追加进同一目录。

### 6.1 手动执行在 `scripts/data_collector/yahoo` 目录下（或与文档一致指定模块路径）

**一键脚本（`conda` + 日志 + 可选健康检查；不设代理环境变量，网络依赖本机路由/VPN）**：仓库内 **`scripts/data_collector/yahoo/run_cn_incremental_update.sh`**。用法见脚本头部注释；简例：

- **Conda 环境名**：脚本执行前会激活 Conda；默认 **`CONDA_ENV=ai-trade`**（与 **ai-trading-coach** 父仓库约定一致）。若本机环境名不同，例如 `CONDA_ENV=myqlib ./run_cn_incremental_update.sh …`。

```bash
cd /path/to/qlib/scripts/data_collector/yahoo
chmod +x run_cn_incremental_update.sh   # 首次
./run_cn_incremental_update.sh ~/.qlib/qlib_data/cn_data
# 或：END_DATE=2026-04-18 SKIP_HEALTH=1 ./run_cn_incremental_update.sh
```

**等价的手动 Python 调用**：

```bash
cd /path/to/qlib/scripts/data_collector/yahoo

python collector.py update_data_to_bin \
  --qlib_data_1d_dir ~/.qlib/qlib_data/cn_data \
  --end_date 2026-04-13
```

**参数说明（摘自实现与 README）**：

| 参数 | 含义 |
|------|------|
| `qlib_data_1d_dir` | 要被更新的 Qlib 日频数据根目录 |
| `end_date` | 结束时间（**开区间，不包含该日**）；默认行为与「最后一交易日」推导有关，详见源码 |
| `region` | 默认 `CN`；亦支持 `US` 等（指数成分更新逻辑对非 cn/us 会跳过） |
| `interval` | **仅支持 `1d` 增量**（脚本内会对非 1d 给出警告） |
| `delay` | 请求间隔，默认 `1` |
| `check_data_length` | 若设置，则少于该行数会重试拉取 |
| `exists_skip` | 若目录已有合法 qlib 数据是否跳过「自动下载基础包」；与 `GetData.qlib_data` 联动 |

**内部流程概要**（`collector.py` 中 `update_data_to_bin`）：

1. 若 `qlib_data_1d_dir` 尚不完整，可调用 `GetData().qlib_data(...)` 拉取官方包打底（受 `exists_skip` 等影响）。
2. 读取 `calendars/day.txt` 推断上次交易日，从 Yahoo 下载增量区间 CSV。
3. 归一化（`normalize_data_1d_extend`）。
4. 使用 **`DumpDataUpdate`** 将归一化结果合并进现有 `features`，并更新日历与 `instruments`。
5. 对 `cn` 尝试更新 **CSI100 / CSI300** 等成分；`us` 则更新 SP500 等相关指数列表。

### 6.2 定时任务（Linux `crontab`示例）

README 示例（工作日每分钟槽位仅为示例，实际应改为收盘后固定时间，并写好绝对路径与日志）：

```cron
# 每周一到五执行（请把路径改成你的机器路径）
0 16 * * 1-5 cd /path/to/qlib/scripts/data_collector/yahoo && /path/to/python collector.py update_data_to_bin --qlib_data_1d_dir /home/yourname/.qlib/qlib_data/cn_data >> /tmp/qlib_cn_update.log 2>&1
```

建议：

- 在**交易所日历确认当日为交易日**后再跑，或使用你自己的调度判断。
- 首次跑通前务必**备份**整个 `qlib_data_1d_dir`。

### 6.3 增量失败与数据缺口

源码注释说明：若本地数据不完整，某些情况下会用 **`np.nan` 填充**到上一交易日等（详见 `update_data_to_bin` 文档字符串）。若长期依赖增量，应定期做 **全量校验** 或对账。

### 6.4 查看更新日志

增量任务若在前台运行，日志会直接打在终端；**后台或定时任务**应把输出重定向到文件，便于排查进度与告警。

| 运行方式 | 日志常见位置 | 说明 |
|----------|--------------|------|
| **`run_cn_incremental_update.sh`**（默认） | `~/.qlib/logs/cn_incremental_YYYYMMDD_HHMMSS.log` | 脚本启动时会 `echo` 打印完整路径；可通过环境变量 **`LOG_DIR`**、**`LOG_FILE`** 覆盖默认路径（见脚本头部注释）。 |
| **`crontab` 重定向**（本文 6.2 示例） | `/tmp/qlib_cn_update.log` | 路径可自定，建议固定为长期保留路径并做好 **logrotate** 或定期清理。 |
| **手动 `nohup` / 管道** | 例如 `/tmp/qlib_cn_incremental.log` | 与 `collector.py update_data_to_bin >>某文件 2>&1` 中写的路径一致即可。 |

**实时查看末尾输出**（适合长任务）：

```bash
# 一键脚本：启动时会在终端打印「日志: …」；也可先取最新一份再跟踪（无匹配文件时会报错，需先跑过至少一次）
tail -f "$(ls -t "${HOME}/.qlib/logs"/cn_incremental_*.log 2>/dev/null | head -1)"

# crontab / nohup 里若重定向到固定文件，直接跟踪该路径即可
tail -f /tmp/qlib_cn_update.log
```

**注意**：采集阶段若使用 **tqdm** 进度条，单行会用回车符 `\r` 刷新，直接用 `tail` 可能看到「挤在一行」的乱序文本。可读末尾进度时改用：

```bash
tail -c 8000 /path/to/your.log | tr '\r' '\n' | tail -25
```

**日志里常见关键字**（便于判断是否正常）：

- **标的列表**：东方财富失败时可能回退 **Baostock**，仍应看到最终 `get N symbols` 一类 INFO。
- **Yahoo**：若出现 **`GFW` / `firewall` / `Your data request fails`**，多为网络无法访问 Yahoo，需调整代理或路由；部分标的会 **`is empty`** 或重试告警。
- **任务是否仍在跑**：`pgrep -af 'update_data_to_bin'` 有进程则说明尚未结束；结束后可对比 **`calendars/day.txt` 最后一行**是否已推进到预期交易日。

---

## 7. 分钟线 `cn_data_1min` 相关（简要）

- 官方下载：`get_data.py qlib_data --interval 1min --target_dir ~/.qlib/qlib_data/cn_data_1min --region cn`。
- Yahoo **1min** 采集受 API 限制，通常只有短期数据；仓库另有 `scripts/data_collector/contrib/fill_cn_1min_data/` 等补充说明，可与日线目录配合使用。
- **初始化时** `provider_uri` 指向分钟线目录，`D.features(..., freq="1min")`。

---

## 8. 更新后建议自检

### 8.1 `check_data_health.py`

```bash
cd /path/to/qlib/scripts
python check_data_health.py check_data --qlib_dir ~/.qlib/qlib_data/cn_data --freq day
```

更多参数（如缺失行数阈值、跳变阈值）见项目根目录 `README.md` 与 `docs/component/data.rst` 中的示例；也可用 `python check_data_health.py --help` 查看 Fire 暴露的子命令。

### 8.2 `check_dump_bin.py`

若你从 CSV 自行 `dump_bin`，可用 `scripts/check_dump_bin.py` 对比 CSV 与 bin 一致性（见脚本内说明）。

### 8.3 特征目录大小写（Linux）

`check_data_health.py` 中注释：在**大小写敏感**文件系统上，`features/` 下子目录名需与 Qlib 期望一致（全小写等），否则可能加载失败（参见脚本内 issue 链接）。若从 Windows 拷贝数据到 Linux，需特别检查。

---

## 9. 常见问题（FAQ）

**Q1：我只用官方 `get_data` 下过一次，能否直接 `update_data_to_bin`？**  
A：文档倾向 **否**——官方包可能缺字段，增量逻辑面向 **Yahoo 自建完整链路** 的数据。稳妥做法是：按方式 C 重建，或接受方式 A 定期整包覆盖。

**Q2：增量更新后回测结果和官方包不一致？**  
A：可能来自复权、缺失填充、Yahoo 源质量、指数成分更新时点等。应用层应对齐数据源与复权口径，并做样本对账。

**Q3：不用 Yahoo，用 Tushare/Baostock 等可以吗？**  
A：可以，但需自行实现「下载 → 与 Qlib 字段对齐的 CSV → `dump_bin`」；仓库中另有 `data_collector` 下不同数据源示例，可对照字段表实现。

**Q4：`target_dir` 可以换吗？**  
A：可以，`provider_uri` 与所有脚本中的 `--qlib_dir` / `--qlib_data_1d_dir` 改成你的路径即可，**保持一致**即可。

---

## 10. 参考路径（本仓库内）

| 文件 | 内容 |
|------|------|
| `scripts/README.md` | `get_data`、初始化示例、社区包解压 |
| 本文第 4.1.1 节 | 社区 Release 一键下载解压到 `cn_data` 的 shell 脚本 |
| `scripts/data_collector/README.md` | 数据集字段与目录约定总览 |
| `scripts/data_collector/yahoo/README.md` | Yahoo 下载、归一化、`dump_all`、`update_data_to_bin`、crontab |
| `scripts/data_collector/yahoo/run_cn_incremental_update.sh` | 中国区日频增量 Shell 入口；默认日志见本文 **6.4** |
| 本文 **6.4** | 增量更新日志路径、`tail`跟踪、`tr` 展开 tqdm 的 `\r` 行、常见告警与进程检查 |
| `scripts/dump_bin.py` | `dump_all` / `dump_fix` / `dump_update` |
| `qlib/tests/data.py` | `GetData.qlib_data` 下载逻辑与参数 |
| `scripts/check_data_health.py` | 数据健康检查 |

---

*文档版本：与 Qlib 仓库脚本同步整理；若上游 CLI 变更，请以 `--help` 与源码为准。*
