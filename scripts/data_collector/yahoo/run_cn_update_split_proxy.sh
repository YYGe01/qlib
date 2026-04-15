#!/usr/bin/env bash
# 中国区日线增量辅助脚本：东财相关域名走直连（NO_PROXY），Yahoo（yahooquery）走 WSL2 网关 SOCKS5。
# A 股列表默认优先 Baostock（开源）；失败时回退东财。可用 QLIB_HS_SYMBOLS_SOURCE=eastmoney 强制仅用东财。
# 用法：./run_cn_update_split_proxy.sh [qlib_data_1d_dir]，默认 ~/.qlib/qlib_data/cn_data
set -euo pipefail
QLIB_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
GW="$(ip route show default | awk '{print $3}')"
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY 2>/dev/null || true
export ALL_PROXY="socks5h://${GW}:7897"
export NO_PROXY="localhost,127.0.0.1,127.0.0.0/8,.eastmoney.com,eastmoney.com,push2.eastmoney.com,99.push2.eastmoney.com,push2his.eastmoney.com,www.szse.cn,szse.cn"
export no_proxy="${NO_PROXY}"

QLIB_DATA_1D="${1:-${HOME}/.qlib/qlib_data/cn_data}"

CONDA_ROOT="${CONDA_ROOT:-${HOME}/miniconda3}"
# shellcheck disable=SC1091
source "${CONDA_ROOT}/etc/profile.d/conda.sh"
conda activate rdagent

END_DATE="$(date +%Y-%m-%d)"
cd "${QLIB_ROOT}/scripts/data_collector/yahoo"
exec python collector.py update_data_to_bin \
  --qlib_data_1d_dir "${QLIB_DATA_1D}" \
  --end_date "${END_DATE}" \
  --delay 0.5
