# Qlib 深度学习工作流：数据流与「喂给神经网络」的输入格式说明

本文档与 [`qrun_Alpha158_数据流说明.md`](./qrun_Alpha158_数据流说明.md) 对照阅读：前半部分沿用「行情 → Handler → 数据集切分 → 训练/预测 → 落盘 → 分析/回测」的叙事；**后半部分聚焦深度学习**：同一套 `(datetime, instrument)` 面板数据，在进入 **树模型（如 LightGBM）** 与 **不同结构的神经网络** 时，**张量形状、批次语义、是否需要 `TSDatasetH`** 有何本质差别，并给出可对照源码的详细样例。

默认你已在仓库中准备好 `cn_data` 等 Qlib 二进制数据；示例命令以官方 `examples/benchmarks` 下的工作流 YAML 为准（路径相对仓库根目录）。

---

## 一、与 LightGBM 工作流相同的部分（简述）

以下阶段与《Alpha158 + LightGBM》文档一致，深度学习只是把 `task.model` 换成了 PyTorch 封装类：

| 阶段 | 内容 |
|------|------|
| 初始化 | `qlib.init`：`provider_uri`、`region`、实验目录等 |
| Handler | `Alpha158` / `Alpha360` 等：从二进制库取原始字段 → 计算特征列与标签（如 `LABEL0`） |
| 切分 | `DatasetH` / `TSDatasetH` 的 `segments`：`train` / `valid` / `test` |
| 记录 | `SignalRecord` → `SigAnaRecord` → `PortAnaRecord`，产物仍在 `mlruns/` 下 |

**标签含义**（与树模型文档一致）：`Alpha158` 默认 `LABEL0 = Ref($close, -2) / Ref($close, -1) - 1`，对应可交易窗口下的 T+1→T+2 收益；Handler 侧处理（`learn_processors` / `infer_processors`）同样影响深度模型看到的标签尺度（如 `CSZScoreNorm`、`CSRankNorm`）。

---

## 二、核心对比：树模型的特征输入 vs 神经网络的特征输入

### 2.1 数据从 Dataset 出来时，「逻辑上」都是面板`DatasetH.prepare(seg, col_set=["feature", "label"], ...)` 返回的仍是 **多级索引** `(datetime, instrument)` 上的表格；**差别发生在模型类的 `fit` / `predict` 里**：如何把这张表变成 **NumPy / PyTorch 张量**，以及 **batch 维到底代表什么**。

### 2.2 对照表（务必结合后面各架构样例看）

| 范式 | 典型模型类 | 数据集类 | 单个样本在模型里的形状（概念） | Batch 语义 |
|------|------------|----------|-------------------------------|------------|
| 树模型 | `LGBModel` | `DatasetH` | 一行 =一天、一只股票的 **扁平特征向量** `[F]` | 批量训练由树库内部处理；无「时间步」维 |
| 全连接 MLP | `DNNModelPytorch` | `DatasetH` | `[F]`，拼成 `x_batch` 为 `[B, F]` | `B` 条 **独立** `(日, 股)` 样本 |
| 序列（展平在列上） | `LSTM`（`pytorch_lstm`）/`TransformerModel`（`pytorch_transformer`）/`GATs` | `DatasetH`（常配 `Alpha360`） | 先把 **`[F×T]` 扁平向量** reshape 为 `[T, F]` 再送 RNN/Transformer | 与 MLP 相同：`B` 条独立样本；**每条样本已内含 T 个历史步** |
| 序列（显式时间步维） | `LSTM`（`pytorch_lstm_ts`）/`TransformerModel`（`pytorch_transformer_ts`）等 | **`TSDatasetH`** | DataLoader 给出 `[B, step_len, F+1]`，代码取 `[:, :, :-1]` 为特征 | 每条样本是 **连续 `step_len` 个交易日** 的轨迹；**必须**与 `step_len` 对齐 |
| 图注意力（同日横截面） | `GATs` | `DatasetH` |先对单只股票得到序列嵌入，再在 **同一交易日 N 只股票** 上算注意力 | **一个 batch = 一个交易日** 的截面（`N` 随当日股票数变化） |

### 2.3 和「传统机器学习」相比，神经网络侧多出来的工程事实

1. **设备与精度**：特征/标签会转为 `torch.float` 并放到 `cuda` 或 `cpu`（见 `DNNModelPytorch.fit` 等）。
2. **归一化与缺失**：Handler 仍负责主要归一化；部分 TS 模型在拿到 `TSDataSampler` 后会 `config(fillna_type="ffill+bfill")` 处理滑窗带来的 NaN。
3. **验证与早停**：MLP 常用 `max_steps` + 验证集 loss；RNN/Transformer/GATs 常用 `n_epochs` + `early_stop`。
4. **指标**：部分 PyTorch 模型用「负的 IC 相关 loss」作 early stop 指标（如 `DNNModelPytorch.get_metric`），与 LightGBM 默认 objective 不同，但 **下游 `pred.pkl` 仍是连续 score**，后处理流水线兼容。

### 2.4 统一案例：三只股票、连续两个交易日，各范式下的数据格式

以下用**同一股票池**（3 只标的）与**连续两个交易日**上的 `(datetime, instrument)` 面板，对照树模型与各类神经网络在「喂入学习器」时的张量形状。**表中特征与标签为虚构数值，仅说明结构**；`LABEL0` 的经济含义与表达式见 [`qrun_Alpha158_数据流说明.md`](./qrun_Alpha158_数据流说明.md)。

**共同设定**：Handler 已产出 Alpha158 侧特征维 **`F = 158`**（与典型列数同量级；实际以你 YAML 中 `FilterCol` / `DropCol` 后的列数为准）。股票池：`SH600000`、`SZ000001`、`SH600519`。

#### 2.4.1 面板样例（`2024-01-15`～`2024-01-16`，每日各 3 行）

| datetime | instrument | f1 | f2 | f3 | … | label（`LABEL0`） |
|----------|------------|---:|---:|---:|---|------------------:|
| 2024-01-15 | SH600000 | 0.12 | -1.03 | 0.55 | … | 0.008 |
| 2024-01-15 | SZ000001 | -0.21 | 0.67 | -0.14 | … | -0.003 |
| 2024-01-15 | SH600519 | 0.09 | 1.22 | 0.31 | … | 0.011 |
| 2024-01-16 | SH600000 | 0.11 | -0.98 | 0.52 | … | 0.005 |
| 2024-01-16 | SZ000001 | -0.19 | 0.71 | -0.10 | … | 0.001 |
| 2024-01-16 | SH600519 | 0.10 | 1.18 | 0.29 | … | 0.009 |

有效样本数 **`N = 6`（2 日 × 3 股）**。真实回测里日期会覆盖整段 `segments`，但**张量形状规则与此相同**：`N` 即为样本期内所有 `(日, 股)` 行数。

#### 2.4.2 各范式下如何用这张表（本例 `N = 6`）

**1）树模型（`LGBModel` + `DatasetH`）**

- 样本定义：**一行 = 某日 × 某股**。
- 对上表：`X.shape = [6, 158]`，`y.shape = [6]`（或等价地 `pandas` 宽表 + `LABEL0` 一列）。  
  训练时还可从更大的 `prepare("train")` 结果中再抽样 mini-batch，但**每一行语义不变**。

**2）全连接 MLP（`DNNModelPytorch` + `DatasetH`）**

- 与树模型**相同的样本定义**：`[N, F]`。
- 若本批恰好包含上表全部 6 行：`x_batch.shape = [6, 158]`，`y_batch.shape = [6]`。

**3）序列模型、历史编码在列上（`Alpha360` + `DatasetH`，如非 TS 版 LSTM/Transformer）**

- 每行特征是 **60 天 × 6 类字段** 展平后的 **`F_flat = 360`** 维（见本文 §4.2）。
- 对上表：`x_flat.shape = [6, 360]`，`forward` 内再为 **`[6, 60, 6]`**。  
  注意：**`6` 来自 6 条不同的 `(日, 股)` 样本**；Alpha360 里编码的 60 个历史步仍体现在**每行**的 360 列中，与「日历上有几天」不是同一概念。

**4）显式滑窗序列（`*_ts` + `TSDatasetH`，如 `step_len = 20`）**

- 每个训练样本：某标的在 **预测日 `t`** 上，由 **过去连续 `step_len` 个交易日** 拼成的轨迹（见本文 §4.3），**不是**面板上的单行。
- 上表中 **6 个 `(日, 股)` 端点** 一般对应 **6 条** 滑窗样本（例如 `SH600000` 在 15 日、16 日各一条，窗口内容不同）。若把这 6 条打进同一 batch，则 **`x.shape = [6, 20, F]`**，**`y.shape = [6]`**（标签常取各窗口**最后一天**）。  
  实现上，DataLoader 还会在 batch 维上打乱顺序；此处只强调**形状**。

**5）GATs（同日横截面 + `Alpha360`）**

- **每个交易日**、每只股票仍是一条 **`[360]`** 扁平向量。
- **按交易日分组**：`2024-01-15` 一次前向为 **`feature.shape = [3, 360]`** → 模型内 `[3, 60, 6]` + 当日 **`3×3`** 注意力；`2024-01-16` 再 **`[3, 360]`** 一次。  
  **两个交易日 = 两次「当日截面」前向**，而不是把 6 行合成一个 `N_t = 6` 的图（除非代码把两日混在一个 batch——以 `pytorch_gats` 实现为准，语义上仍以「日」为横截面单位）。真实 CSI300 下常为 **`N_t` 约为 300**，此处 `N_t = 3` 仅演示。

**小结**：Handler 产出的面板在逻辑上共用；**树模型与 MLP 为 `[样本条数, 特征数]`，本例样本条数为 6**；**Alpha360 系每行先 `[360]` 再还原 `[60,6]`**；**`TSDatasetH` 每条样本是 `[step_len, F]`，batch 为 `[B, step_len, F]`，多个预测日/多标的对应更大的 `B`**；**GATs 以「每个交易日一块 `[N_t, 360]`」为主循环单元**。

---

## 三、数据流示意图（深度学习视角）

```mermaid
flowchart TB subgraph src["数据源"]
        BIN["Qlib 二进制行情"]
        YAML["workflow_config_*.yaml"]
    end

    subgraph handler["Handler"]
        H["Alpha158 / Alpha360\n特征 + LABEL0"]
    end

    subgraph ds["数据集"]
        DH["DatasetH\n一日一行面板"]
        TSD["TSDatasetH + TSDataSampler\n滑窗序列样本"]
    end

    subgraph nn["神经网络模型"]
        MLP["DNNModelPytorch\n[B,F]"]
        RNN360["LSTM / Transformer / GATs\n扁平 [F*T] → [T,F]"]
        RNNTS["*_ts 模型\n[B,T,F]"]
    end

    YAML --> H
    BIN --> H
    H --> DH
    H --> TSD
    DH --> MLP
    DH --> RNN360
    TSD --> RNNTS
```

---

## 四、架构样例详解（含数字与张量形状）

以下数字与 **官方 benchmark 配置** 一致，便于你打开 YAML 逐项核对。

### 4.1 全连接 MLP（`DNNModelPytorch` + `DatasetH` + `Alpha158`）

**典型配置**：`examples/benchmarks/MLP/workflow_config_mlp_Alpha158.yaml`。

- **Handler 输出**：每个 `(datetime, instrument)` 一行，特征列数约 **157**（配置里 `DropCol` 去掉 `VWAP0` 后，`pt_model_kwargs.input_dim: 157`）。
- **进入模型前**：`DNNModelPytorch.fit` 将 `df["feature"].values` 转为 `torch.Tensor`，形状 **`[N, 157]`**，`N` 为训练段有效样本数。
- **一个 mini-batch**：随机索引 `choice` 长度 `batch_size`（如 8192），得到 **`x_batch_auto`: `[8192, 157]`**。
- **前向**：`Net` 中 `nn.Linear` 期望最后一维为 `input_dim`，即 **扁平向量**，无时间维。

**与 LightGBM 的异同**：

- **相同**：都是「**一行样本 = 某日某股**」，特征维固定为 `F`。
- **不同**：LightGBM 通常直接吃 `pandas`/`numpy` 的 **2D 表**；MLP 显式转为 **GPU张量**，并 mini-batch 随机梯度训练。

---

### 4.2 LSTM / Transformer（`Alpha360` + `DatasetH`）：**扁平 `F×T` 在列上，模型内 reshape**

**背景**：`Alpha360` 由 **6 类行情字段 × 各 60 个时间偏移** 拼成 **360列**（见 `qlib.contrib.data.loader.Alpha360DL.get_feature_config`：`CLOSE/OPEN/HIGH/LOW/VWAP/VOLUME` 各 60 个值）。列顺序是「按字段块」排列，因此 **reshape 规则** 与 `d_feat=6`、时间长度 `T=60` 严格对应。

**LSTM（非 TS 版）**：`examples/benchmarks/LSTM/workflow_config_lstm_Alpha360.yaml`，模块 `qlib.contrib.model.pytorch_lstm`。

`LSTMModel.forward` 中（逻辑等价于）：

1. 输入 `x`：**`[N, 360]`**（`N` 为 batch 内样本数）。
2. `reshape(N, 6,60)` → **`[N, 6, 60]`**（6 个特征通道，60 个时间步）。
3. `permute(0, 2, 1)` → **`[N, 60, 6]`**，满足 `nn.LSTM(batch_first=True, input_size=6)`。
4. 取最后时间步 `out[:, -1, :]` 接 `Linear`得到标量预测。

**数值小例子**（仅说明 reshape，非真实行情）：

- 设某样本扁平向量长度 360，前 60 维是「CLOSE 相关」、接下来 60 维是 OPEN、……- `d_feat=6`，则第 1 维长度必为 `360 / 6 = 60`，否则 `reshape` 报错。

**Transformer（非 TS 版）**：`examples/benchmarks/Transformer/workflow_config_transformer_Alpha360.yaml`，`qlib.contrib.model.pytorch_transformer.Transformer`。

- 同样 **`[N, 360]` → reshape为 `[N, 60, 6]`**，再 `Linear(6, d_model)`、**`[T, N, d_model]`** 送入 `nn.TransformerEncoder`（注意源码里 **非 batch_first**），最后取最后一个时间步做预测。

**与 MLP 的差别**：

- MLP 把 360 维当作 **一个长向量** 一次性全连接；
- LSTM/Transformer 把360 维 **还原为「60×6」的序列**，在时间维上参数共享（卷积/RNN/自注意力），**归纳偏置完全不同**。

---

### 4.3 LSTM / Transformer（`*_ts` + `TSDatasetH` + `Alpha158`）：**显式滑窗 `[B, step_len, F]`**

**典型配置**：`examples/benchmarks/LSTM/workflow_config_lstm_Alpha158.yaml`。

关键点：

- `dataset.class: TSDatasetH`，`kwargs` 里 **`step_len: 20`**。
- `TSDatasetH._prepare_seg` 会把时间区间 **向前多取 `step_len` 个交易日`**，以便每个预测日都能凑满历史窗（见 `qlib.data.dataset.TSDatasetH._extend_slice`）。
- `TSDataSampler.__getitem__` 返回该样本在过去 **`step_len`** 行上拼接的数组；与 `DataLoader` 组合后，单 batch 张量形状为 **`[batch_size, step_len, num_columns]`**。

在 `pytorch_lstm_ts.LSTM.train_epoch` 中：

- `feature = data[:, :, 0:-1]` → **`[B, 20, F]`**，`F` 为特征列数（示例配置里过滤后 **`d_feat: 20`**，与 `FilterCol` 后列数一致）。
- `label = data[:, -1, -1]` → 取 **窗口最后一天** 的标签标量，形状 **`[B]`**。

**与 4.2 的本质差别**：

| 项目 | Alpha360 + `DatasetH` | Alpha158 + `TSDatasetH` |
|------|----------------------|-------------------------|
| 历史从哪来 | **已经编码在 360 列里**（60 天 × 6 字段） | 从面板 **滑窗取出连续20 天** |
| 模型入口形状 | `[N, 360]` 再 reshape | DataLoader 直接给 `[B, 20, F]` |
| `d_feat` 含义 | 每个时间步 **6 个通道** | 每个时间步 **20 个因子**（示例配置） |

---

### 4.4 GATs：「**按交易日** 横截面 batch + 序列编码 + 图注意力」

**典型配置**：`examples/benchmarks/GATs/workflow_config_gats_Alpha360.yaml`，`qlib.contrib.model.pytorch_gats`。

**特征表**：仍是 `DatasetH` 的 `(datetime, instrument)` 面板，每行 **`[360]`** 扁平向量（`Alpha360`）。

**训练时 batch 构造**（`GATs.get_daily_inter` + `train_epoch`）：

1. 按 **日期**（MultiIndex 第一层）分组，得到每个交易日 `t` 的股票数 `N_t`。
2. 对每个 `t`，取该日 **全部 `N_t` 行** 组成一个张量 **`feature`: `[N_t, 360]`**。
3. `GATModel.forward`：`[N_t, 360]` → reshape 为 **`[N_t, 60, 6]`**，RNN 得到每只股票的最后隐状态 **`[N_t, hidden]`**。
4. 在 **`N_t` 个节点** 上计算注意力矩阵 **`[N_t, N_t]`**，做一次图上的加权聚合，再输出 **`[N_t]`** 预测。

**数值例子**（虚构，只说明形状）：

- 某日沪深 300 有 300 只可交易样本，则 **一个 forward** 的 batch 是 **`[300, 360]`**，注意力矩阵是 **`300×300`**（显存与复杂度随当日股票数平方增长，这是图注意力类模型与「独立样本 MLP」最大的工程差异之一）。

**与 LightGBM 的差别**：

- LightGBM 每个 `(日, 股)` 样本 **独立**；
- GATs **强制同一日内的样本在模型内部相互看见**（通过注意力），score 是 **截面联合推断** 的结果。

---

### 4.5 TabNet（`TabnetModel`）：回到 **扁平表**，但带预训练与稀疏特征选择

**典型配置**：`examples/benchmarks/TabNet/workflow_config_TabNet_Alpha158.yaml`。

-数据管线：**`DatasetH` + `Alpha158`**，与 MLP 一样是 **2D 特征表**。
- `d_feat` 需与特征维一致（默认158，实际以 Handler 列数为准）。
-额外：`TabnetModel` 可先对 `feature` 做 **自监督预训练**（`pretrain_fn`），再监督训练；输入仍是 **`[B, F]`**。

---

## 五、YAML 字段与「该用哪种 Dataset」速查

| 你的目标 | `task.dataset.class` | 常见 `task.model.module_path` | 备注 |
|----------|---------------------|--------------------------------|------|
| 扁平因子 + MLP | `DatasetH` | `qlib.contrib.model.pytorch_nn` | `pt_model_kwargs.input_dim` 对齐特征列数 |
| Alpha360 + RNN/Transformer/GATs | `DatasetH` | `pytorch_lstm` / `pytorch_transformer` / `pytorch_gats` | `d_feat=6`，列数应能被6 整除 |
| Alpha158 + 滑窗序列 | **`TSDatasetH`** | `pytorch_lstm_ts` / `pytorch_transformer_ts` / `pytorch_tcn_ts` 等 | 必须配置 **`step_len`**；`d_feat` = 每步特征维 |
| TabNet | `DatasetH` | `qlib.contrib.model.pytorch_tabnet` | 注意预训练段 `pretrain`/`pretrain_validation` 是否在 segments 中定义 |

---

## 六、一句话小结

**Qlib 里 Handler 产出的「面板数据」对树模型和大部分神经网络是共用的；真正的分叉在于：模型把每一行当成「扁平向量」「内置多日的扁平编码（Alpha360）」还是「滑窗拉出的序列（TSDatasetH）」，以及 GATs 这类结构是否要求「按日截面」联合前向。**

对照阅读：[`qrun_Alpha158_数据流说明.md`](./qrun_Alpha158_数据流说明.md)（LightGBM 端到端数据流与 `LABEL0` 详解）。

---

## 附录：相关源码锚点（便于自行跟进实现）

| 主题 | 路径 |
|------|------|
| MLP 张量化与 batch训练 | `qlib/contrib/model/pytorch_nn.py`（`DNNModelPytorch.fit`） |
| Alpha360 列定义 | `qlib/contrib/data/loader.py`（`Alpha360DL.get_feature_config`） |
| LSTM reshape（Alpha360） | `qlib/contrib/model/pytorch_lstm.py`（`LSTMModel.forward`） |
| Transformer（Alpha360） | `qlib/contrib/model/pytorch_transformer.py`（`Transformer.forward`） |
| TS 滑窗数据集 | `qlib/data/dataset/__init__.py`（`TSDataSampler`、`TSDatasetH`） |
| LSTM（TS）batch 解析 | `qlib/contrib/model/pytorch_lstm_ts.py`（`train_epoch`） |
| GATs 按日 batch | `qlib/contrib/model/pytorch_gats.py`（`get_daily_inter`、`GATModel.forward`） |
