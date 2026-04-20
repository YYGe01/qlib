# Qlib YAML 驱动工作流实践指南（study_yaml_workflow）

本文面向希望**按官方推荐方式**使用 Qlib 的读者：用 **YAML 配置**驱动 `qrun` / `python -m qlib.cli.run`，理解 **DataHandler 扩展**与 **Model 接口**，并与 **LightGBM 等训练模型**流水线对齐。阅读对象：已能安装环境与准备 `cn_data` 的初学者。

**快速开始（在 `examples/study_yaml_workflow` 目录下执行）：**

```bash
conda activate ai-trader
cd examples/study_yaml_workflow
python -m qlib.cli.run workflow_rule_factor.yaml
```

对照官方 LightGBM 合并配置：

```bash
python -m qlib.cli.run workflow_overlay_lightgbm.yaml
```

---

## 一、这套示例解决什么问题？


| 目标                        | 说明                                                                                  |
| ------------------------- | ----------------------------------------------------------------------------------- |
| 与官方 benchmark **同一入口**    | 使用 `qlib.model.trainer.task_train`，而非手写 `R.start` 拼流程（手写仍合法，用于调试）。                  |
| 规则因子与模型 **同一套 `task` 结构** | 只替换 `task.model` 与 `task.dataset.handler`，`record`（Signal / SigAna / PortAna）可保持不变。 |
| 因子扩展 **有明确继承点**           | 在 `Alpha158` 上追加列：继承并重写 `get_feature_config()`；换预测源：实现兼容的 `Model`。                  |


---

## 二、目录与文件职责

```
examples/study_yaml_workflow/
├── README.md                      # 本文档（唯一说明文档）
├── workflow_rule_factor.yaml      # 主配置：规则因子 + 完整 record
├── workflow_overlay_lightgbm.yaml # 演示 BASE_CONFIG_PATH 合并官方 LightGBM
└── mylib/
    ├── handler.py                 # StudyAlpha158：Alpha158 + 自定义列
    └── model.py                   # FactorColumnModel：单列特征即 pred
```

- `**workflow_rule_factor.yaml**`：顶层包含 `qlib_init`、`sys`、`task`、`record` 等，与 `examples/benchmarks/Linear/workflow_config_linear_Alpha158.yaml` 结构平行。
- `**mylib**`：通过 YAML 中的 `module_path: mylib.handler` 引用；**必须在运行命令时让 Python 能找到该包**（见下文 `sys.rel_path`）。

---

## 三、环境准备

1. **Conda 环境**（与仓库 `AGENTS.md` 一致）
  ```bash
   conda activate ai-trader
  ```
2. **数据**
  - `qlib_init.provider_uri` 指向本机 `cn_data`（默认 `~/.qlib/qlib_data/cn_data`）。  
  - 若路径不同，可在 YAML 里改 `provider_uri`，或设置环境变量后在配置里引用（需自行与 Jinja 模板配合）。
3. **工作目录（重要）**
  配置中有：
   含义：把**当前 YAML 所在目录**加入 `sys.path`，从而 `import mylib` 成功。  
   **请始终在 `examples/study_yaml_workflow` 目录下执行命令**，不要从仓库根目录用相对路径随意调用，否则可能找不到 `mylib`。

---

## 四、第一次运行（建议逐步做）

### 步骤 1：进入目录并执行规则因子工作流

```bash
cd /path/to/qlib/examples/study_yaml_workflow
python -m qlib.cli.run workflow_rule_factor.yaml
```

若已安装控制台脚本，也可：

```bash
qrun workflow_rule_factor.yaml
```

成功时终端会打印数据加载、SignalRecord、`SigAnaRecord` 指标、`PortAnaRecord` 回测风险摘要等，与官方 Linear/LightGBM 运行风格一致。

### 步骤 2：对照运行「继承官方 LightGBM 配置」

```bash
python -m qlib.cli.run workflow_overlay_lightgbm.yaml
```

该文件仅设置 `BASE_CONFIG_PATH` 指向 `../benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml` 并覆盖 `experiment_name`，用于体会 **配置合并** 与 **同一 record 链下真模型** 的行为。

### 步骤 3：查看实验产物

- 默认实验跟踪目录为当前工作目录下的 `**mlruns/`**（由 `qlib.cli.run` 中 `exp_manager` 与 `uri_folder` 决定）。  
- 可用 MLflow UI 或直接在 `mlruns` 目录中查看某次 `recorder` 保存的 `pred.pkl`、回测报告等（与官方文档一致）。

---

## 五、配置文件逐项说明（`workflow_rule_factor.yaml`）

### 5.1 `qlib_init`

- `**provider_uri**`：Qlib 数据根目录。  
- `**region: cn**`：中国 A 股区域常量，与数据一致。

### 5.2 `sys.rel_path`

- 将「YAML 所在目录」加入 `sys.path`。  
- **不要**随意改成子目录，**除非**你把 `mylib` 同步移动并相应修改 import 路径。

### 5.3 `experiment_name`

- MLflow/Qlib 实验名，便于在 `mlruns` 中区分「规则因子实验」与「LightGBM 基线」。

### 5.4 `data_handler_config`（锚点 `&data_handler_config`）

- `**instruments`**：股票池，此处为 `csi300`。  
- **时间范围**：`start_time` / `end_time` 为数据加载区间；`fit_start_time` / `fit_end_time` 供部分 Processor 拟合（如标准化）。  
- `**infer_processors` / `learn_processors`**：与官方 Alpha158 教程一致，对特征与标签做缺失、标准化等。  
修改这些会改变 **输入给模型的特征分布**，与换模型一样需要谨慎对照。

### 5.5 `task.model`

```yaml
class: FactorColumnModel
module_path: mylib.model
kwargs:
    feature_col: MA_TREND_5_20
```

- `**FactorColumnModel**`：不训练参数；`predict` 时从 `dataset.prepare(..., data_key=DK_I)` 中取 `**feature_col**` 对应列作为预测序列。  
- `**feature_col**` 必须与 Handler 产出的列名一致（见 `StudyAlpha158` 中追加的 `MA_TREND_5_20`）。

### 5.6 `task.dataset.handler`

```yaml
class: StudyAlpha158
module_path: mylib.handler
kwargs: *data_handler_config
```

- `**StudyAlpha158**` 在 `**get_feature_config()**` 中调用与官方 `Alpha158` 相同的 `Alpha158DL.get_feature_config(conf)`，再 **append** 一条表达式与列名。  
- 这是 **官方推荐的「在 Alpha158 上增列」方式**，无需复制整份 Alpha158 源码。

### 5.7 `task.record`

- `**SignalRecord`**：调用 `model.predict` 生成 `pred.pkl`（及标签相关产物）。  
- `**SigAnaRecord**`：IC、Rank IC 等（需标签合法）。  
- `**PortAnaRecord**`：组合回测与风险指标；`config` 引用 `port_analysis_config`（TopK、成本、基准等）。

与 **Linear/LightGBM** 的 YAML 相比，通常 **只改 `task.model` 与 `task.dataset.handler`** 即可切换「规则单列」与「机器学习模型」。

---

## 六、`mylib` 代码阅读顺序

1. `**handler.py` → `StudyAlpha158**`
  - 阅读 `Alpha158.get_feature_config`（上游 `qlib/contrib/data/handler.py`）。  
  - 理解 `(fields, names)` 与 `Alpha158DL.get_feature_config` 的关系。  
  - 练习：改表达式、改列名，并同步修改 YAML 里 `FactorColumnModel.feature_col`。
2. `**model.py` → `FactorColumnModel**`
  - 阅读 `qlib.contrib.model.linear.LinearModel.predict` 如何使用 `dataset.prepare(..., DK_I)`。  
  - 理解 `**fit` 为空** 仍满足 `task_train` 对 `Model` 的调用约定。  
  - 练习：临时改为输出另一列（如某 Alpha158 原有列名），观察 IC/回测变化。

---

## 七、建议的实践任务（从易到难）


| 序号  | 任务                                                                                     | 目的                 |
| --- | -------------------------------------------------------------------------------------- | ------------------ |
| 1   | 只改 `experiment_name` 再跑一遍                                                              | 熟悉 `mlruns` 中实验区分  |
| 2   | 在 `StudyAlpha158` 中再 append 一列，并新建第二个 YAML 用 `FactorColumnModel` 指向新列                  | 熟悉「一列一策略」的切换方式     |
| 3   | 复制 `workflow_rule_factor.yaml`，把 `task.model` 换成 `LinearModel`（参考 `benchmarks/Linear`） | 体会与规则列混用的差异        |
| 4   | 运行 `workflow_overlay_lightgbm.yaml`，对比同一 `port_analysis` 设定下与 `FactorColumnModel` 的指标  | 建立「基线模型」概念         |
| 5   | 阅读 `qlib/model/trainer.py` 中 `_exe_task`                                               | 理解 `qrun` 背后逐步执行顺序 |


---

## 八、Windows 与中文：编码说明（已修复）

**原因**：旧版 `qlib/cli/run.py` 使用 `open(path)` 未指定编码，在简体中文 Windows 上默认常为 **GBK**，若 YAML 以 **UTF-8** 保存且含中文注释，会触发 `UnicodeDecodeError`。

**处理**：已在 `qlib/cli/run.py` 中为以下两处统一使用 `encoding="utf-8"`：

- 读取用户传入的主配置文件（`render_template`）；  
- 读取 `BASE_CONFIG_PATH` 合并进来的基础配置。

因此：**工作流 YAML 可使用 UTF-8 中文注释**；请仍用编辑器将文件保存为 **UTF-8**（可选带 BOM，一般无必要）。

若你使用 **上游 pip 安装的 pyqlib** 而非当前仓库源码，需等待上游合并相同修改，或在本地对 `site-packages/qlib/cli/run.py` 做同样改动。

---

## 九、常见问题

**Q：提示找不到 `mylib`？**  
A：确认当前工作目录为 `examples/study_yaml_workflow`，且 YAML 中 `sys.rel_path` 为 `["."]`。

**Q：`FactorColumnModel` 报列不存在？**  
A：`feature_col` 必须与 Handler 生成的列名完全一致（区分大小写）。

**Q：想和官方 CSI500 对齐？**  
A：修改 YAML 中 `market`、`instruments` 与 `benchmark` 等，与 `benchmarks` 下 `*_csi500.yaml` 对齐即可，并注意数据集中是否包含对应指数成分。

**Q：回测很慢？**  
A：Alpha158 数据量较大属正常；可先缩短 `test` 段日期做调试。

---

## 十、MLflow：怎么看、看什么指标

`qrun` / `python -m qlib.cli.run` 会把每次完整跑的结果记到当前目录下的 **`mlruns/`**。用 **MLflow** 自带的网页界面最方便对比「哪一次跑、指标谁好」。

### 1. 怎么打开界面

1. 先进入**你运行 YAML 时所在的目录**（本示例应为 `examples/study_yaml_workflow`，且该目录里已有 `mlruns` 文件夹）。
2. 在同一环境中执行：
   ```bash
   mlflow ui
   ```
3. 终端会提示本地地址，一般为 **http://127.0.0.1:5000** ，用浏览器打开即可。

若提示找不到 `mlflow`，请先安装：`pip install mlflow`（或与 pyqlib 一起装好的环境）。

### 2. 界面里先看什么

- 左侧或下拉框里选 **Experiment（实验）**：名称对应 YAML 里的 **`experiment_name`**（例如 `study_rule_factor`、`study_lightgbm_baseline`）。
- 中间是 **Run 列表**：**每一行就是完整跑了一次**（改参数再跑会出现新行）。可按时间排序，点某一行进入详情。
- 点进某次 Run 后，常用三个页签：
  - **Parameters**：本次记录的参数（如任务配置里展开后的项）。
  - **Metrics**：**数值指标**，适合和别的 Run **对比曲线或表格**（勾选多行 Run 可对比）。
  - **Artifacts**：本次保存的文件（如 `pred.pkl`、组合分析结果 `portfolio_analysis/` 下的 `*.pkl` 等）。

### 3. 指标大致分两类（本工作流会记这些）

**A. 预测质量（`SigAnaRecord`，信号 vs 标签）**

| 名称（界面里常见） | 含义（直观理解） |
|-------------------|------------------|
| **IC** | 预测分数与标签收益的截面相关性，日均后再平均；越大通常越好（是否显著要样本长度）。 |
| **ICIR** | IC 均值 / IC 标准差，类似「信噪比」；越大表示 IC 更稳。 |
| **Rank IC** | 用秩相关代替 Pearson IC；同样可看 **Rank ICIR**。 |
| **Long-Short Ann Return / Sharpe** 等 | 若开了多空分析，会多几项年化收益、夏普（与配置 `ana_long_short` 有关）。 |

**B. 回测组合（`PortAnaRecord`，模拟交易后）**

Metrics 里键名常带频率前缀，例如 **`1day.`**（日线），后面是风险分析展平后的字段，例如：

| 含义 | 在界面里可关注的典型项 |
|------|------------------------|
| 相对基准的超额收益（不含交易成本） | 名里常含 **`excess_return_without_cost`**，里面有 **年化收益 annualized_return**、**信息比率 information_ratio**、**最大回撤 max_drawdown** 等。 |
| 相对基准的超额收益（含成本） | 名里常含 **`excess_return_with_cost`**，同样可看年化、IR、回撤。 |
| 基准本身 | 名里常含 **benchmark** 相关键，用于对照指数表现。 |

具体键名会因 `flatten_dict` 略长，在 **Metrics** 里可搜索关键词：`annualized`、`information_ratio`、`max_drawdown`、`excess`。

**C. 执行层指标（若有）**

部分配置会记 **`ffr`（成交比例）、`pa`、`pos`** 等，偏执行仿真，入门可先以 **IC / 超额年化 / 最大回撤** 为主。

### 4. 怎么「比两次跑」

在实验列表里 **勾选两次 Run** → 用界面上的 **Compare**（对比），选同一批 **Metrics** 名称，可看柱状图或并列数值，便于对比改参数前后的差异。

---

## 十一、延伸阅读（官方）

- `qlib/cli/run.py`：`workflow` 与 `BASE_CONFIG_PATH` 合并逻辑。  
- `qlib/model/trainer.py`：`task_train` / `_exe_task`。  
- `docs/component/workflow.rst`（若已构建文档）：Record 模板说明。  
- `examples/benchmarks/LightGBM/workflow_config_lightgbm_Alpha158.yaml`：完整模型基线配置。

---

文档与 `examples/study_yaml_workflow` 目录中示例代码一致；若你移动目录或重命名 `mylib`，请同步更新本文档中的路径说明。