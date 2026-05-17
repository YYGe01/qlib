# 本地每日预测流程

本文档说明如何用已经训练好的 Qlib recorder 每天生成一个预测结果文件。该流程只做推理，不重训模型，不要求每日更新全市场训练数据。

## 目标

- 全市场 `cn_data` 继续作为训练数据目录，按月从社区数据源刷新后用于增量训练。
- 每日预测也直接使用 `~/.qlib/qlib_data/cn_data`，不再维护单独预测数据目录。
- 预测股票池可以是 `csi300`、配置文件中的自选列表，或 YAML 里直接列出的标的；如果每天只更新部分标的，就只预测这些标的。
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
    instruments: csi300
    date: latest
    output_dir: "predictions/lightgbm_Alpha158_2026"
    output_filename: "{date}.csv"
```

`qlib_init.provider_uri` 直接指向全市场 `cn_data`。预测时不要求全市场所有标的都更新到最新交易日，
但至少要保证：

- `calendars/day.txt` 包含要预测的交易日；
- 你要预测的标的在 `features/<instrument>/` 下有该交易日行情；
- 如果使用 `prediction.instruments: csi300` 这类市场池，池内未更新标的可能产生空值或缺失；每天只更新部分标的时，建议使用 `instruments_file` 或显式列表。

`experiment.recorder_id` 必须指向已经训练好的 recorder。训练产物中需要有 `params.pkl` 和 `dataset`。

`prediction.instruments` 默认是 `csi300`。如果你只想看部分股票，或者 `cn_data` 只有部分标的更新到最新交易日，可以改成列表：

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
predictions/lightgbm_Alpha158_2026/2026-04-17.csv
predictions/lightgbm_Alpha158_2026/2026-04-17.json
```

CSV 字段：

```text
datetime,rank,instrument,score
```

JSON 是本次运行的简要 manifest，记录日期、recorder、行数、NaN 数量和输出路径。

## 可选 cn_data 更新钩子

如果你已经有自己的 `cn_data` 增量更新脚本，可以在 YAML 中启用：

```yaml
data_update:
    enabled: true
    cwd: "."
    command:
        - "python"
        - "scripts/your_update_cn_data.py"
```

命令用列表形式配置，不通过 shell 执行。这个钩子只负责在预测前调用你的数据更新命令；
具体从哪个数据源下载、是否只更新部分标的、如何转换成 Qlib bin，由你的数据更新脚本负责。

`cn_data` 不必每天全市场完整更新。只要当天预测只读取已更新的标的，Qlib 的 `D.features`
会按传入的 instruments 取数。风险在于：如果你传入 `csi300`，但其中部分标的没有最新行情，
这些标的的特征可能为空或最终没有有效 score。因此部分更新时最好同步调整 `prediction.instruments_file`。

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

- 每日只更新你要看的标的也可以，但预测配置要同步限制 instruments。
- 月度再用社区包刷新全市场 `cn_data`，用于训练或大范围回测。
- `prediction.topk` 可以只导出排名靠前的标的；不设置时导出全部预测标的。
- 如果自定义 handler 需要额外历史窗口，把 `prediction.history_window` 调大，例如 `60`。默认 `0`，适合当前 Alpha158 日线配置的快速推理路径。
