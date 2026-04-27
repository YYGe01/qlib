#!/usr/bin/env bash
#
# =============================================================================
# 中国区 Qlib 日频二进制数据 — 增量更新（Shell 入口）
# =============================================================================
#
# Shell 侧三件事：
#   (A) 解析参数、确定 Qlib 仓库路径与数据目录、准备日志文件
#   (B) 激活 Conda 环境，保证使用与项目一致的 Python 与依赖
#   (C) 调用 collector.py update_data_to_bin；再可选执行 check_data_health.py
# 其中 (C) 里「拉 Yahoo CSV → 归一化 → 合并进 features.bin」的细则见下方「update_data_to_bin 内部步骤」。
#
# -----------------------------------------------------------------------------
# update_data_to_bin（Python）内部大致步骤（便于对照日志）
# -----------------------------------------------------------------------------
#   1) 检查 qlib_data_1d_dir 是否为合法 Qlib 目录；若不完整可能自动拉官方包打底
#   2) 读 calendars/day.txt 最后一行，推算要从哪一天开始向 Yahoo 补数；end_date 为区间右端（开区间）
#   3) download_data：按 A 股标的列表逐只从 Yahoo 拉指定日期段的原始 CSV 到
#      QLIB_ROOT/scripts/data_collector/yahoo/source/（相对采集目录，非数据根目录）
#   4) normalize_data_1d_extend：与已有日线对齐，做价格等归一化，写到 yahoo/normalize/
#   5) DumpDataUpdate：把 normalize 结果合并进 qlib_data_1d_dir 的 features/，并更新日历、instruments
#   6) 尝试刷新 CSI100 / CSI300 等指数成分到 qlib 目录（与 region 有关）
#
# -----------------------------------------------------------------------------
# 网络说明
# -----------------------------------------------------------------------------
# 本脚本不设置 http(s)_proxy / ALL_PROXY。流量走系统路由（本机 VPN TUN、运营商等）。
# 需能访问：Yahoo（yahooquery）、东方财富（A 股全市场列表分页）等，否则会在 Python 里报错。
#
# -----------------------------------------------------------------------------
# 用法
# -----------------------------------------------------------------------------
#   ./run_cn_incremental_update.sh [qlib_data_1d_dir]
#   QLIB_DATA_1D=~/.qlib/qlib_data/cn_data ./run_cn_incremental_update.sh
#
# 环境变量（可选）
#   CONDA_ENV        默认 ai-trader
#   CONDA_ROOT       优先使用；否则用 conda info --base
#   END_DATE         Yahoo 区间右端 YYYY-MM-DD（开区间，不含该日）；默认「今天」本地日期
#   SKIP_HEALTH=1    跳过脚本末尾的 check_data_health 步骤
#   LOG_DIR / LOG_FILE  日志目录与文件；默认 ~/.qlib/logs/cn_incremental_时间戳.log
#
# 后台运行示例：
#   nohup ./run_cn_incremental_update.sh >>/tmp/qlib_cn.log 2>&1 &
#
# =============================================================================

set -euo pipefail

usage() {
  echo "用法: $0 [qlib_data_1d_dir]"
  echo "默认 qlib_data_1d_dir: ~/.qlib/qlib_data/cn_data"
  echo "环境变量见脚本头部注释。"
}

# ---------- 参数：仅处理 -h / --help ----------
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

# ---------- (A) 路径与参数：Qlib 源码根目录、要被更新的日频 provider 根目录 ----------
# QLIB_ROOT：本脚本在 yahoo/ 下，向上三级到仓库根
QLIB_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
# 第 1 个参数 > 环境变量 QLIB_DATA_1D > 默认 ~/.qlib/qlib_data/cn_data
QLIB_DATA_1D="${1:-${QLIB_DATA_1D:-${HOME}/.qlib/qlib_data/cn_data}}"

# ---------- (A) Conda 环境名（与仓库 .cursor 约定一致，可覆盖）----------
CONDA_ENV="${CONDA_ENV:-ai-trader}"
# ---------- (A) SKIP_HEALTH=1 时跳过文末 check_data_health ----------
SKIP_HEALTH="${SKIP_HEALTH:-0}"
# ---------- (A) 传给 Python 的 --end_date：Yahoo 区间为左闭右开 [start, end) ----------
END_DATE="${END_DATE:-$(date +%Y-%m-%d)}"

# ---------- (A) 日志目录与文件：带时间戳；run_update 里 tee 同步写屏与文件 ----------
LOG_DIR="${LOG_DIR:-${HOME}/.qlib/logs}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/cn_incremental_$(date +%Y%m%d_%H%M%S).log}"

# ---------- (B) 激活 Conda：注入 conda.sh 后 conda activate，避免误用系统 Python ----------
if [[ -n "${CONDA_ROOT:-}" ]]; then
  # shellcheck disable=SC1091
  source "${CONDA_ROOT}/etc/profile.d/conda.sh"
else
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  if [[ -z "${CONDA_BASE}" || ! -f "${CONDA_BASE}/etc/profile.d/conda.sh" ]]; then
    echo "错误: 未找到 conda。请安装 Miniconda/Anaconda 或设置 CONDA_ROOT。" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source "${CONDA_BASE}/etc/profile.d/conda.sh"
fi
conda activate "${CONDA_ENV}"

# ---------- (C-1) 核心：在 yahoo 目录下执行 update_data_to_bin（详见文件头「内部步骤」）----------
cd "${QLIB_ROOT}/scripts/data_collector/yahoo"

run_update() {
  echo "=== Qlib CN 日频增量（Python: update_data_to_bin）===" | tee -a "${LOG_FILE}"
  echo "QLIB_ROOT=${QLIB_ROOT}" | tee -a "${LOG_FILE}"
  echo "qlib_data_1d_dir=${QLIB_DATA_1D}" | tee -a "${LOG_FILE}"
  echo "end_date=${END_DATE} （Yahoo 下载区间为左闭右开 [start, end)）" | tee -a "${LOG_FILE}"
  echo "日志: ${LOG_FILE}" | tee -a "${LOG_FILE}"
  echo "=====================================================" | tee -a "${LOG_FILE}"
  # --delay：每标的请求间隔（秒），略降 Yahoo 限流概率
  python collector.py update_data_to_bin \
    --qlib_data_1d_dir "${QLIB_DATA_1D}" \
    --end_date "${END_DATE}" \
    --delay 0.5 2>&1 | tee -a "${LOG_FILE}"
}

run_update

# ---------- (C-2) 可选：对 qlib_data_1d_dir 跑日线健康检查；|| true 避免因告警中断 shell ----------
if [[ "${SKIP_HEALTH}" != "1" ]]; then
  echo "=== 数据健康检查 check_data_health.py（SKIP_HEALTH=1 可跳过）===" | tee -a "${LOG_FILE}"
  cd "${QLIB_ROOT}/scripts"
  python check_data_health.py check_data --qlib_dir "${QLIB_DATA_1D}" --freq day 2>&1 | tee -a "${LOG_FILE}" || true
fi

echo "本脚本结束。完整日志: ${LOG_FILE}"
