# 本地每日预测流程

本文档说明如何用已经训练好的 Qlib recorder 每天生成一个预测结果文件。该流程只做推理，不重训模型，不要求每日更新全市场训练数据。

## 目标

- 全市场 `cn_data` 继续作为训练数据目录，按月从社区数据源刷新后用于增量训练。
- 每日预测也直接使用 `~/.qlib/qlib_data/cn_data`，不再维护单独预测数据目录。
- 默认预测 `cn_data` 中的全标的；也可以改成 `csi300`、配置文件中的自选列表，或 YAML 里直接列出的标的。
- 增量更新的标的池放在 `data_update` 下配置，预测标的池放在 `prediction` 下配置，两者可以不同。
- 每次运行只输出当天一个 CSV，方便人工查看或后续接入交易/通知流程。

## 默认配置

默认配置文件：

```bash
examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml
```

关键字段：

```yaml
qlib_init:
    provider_uri: "~/.qlib/qlib_data/cn_data"
    region: cn

experiment:
    uri: "mlruns"
    name: "lightgbm_Alpha158_2026"
    recorder_id: "656273f29b6e46f191d4de56866e52f6"

prediction:
    instruments: all
    date: latest
    instrument_names_file: "configs/instrument_names.csv"
    output_dir: "predictions/lightgbm_Alpha158_2026"
    output_filename: "{date}.csv"
```

`qlib_init.provider_uri` 直接指向全市场 `cn_data`。预测时不要求全市场所有标的都更新到最新交易日，
但至少要保证：

- `calendars/day.txt` 包含要预测的交易日；
- 你要预测的标的在 `features/<instrument>/` 下有该交易日行情；
- 如果使用 `prediction.instruments: all` 或 `csi300` 这类大池，池内未更新标的可能产生空值或缺失；每天只更新部分标的时，建议把预测池也限制到已更新标的。

`experiment.recorder_id` 必须指向已经训练好的 recorder。训练产物中需要有 `params.pkl` 和 `dataset`。

`prediction.instruments` 默认是 `all`。如果你只想看部分股票，或者 `cn_data` 只有部分标的更新到最新交易日，可以改成列表：

```yaml
prediction:
    instruments:
        - SH600000
        - SZ000001
```

也可以用文件：

```yaml
prediction:
    instruments_file: "configs/predict_universe.txt"
```

文件支持一行一个标的，也支持逗号或空格分隔，并允许使用 `#` 写注释。

`cn_data` 自带的 `instruments/*.txt` 通常只有标的代码、开始日期和结束日期，没有中文简称。
仓库内维护一份永久代码映射字典：

```text
configs/instrument_names.csv
```

默认配置已启用这份字典，预测结果里的 `instrument_name` 会按它填充。后续遇到新股、简称变更或退市整理时，
直接更新这份 CSV 即可。映射文件支持 CSV，常见列名包括：

- 代码列：`instrument`、`symbol`、`code`、`ts_code`、`证券代码`、`股票代码`、`代码`；
- 名称列：`instrument_name`、`name`、`stock_name`、`证券简称`、`股票简称`、`中文名称`、`证券名称`。

示例：

```csv
instrument,instrument_name
SZ000001,平安银行
SH600000,浦发银行
```

也支持常见的 `000001.SZ`、`600000.SH` 写法，脚本会转换成 Qlib 使用的 `SZ000001`、`SH600000`。

默认不会在预测前更新行情数据：

```yaml
data_update:
    enabled: false
```

也就是说，当前默认运行只读取已有的 `~/.qlib/qlib_data/cn_data` 和本地 recorder 做推理。
如果启用 `data_update.enabled: true`，默认更新标的池配置为 `data_update.instruments: all`；
也可以改成指数池、自选列表或 `instruments_file`。更新耗时取决于你接入的数据源、增量更新脚本和标的数量，
当前默认配置还没有行情更新脚本，因此本轮没有实测全市场增量更新时间。

## 运行

在仓库根目录执行：

```bash
python scripts/daily_predict.py --config examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml
```

指定日期：

```bash
python scripts/daily_predict.py \
  --config examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml \
  --date 2026-04-17
```

如果当天结果文件已存在，默认跳过。需要覆盖时：

```bash
python scripts/daily_predict.py --config examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml --force
```

输出示例：

```text
/root/code/qlib/predictions/lightgbm_Alpha158_2026/2026-04-17.csv
/root/code/qlib/predictions/lightgbm_Alpha158_2026/2026-04-17.json
```

CSV 字段：

```text
datetime,rank,instrument,instrument_name,score
```

JSON 是本次运行的简要 manifest，记录日期、recorder、行数、中文名缺失数量、NaN 数量和输出路径。
`predictions/` 属于本地运行结果，已被 git 忽略，不会出现在提交里。

本机在默认 `all` 标的池上跑完整预测约 55 秒，当前输出 5186 条预测记录。

## 可选 cn_data 更新钩子

如果你已经有自己的 `cn_data` 增量更新脚本，可以在 YAML 中启用：

```yaml
data_update:
    enabled: true
    cwd: "."
    instruments: csi300
    command:
        - "python"
        - "scripts/your_update_cn_data.py"
        - "--provider-uri"
        - "{provider_uri}"
        - "--instruments"
        - "{data_update_instruments}"
```

命令用列表形式配置，不通过 shell 执行。这个钩子只负责在预测前调用你的数据更新命令；
具体从哪个数据源下载、是否只更新部分标的、如何转换成 Qlib bin，由你的数据更新脚本负责。
命令里可以使用这些占位符：

- `{provider_uri}`：当前 `qlib_init.provider_uri`，会展开成本机路径；
- `{data_update_instruments}`：`data_update.instruments`，列表会转成逗号分隔；
- `{data_update_instruments_file}`：`data_update.instruments_file`；
- `{prediction_instruments}`：`prediction.instruments`；
- `{prediction_instruments_file}`：`prediction.instruments_file`；
- `{date}`：`prediction.date`。

`cn_data` 不必每天全市场完整更新。只要当天预测只读取已更新的标的，Qlib 的 `D.features`
会按传入的 instruments 取数。风险在于：如果你默认预测 `all`，但只增量更新了小池，
小池外标的的特征可能为空或最终没有有效 score。因此部分更新时最好同步调整 `prediction.instruments_file`。

临时跳过数据更新：

```bash
python scripts/daily_predict.py --skip-data-update
```

## 本地定时

Linux cron 示例，按北京时间交易日收盘后运行：

```cron
QLIB_DIR=/root/code/qlib
QLIB_DAILY_CONFIG=examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml
QLIB_DAILY_LOG=logs/daily_predict.log
30 18 * * 1-5 cd $QLIB_DIR && python scripts/daily_predict.py --config $QLIB_DAILY_CONFIG >> $QLIB_DAILY_LOG 2>&1
```

脚本会按 Qlib 交易日历选择最新日期。遇到节假日或预测数据没有更新时，通常会生成最近可用交易日的结果；如果结果文件已存在，会直接跳过。

## 性能建议

- 默认会预测 `all`；每日只更新你要看的标的也可以，但预测配置要同步限制 instruments。
- 月度再用社区包刷新全市场 `cn_data`，用于训练或大范围回测。
- `prediction.topk` 可以只导出排名靠前的标的；不设置时导出全部预测标的。
- 如果自定义 handler 需要额外历史窗口，把 `prediction.history_window` 调大，例如 `60`。默认 `0`，适合当前 Alpha158 日线配置的快速推理路径。
