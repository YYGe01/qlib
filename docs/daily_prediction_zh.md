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

默认会在预测前尝试更新行情数据：

```yaml
data_update:
    enabled: true
    source: pool
    sources: "baostock,yahoo,akshare"
    instruments: all
```

`pool` 是多源负载均衡模式：标的队列会随机分配给 `baostock`、`yahoo`、`akshare`；
每个标的同一轮只请求一个源，不会把同一个标的同时打到多个源。返回空数据、异常或标准化失败的标的会回到队列，
下一轮重新分配。某个源如果连续出现网络或接口异常，会先进入冷却退避；多次冷却后本轮禁用该源。

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

## cn_data 增量更新

默认 YAML 已接入仓库内的增量更新脚本：

```yaml
data_update:
    enabled: true
    source: pool
    sources: "baostock,yahoo,akshare"
    cwd: "."
    instruments: all
    work_dir: "~/.qlib/stock_data/cn_daily_update"
    max_workers: 6
    source_workers: "baostock=1,yahoo=3,akshare=2"
    retry_count: 4
    source_consecutive_failures: 3
    source_cooldown: 10
    max_source_cooldown: 120
    source_disable_after_cooldowns: 2
    command:
        - "python"
        - "scripts/update_cn_data.py"
        - "--provider-uri"
        - "{provider_uri}"
```

命令用列表形式配置，不通过 shell 执行。`scripts/update_cn_data.py` 会完成「下载源数据 → 标准化到 Qlib 当前口径 → 写入 cn_data」。
为避免生产数据半更新，测速时使用 `--dry-run`，只下载和标准化，不写入 `~/.qlib/qlib_data/cn_data`。
如果 `data_update.instruments` 使用 `csi300` 这类 `cn_data/instruments/<market>.txt` 命名池，
脚本在写入行情后会同步推进该命名池文件中本轮成功更新标的的结束日期；`all` 仍由 Qlib dump 流程维护。
命令里可以使用这些占位符：

- `{provider_uri}`：当前 `qlib_init.provider_uri`，会展开成本机路径；
- `{data_update_source}`：`data_update.source`；
- `{data_update_sources}`：`data_update.sources`；
- `{data_update_instruments}`：`data_update.instruments`，列表会转成逗号分隔；
- `{data_update_instruments_file}`：`data_update.instruments_file`；
- `{data_update_work_dir}`：临时源数据和标准化 CSV 目录；
- `{data_update_max_workers}`：全局最大并发；
- `{data_update_source_workers}`：每个源的并发上限；
- `{data_update_retry_count}`：单标的最大尝试次数；
- `{data_update_source_cooldown}`：源异常后的初始冷却秒数；
- `{data_update_source_disable_after_cooldowns}`：源冷却多少次后本轮禁用；
- `{prediction_instruments}`：`prediction.instruments`；
- `{prediction_instruments_file}`：`prediction.instruments_file`；
- `{date}`：`prediction.date`。

`cn_data` 不必每天全市场完整更新。只要当天预测只读取已更新的标的，Qlib 的 `D.features`
会按传入的 instruments 取数。风险在于：如果你默认预测 `all`，但只增量更新了小池，
小池外标的的特征可能为空或最终没有有效 score。因此部分更新时最好同步调整预测池；
如果更新和预测都使用同一个命名池，例如 `csi300`，脚本会自动维护该命名池的结束日期。

临时跳过数据更新：

```bash
python scripts/daily_predict.py --skip-data-update
```

本机测速结果：

- `baostock`：5 个标的 dry-run 全成功，约 1.67 秒；20 个活跃预测标的在 pool 中主要由 Baostock 承担。
- `yahoo`：5 个标的 dry-run 全成功，约 6.64 秒；适合作为并行补充源。
- `akshare`：指数可用，但股票接口多次连接失败；在 pool 中会被健康检查自动冷却，不作为单独默认源。
- `pool`：20 个当前预测结果中的活跃标的 dry-run 全成功，约 4.05 秒；按该样本粗略外推，5000 级 SH/SZ 标的的下载和标准化约十几分钟级别，实际取决于当晚网络、源限流、停牌/退市标的比例和失败重试次数。

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
