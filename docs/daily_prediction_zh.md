# 本地每日预测流程

本文档说明如何用已经训练好的 Qlib recorder 每天生成一个预测结果文件。该流程只做推理，不重训模型，不要求每日更新全市场训练数据。

## 目标

- 全市场 `cn_data` 继续作为训练数据目录，按月从社区数据源刷新后用于增量训练。
- 每日预测使用单独的轻量 Qlib 数据目录，例如 `~/.qlib/qlib_data/cn_predict_csi300`。
- 预测股票池可以是 `csi300`、配置文件中的自选列表，或 YAML 里直接列出的标的。
- 每次运行只输出当天一个 CSV，方便人工查看或后续接入交易/通知流程。

## 默认配置

默认配置文件：

```bash
examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml
```

关键字段：

```yaml
qlib_init:
    provider_uri: "~/.qlib/qlib_data/cn_predict_csi300"
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

`qlib_init.provider_uri` 是每日预测数据目录，建议和全市场训练目录分开。只要这个目录里有当天需要预测的行情、日历和对应 instruments，就可以不更新全市场数据。

`experiment.recorder_id` 必须指向已经训练好的 recorder。训练产物中需要有 `params.pkl` 和 `dataset`。

`prediction.instruments` 默认是 `csi300`。如果预测数据目录没有 `csi300` instruments 文件，或者你只想看部分股票，可以改成列表：

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

## 可选数据更新钩子

如果你已经有自己的轻量预测数据更新脚本，可以在 YAML 中启用：

```yaml
data_update:
    enabled: true
    cwd: "."
    command:
        - "python"
        - "scripts/update_predict_data.py"
        - "--market"
        - "csi300"
```

命令用列表形式配置，不通过 shell 执行。这个钩子只负责在预测前调用你的数据更新命令；具体从哪个数据源下载、如何转换成 Qlib bin，由你的数据更新脚本负责。

仓库也提供了一个轻量同步脚本，可以从已有全市场 Qlib 数据目录复制指定股票池到独立预测目录：

```bash
python scripts/update_predict_data.py \
  --source-uri ~/.qlib/qlib_data/cn_data \
  --target-uri ~/.qlib/qlib_data/cn_predict_csi300 \
  --market csi300
```

这个脚本不下载外部行情，只复制 `calendars/`、选定 instruments 和对应 `features/<instrument>/`。
如果全市场源目录没有更新，它不会凭空产生新行情；如果你先用自己的数据源更新了源目录或预测目录，
它可以只同步关注股票池，避免每日处理全市场。

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

- 每日预测数据目录只维护关注股票池，例如 `csi300` 或自选池。
- 全市场 `cn_data` 保留给月度刷新和增量训练，不放进每日预测流程。
- `prediction.topk` 可以只导出排名靠前的标的；不设置时导出全部预测标的。
- 如果自定义 handler 需要额外历史窗口，把 `prediction.history_window` 调大，例如 `60`。默认 `0`，适合当前 Alpha158 日线配置的快速推理路径。
