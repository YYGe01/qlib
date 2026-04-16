# `qrun benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml` 数据流说明

本文档描述在该命令下**数据从哪里来、经过哪些阶段、变成什么形态、最终写到哪里**，不展开源码实现细节。默认你在仓库中执行：

```bash
cd examples
qrun benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml
```

工作流配置文件路径：`examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`（相对仓库根目录）。

---

## 一、流程总览（先见森林）

| 阶段 | 做什么 | 数据上发生了什么 |
|------|--------|------------------|
| 1. 启动与初始化 | 读取 YAML、`qlib.init` | 指定**行情数据源根目录**与**实验区**（实验跟踪目录） |
| 2. 构建数据集 | `Alpha158` + `DatasetH` | 从二进制行情库**读取原始字段** → 计算 **158 维因子**与 **标签列** → 按时间切成 train/valid/test |
| 3. 训练 | `LGBModel.fit` | **训练段**（及需要时的验证段）上的 `(特征矩阵, 标签)` → **拟合好的模型**（内存 + 随后写入实验产物） |
| 4. 预测 | `model.predict` | **测试段**上的特征 → **逐日、逐股票的预测分数**（signal / score） |
| 5. 信号落盘 | `SignalRecord` | 预测分数、测试段标签等 → **写入当前 Recorder 的 artifact** |
| 6. 信号分析 | `SigAnaRecord` | 预测 vs 标签 → **IC / Rank IC 等序列与标量指标** |
| 7. 组合回测 | `PortAnaRecord` | 预测分数作为策略输入 → **调仓、成交、净值、相对基准的超额** → 风险指标与报表文件 |

---

## 二、数据流示意图

```mermaid
flowchart LR
 subgraph inputs["外部输入"]
        BIN["Qlib 二进制行情目录\n~/.qlib/qlib_data/cn_data"]
        YAML["workflow_config_lightgbm_Alpha158.yaml"]
    end

    subgraph qlib_core["Qlib 运行时"]
        INIT["qlib.init\n挂载数据提供方"]
        H["Alpha158 数据处理器\n特征 + 标签"]
        DS["DatasetH\n按 segments 切片"]
        M["LGBModel\nfit / predict"]
    end

    subgraph outputs["输出产物"]
        ML["实验目录 mlruns/\n(默认在当前工作目录下)"]
        PRED["pred.pkl\n预测分数"]
        SIG["sig_analysis/\nic.pkl, ric.pkl …"]
        PORT["portfolio_analysis/\nreport_*, positions_*, port_analysis_* …"]
    end

    YAML --> INIT
    BIN --> INIT
    INIT --> H
    H --> DS
    DS --> M
    M --> PRED
    PRED --> SIG
    PRED --> PORT
    PRED --> ML
    SIG --> ML
    PORT --> ML
```

---

## 三、各阶段：输入 / 中间数据形态 / 输出（含举例）

### 阶段 1：配置与数据根目录

**输入**

- **YAML 文件**：`examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`
  - `qlib_init.provider_uri`：一般为 `~/.qlib/qlib_data/cn_data`（展开为用户主目录下的绝对路径）
  - `qlib_init.region`：`cn`
- **本地行情数据**：上述 `provider_uri` 目录中已准备好的 Qlib 日线二进制数据（各标的、各字段的分区文件，由官方或社区工具事先下载/转换得到）

**输出（逻辑上）**

- 进程内：**数据提供方**指向该 `provider_uri`，后续所有 `D.features`、DataLoader 读取均从这里取数。
- **实验跟踪根 URI**：若配置里未单独写 `exp_manager`，CLI 会把实验文件落在**当前工作目录**下的 `mlruns/`（`file:<cwd>/mlruns`）。

**举例**

- `provider_uri` 解析后类似：`/home/yourname/.qlib/qlib_data/cn_data`
- 若你在 `/root/qlib/examples` 下执行 `qrun`，则默认实验目录为：`/root/qlib/examples/mlruns/`

---

### 阶段 2：Alpha158 特征与标签

**输入**

- **股票池**：YAML 中 `market: csi300`，数据处理器使用 `instruments: csi300`（沪深 300 成分口径由 Qlib 数据与 `instruments` 定义共同决定）。
- **时间范围**（与配置一致）：
  - 行情与因子加载总窗口：`start_time`～`end_time`（如 2008-01-01～2020-08-01）
  - 处理器拟合窗口：`fit_start_time`～`fit_end_time`（用于部分预处理/归一化在训练期上 fit）
- **原始行情字段**：由 `Alpha158` 内部配置的 `QlibDataLoader` 从二进制库中读取（如开高低收、成交量、复权价等，具体字段集合由 Alpha158 因子定义决定）。

**中间数据（概念形态）**

- **特征表**：在 `(日期 × 股票)` 上展开，约 **158 列**因子（名称由 Alpha158 规则生成，如各类价量、均线、波动等），供 `learn` / `infer` 使用。
- **标签列**：默认 **`LABEL0`**，由收盘价表达式在加载时计算（**不是**原始 bin 里的现成字段；详见下节）。

**举例（结构说明，非真实数值）**

- 某一行可理解为：`(datetime=2014-06-03, instrument=SH600000)` 对应 `158` 个特征值 + `LABEL0`。

### 标签列 LABEL0：含义、数值例子与来源

> **公式写法**：行内公式使用 `$ … $`；独立展示的公式使用单独成段的 `$$ … $$`（上下各空一行），便于在 GitHub、VS Code 等环境中一致渲染。

**定义（Alpha158 默认）**  
`Alpha158` 在 `qlib.contrib.data.handler` 中将标签配置为：

- **表达式**：`Ref($close, -2) / Ref($close, -1) - 1`
- **列名**：`LABEL0`

官方文档（`docs/component/data.rst`）说明：该标签表示 **T+1 日收盘到 T+2 日收盘** 的相对收益，而不是「T 收盘 → T+1 收盘」。常见解释是 A 股交易习惯：**在 T 日收盘得到信号 → T+1 才能买入 → T+2 才能卖出**，因此用 **T+1→T+2** 这段收益作为监督目标，更贴近可交易窗口。

记样本在日历上对应交易日为 **T**，**T+1**、**T+2** 为紧随其后的两个交易日；$C_{T+1}$、$C_{T+2}$ 分别为 **T+1**、**T+2** 日的收盘价。则标签在数值上等价于：

$$
\mathrm{LABEL0} = \frac{C_{T+2}}{C_{T+1}} - 1
$$

与 Qlib 表达式 **`Ref($close, -2) / Ref($close, -1) - 1`** 在「以收盘价为基准、按交易日对齐」的前提下一致。

**数值例子**

- **例 1（上涨）**：$C_{T+1} = 10.00,\; C_{T+2} = 10.20$。

$$
\mathrm{LABEL0} = \frac{10.20}{10.00} - 1 = 0.02
$$

即约 **+2%**。

- **例 2（下跌）**：$C_{T+1} = 20.00,\; C_{T+2} = 19.60$。

$$
\mathrm{LABEL0} = \frac{19.60}{20.00} - 1 = -0.02
$$

即约 **-2%**。

**怎么来的**

1. **原始 Qlib 二进制数据**中通常有 **`$close`**（复权收盘价等）等基础行情序列，**一般没有**名为 `LABEL0` 的单独存储列。
2. **`QlibDataLoader`** 在 DataHandler 拉数时，通过 **Qlib 表达式引擎** 对 `$close` 计算 `Ref(...)`，**现场生成** `LABEL0`，再与特征一起进入 `DatasetH` /模型训练。
3. 若使用 **`Alpha158vwap`**，默认标签为 `Ref($vwap, -2)/Ref($vwap, -1) - 1`，列名仍为 `LABEL0`，仅价格字段从收盘价改为 VWAP。

**小结**

| 项目 | 说明 |
|------|------|
| 列名 | `LABEL0`（Alpha158 默认） |
| 与特征同日索引 T 对应的含义 | 约等于 **T+1 收盘 → T+2 收盘** 的收益率 |
| 原始 `cn_data` bin 里有没有 `LABEL0` | **通常没有**；有 **`$close`** 等基础字段，由框架 **派生** |

---

### 阶段 3：DatasetH 时间切分

**输入**

- 上一步处理器生成的统一数据视图。
- YAML 中 `task.dataset.kwargs.segments`：

```yaml
train: [2008-01-01, 2014-12-31]
valid: [2015-01-01, 2016-12-31]
test:  [2017-01-01, 2020-08-01]
```

**输出（逻辑形态）**

- **train**：仅落在训练段日期范围内、且属于股票池的样本，用于 `LGBModel.fit` 的主要拟合。
- **valid**：验证段样本，是否参与拟合取决于 `LGBModel` 实现（LightGBM 常可用验证集做 early stopping；以当前 contrib 实现为准）。
- **test**：测试段样本，**不参与训练**，仅用于 `predict` 与后续分析/回测。

**举例**

- train 段某日可能包含约 300 只成分股 × 该日有效样本；test 段从 2017-01-01 起用于生成**样本外预测**。

---

### 阶段 4：模型训练与预测

**输入**

- **训练（及可能的验证）**：`DatasetH` 提供的特征张量/表与 `LABEL0`。
- **测试**：同上的特征部分（测试段）。

**输出**

- **内存中**：拟合后的 `LGBModel`（梯度提升树集成）。
- **预测**：对 **test 段**每个 `(datetime, instrument)` 输出一个**连续分数**（分数越高通常表示模型越看多该标的的相对收益）。

**举例（预测表结构）**

- `pred.pkl` 中对象多为 `pandas.DataFrame`：
  - **索引**：多级索引 `(instrument, datetime)`（层级名一般为 `instrument`、`datetime`）。
  - **列名**：常见为 `score`（或由模型输出列转换而来）。
- 示例行（虚构数值）：

| instrument | datetime   | score   |
|------------|------------|---------|
| SH600000   | 2017-01-03 | 0.0312  |
| SH600000   | 2017-01-04 | -0.0084 |
| SZ000001   | 2017-01-03 | 0.0156  |

---

### 阶段 5：SignalRecord（信号与标签落盘）

**输入**

- 训练好的 `model` 与 `dataset`（其中 dataset 仍可按需取出测试段标签）。

**输出（写入当前 Recorder）**

- **`pred.pkl`**：测试段预测分数（见上表）。
- **`label.pkl`**：与预测对齐的测试段**原始标签**（`LABEL0`），用于后续 IC 与多空分析等。

**数据流关系**

- `pred.pkl` 与 `label.pkl` 在 **test 时间范围**内按 `(instrument, datetime)` 对齐后，供 `SigAnaRecord` 计算 IC。

---

### 阶段 6：SigAnaRecord（信号质量分析）

**输入**

- `pred.pkl` 第一列：预测分数（常见列名 `score`）。
- `label.pkl` 用于分析的列：默认第 0 列（Alpha158 多为 `LABEL0`）。

**输出**

- **Metrics**（如 MLflow）：默认含 `IC`、`ICIR`、`Rank IC`、`Rank ICIR`；`ana_long_short: False` 时不记多空扩展指标。
- **`sig_analysis/`**：`ic.pkl`、`ric.pkl` 等为**按日**序列，便于作图。

---

#### 统一前提：横截面、按日

- 预测与标签在 **test 段**按 `(instrument, datetime)` 对齐。
- **每个交易日** $t$ 单独取当日所有股票的 $(x_i,y_i)=(\text{pred}_{t,i},\,\text{label}_{t,i})$，在这一批点上算相关，得到**该日一个**日度 IC 与日度 Rank IC；**不是**单只股票沿时间算相关。
- 实现：`qlib.contrib.eva.alpha.calc_ic`；按 `datetime` 分组后，`corr()` 为 Pearson，`corr(method="spearman")` 为 Rank IC。

---

#### 公式：日度 IC（Pearson）与日度 Rank IC（Spearman）

设某日有 $n$ 只股票，$x_i$ 为预测，$y_i$ 为标签，$\bar{x}=\frac{1}{n}\sum_i x_i$，$\bar{y}=\frac{1}{n}\sum_i y_i$。**该日 IC**（Pearson 样本相关系数，与 `pandas.Series.corr` 默认一致）为：

$$
r_t=\frac{\sum_{i=1}^{n}(x_i-\bar{x})(y_i-\bar{y})}{\sqrt{\sum_{i=1}^{n}(x_i-\bar{x})^2}\,\sqrt{\sum_{i=1}^{n}(y_i-\bar{y})^2}}
$$

**该日 Rank IC**：先给每只股票算出两个整数或半整数**秩** $\mathrm{rk}^x_i$、$\mathrm{rk}^y_i$（见下），再把 Pearson 公式里的 $(x_i,y_i)$ 换成 $(\mathrm{rk}^x_i,\mathrm{rk}^y_i)$ 算相关系数，即 Spearman；Qlib 中对该日 `corr(method="spearman")` 与此一致。

**股票 $i$ 的秩 $\mathrm{rk}^x_i$、$\mathrm{rk}^y_i$ 怎么算（只谈「某一个交易日」）**

- **$\mathrm{rk}^x_i$（预测秩）**：这一天的横截面上，把所有股票的预测 $x$ **放在一起**，按 $x$ **从小到大**排队。  
  - $x$ **最小**的那只，$\mathrm{rk}^x=1$；**第二小**的，$\mathrm{rk}^x=2$；……**最大**的，$\mathrm{rk}^x=n$。  
  - 股票 $i$ 在这一天里排第几名，它的 $\mathrm{rk}^x_i$ 就是几（**名次从 1 开始**，与 pandas `rank(method="average")` 一致）。
- **$\mathrm{rk}^y_i$（标签秩）**：**完全另算一遍**：只看各只股票的 $y$，仍按 $y$ **从小到大**排队，同样得到 $1\sim n$ 的名次；这只股票在「按 $y$ 排队」里第几名，就是 $\mathrm{rk}^y_i$。  
- **要点**：$\mathrm{rk}^x$ 与 $\mathrm{rk}^y$ 是**两套独立排名**——先按预测排一次名，再按真实收益排一次名；**不是**把 $(x,y)$ 绑在一起排序。

**并列（两只股票预测一样）**：若按 $x$ 从小到大数，它们本应占第 $k$、$k+1$ 名，则这两只的 $\mathrm{rk}^x$ **都取平均** $\dfrac{k+(k+1)}{2}=k+\dfrac{1}{2}$。标签 $y$ 并列同理。

**对照后面「第 1 日」四只股票表**：$x$ 为 $0.10,0.20,0.30,0.40$，从小到大已是 A→B→C→D，故 $\mathrm{rk}^x$：A=1，B=2，C=3，D=4。$y$ 为 $0.01,0.02,0.03,0.04$，同理 $\mathrm{rk}^y$：A=1，B=2，C=3，D=4。得到四对 $(\mathrm{rk}^x,\mathrm{rk}^y)=(1,1),(2,2),(3,3),(4,4)$，再代入上面的 Pearson 式（把 $x,y$ 换成这两列秩），即该日 Rank IC。

---

#### 由日度序列到四个 Metrics

记第 $t$ 日的 Pearson 结果为 $r_t$，Spearman 结果为 $\rho_t$（各日一条，分别对应 `ic.pkl`、`ric.pkl`）。**样本标准差**取 $\mathrm{std}$ 的默认（分母 $n-1$，与 pandas 一致）。

| Metrics | 计算 |
|---------|------|
| **IC** | $\displaystyle \overline{r}=\frac{1}{T}\sum_{t=1}^{T} r_t$ |
| **ICIR** | $\displaystyle \overline{r}\,/\,\mathrm{std}(r_1,\ldots,r_T)$ |
| **Rank IC** | $\displaystyle \overline{\rho}=\frac{1}{T}\sum_{t=1}^{T} \rho_t$ |
| **Rank ICIR** | $\displaystyle \overline{\rho}\,/\,\mathrm{std}(\rho_1,\ldots,\rho_T)$ |

**边界**：$n<2$ 或当日某列方差为0 时该日相关无定义，常为 `NaN`；解读整体指标时宜看日度序列是否大量缺失。

---

#### 一个算例（三日、每日四只股票）：从原始表算到四个指标

下表为虚构的 **3 个交易日**，股票均为 A～D，仅用于演示计算；真实回测中每日约有数百只股票。

**第 1 日**（预测与标签同向、近似成比例）

| 股票 | $x$（pred） | $y$（label） |
|------|------------|-------------|
| A | 0.10 | 0.01 |
| B | 0.20 | 0.02 |
| C | 0.30 | 0.03 |
| D | 0.40 | 0.04 |

代入 Pearson 公式：$\bar{x}=0.25$，$\bar{y}=0.025$，分子 $\sum_i(x_i-\bar{x})(y_i-\bar{y})=0.005$，分母 $\sqrt{0.05}\cdot\sqrt{0.0005}=0.005$，故 **$r_1=1$**。  
秩：$x$、$y$ 均为从小到大 $1,2,3,4$，对秩套用同一公式得 **$\rho_1=1$**。

**第 2 日**（预测与标签反向：预测越高、收益越低）

| 股票 | $x$ | $y$ |
|------|-----|-----|
| A | 0.40 | 0.01 |
| B | 0.30 | 0.02 |
| C | 0.20 | 0.03 |
| D | 0.10 | 0.04 |

完全反向单调，故 **$r_2=-1$**，**$\rho_2=-1$**。

**第 3 日**（排序仍一致，但 $D$ 的 `label` 极端大，拉低 Pearson、不改变秩）

| 股票 | $x$ | $y$ |
|------|-----|-----|
| A | 0.10 | 0.01 |
| B | 0.20 | 0.02 |
| C | 0.30 | 0.03 |
| D | 0.40 | 2.00 |

- **Rank IC**：$x$ 的秩为 $1,2,3,4$；$y$ 仍为 $0.01<0.02<0.03<2.00$，秩亦为 $1,2,3,4$，故 **$\rho_3=1$**。  
- **IC（Pearson）**：$\bar{x}=0.25$，$\bar{y}=0.515$，分子 $\sum_i(x_i-\bar{x})(y_i-\bar{y})=0.299$，$\sum_i(x_i-\bar{x})^2=0.05$，$\sum_i(y_i-\bar{y})^2=2.9405$，故  $$r_3=\frac{0.299}{\sqrt{0.05\times 2.9405}}\approx 0.7798$$
可见：**排序全对时 Rank IC 仍为 1，但极端收益会削弱线性相关，IC 明显小于 1**。

**汇总四个 Metrics**（$T=3$，日度序列 $r=(1,\,-1,\,0.7798)$，$\rho=(1,\,-1,\,1)$）：

- **IC** $\;=\frac{1+(-1)+0.7798}{3}\approx 0.260$
- **ICIR** $\;=\dfrac{0.260}{\mathrm{std}(1,-1,0.7798)}\approx\dfrac{0.260}{1.097}\approx 0.237$（分母为样本标准差，$n-1=2$）
- **Rank IC** $\;=\frac{1+(-1)+1}{3}=\frac{1}{3}\approx 0.333$
- **Rank ICIR** $\;=\dfrac{1/3}{\mathrm{std}(1,-1,1)}=\dfrac{1/3}{\sqrt{4/3}}\approx 0.289$

（若用程序逐位核对，$r_3$ 约为 $0.779786$，IC、ICIR 与上式会有末位差异。）

---

**与 `LABEL0`**：`label` 为真实未来段收益（见上文 LABEL0）；上述 $y$ 在实盘中即与之对齐的列。

**可选 `ana_long_short: True`**：额外写入多空分位组合等收益类 Metrics；Alpha158 默认多为关。

**运行现象**：控制台可见 `IC: 0.04xx` 等；`ic.pkl` / `ric.pkl` 为日度序列。

---

### 阶段 7：PortAnaRecord（组合回测与风险分解）

**输入**

- **`pred.pkl`**：作为策略配置里占位符 `<PRED>` 的**实时信号源**（YAML 中 `strategy.kwargs.signal: <PRED>`）。
- **回测配置** `port_analysis_config`：
  - 策略：`TopkDropoutStrategy`，`topk: 50`，`n_drop: 5`（每日保留预测分最高的约 50 只，并淘汰 5 只）。
  - 回测区间：`2017-01-01`～`2020-08-01`，初始资金 `1e8`，基准 `SH000300`。
  - 费率：`open_cost` / `close_cost` / `limit_threshold` / `deal_price: close` 等（决定成交与成本）。

**中间过程（数据语义）**

- 每个交易日：根据**预测分**生成目标持仓 → 模拟撮合（日线、收盘价成交等）→ 更新账户与持仓。
- 相对基准计算超额收益序列（含费与不含费两套）。

**输出（默认日线频率下常见文件名，在 `portfolio_analysis/` 下）**

- `report_normal_1day.pkl`：组合净值、基准、成本、收益等**日频报表**。
- `positions_normal_1day.pkl`：**持仓与成交相关明细**。
- `port_analysis_1day.pkl`：对超额收益做 `risk_analysis` 后的**风险指标表**（含无成本与有成本超额）。
- 可能还有 `indicators_normal_1day.pkl` 等扩展指标。

**Metrics 举例（记入实验跟踪）**

- 键名通常为带频率前缀的扁平化指标，例如：
  - `1day.excess_return_with_cost.annualized_return`
  - `1day.excess_return_with_cost.information_ratio`
  - `1day.excess_return_with_cost.max_drawdown`
- 控制台会 `pprint` 基准收益、超额（无成本）、超额（有成本）的风险摘要。

---

## 四、本工作流在磁盘上的典型产物结构

默认实验名 **`workflow`**（若 YAML 未覆盖 `experiment_name`），在 `examples/mlruns/` 下可看到类似：

```text
mlruns/
  └── <experiment_id>/
        └── <run_id>/
              ├── artifacts/
              │     ├── pred.pkl
              │     ├── label.pkl
              │     ├── params.pkl          # 序列化模型
              │     ├── dataset             # 数据集配置/句柄（非原始行情全量）
              │     ├── sig_analysis/
              │     └── portfolio_analysis/
              ├── metrics/                  # IC、回测风险等指标
              └── ... # 其他跟踪元数据
```

另：运行结束时还会把**完整 task 配置**存成 artifact（便于复现）。

---

## 五、与 YAML 关键字段的一一对应（数据视角）

| YAML 路径 | 在数据流中的作用 |
|-----------|------------------|
| `qlib_init.provider_uri` | 所有行情与因子的**物理数据源根目录** |
| `qlib_init.region` | 市场区域（影响日历、部分默认行为） |
| `market` / `data_handler_config.instruments` | **股票池**，决定哪些标的进入特征与标签表 |
| `data_handler_config.start_time` / `end_time` | 特征与标签加载的**总时间窗** |
| `data_handler_config.fit_*` | 部分处理器仅在此时段上 **fit**，避免信息泄露 |
| `task.dataset.kwargs.segments` | **train/valid/test** 时间边界，决定学习、预测与回测样本范围 |
| `task.model` | 将特征+标签映射为预测分数的**学习器** |
| `task.record` | 预测 → 分析 → 回测的**后处理流水线**及落盘内容 |

---

## 六、小结：一句话数据流

**二进制日线库 → Alpha158 因子与 LABEL0 → 按时间切分 → LightGBM 学习 → 测试段 score → 与标签算 IC → score 驱动 TopK 策略回测 → 净值/超额/风险指标与 pkl 报表写入 `mlruns`。**

---

## 附录：若要自行读取产物（示例）

在 Python 中可从某次 run 加载预测（路径需换为你的 `mlruns` 下真实 `run_id`；若从 `examples` 目录运行 `qrun`，则相对路径常以 `examples/mlruns/...` 为前缀）：

```python
import pandas as pd
pred = pd.read_pickle("mlruns/<exp_id>/<run_id>/artifacts/pred.pkl")
print(pred.head())
```

实际使用时建议通过 `qlib.workflow.R` 与 `Recorder` API 按实验名/recorder id 读取，避免手写路径。
