# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Markdown reporting helpers for stage 6 breakout backtests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _fmt_pct(value: object) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value) * 100:.2f}%"


def _fmt_num(value: object, digits: int = 2) -> str:
    if pd.isna(value):
        return "NA"
    return f"{float(value):.{digits}f}"


def _output_name(name: str, prefix: str) -> str:
    return f"{prefix}{name}"


def _row_int(row: pd.Series, key: str, default: int) -> int:
    value = row.get(key, default)
    return default if pd.isna(value) else int(value)


def write_markdown_report(
    *,
    summary: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    audit: pd.DataFrame,
    output_path: Path,
    output_prefix: str = "",
) -> None:
    neutral = summary[summary["cost_scenario"] == "neutral"].copy()
    lines = [
        "# A 股日线突破阶段 6 组合回测报告",
        "",
        "本报告由 `examples/a_share_breakout/backtest_rule_breakout.py` 生成。",
        "阶段 6 只验证无训练规则信号的 TopK Dropout MVP，不构成策略有效性结论。",
        "",
        "## 中性成本 baseline",
        "",
        (
            "| baseline | recorder | TopK | n_drop | hold_thresh | 年化收益(成本后) | "
            "成本后超额年化 | 最大回撤 | 超额 IR | 日均换手 | 持有天数代理 |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in neutral.sort_values(["breakout_window", "deal_price"]).iterrows():
        lines.append(
            (
                "| {baseline} | `{recorder}` | {topk} | {n_drop} | {hold_thresh} | "
                "{ann} | {excess} | {mdd} | {ir} | {turnover} | {hold} |"
            ).format(
                baseline=row["baseline"],
                recorder=row["recorder"],
                topk=_row_int(row, "topk", 10),
                n_drop=_row_int(row, "n_drop", 3),
                hold_thresh=_row_int(row, "hold_thresh", 1),
                ann=_fmt_pct(row["annualized_return_with_cost"]),
                excess=_fmt_pct(row["excess_ann_return_with_cost"]),
                mdd=_fmt_pct(row["max_drawdown_with_cost"]),
                ir=_fmt_num(row["excess_information_ratio_with_cost"]),
                turnover=_fmt_pct(row["avg_turnover"]),
                hold=_fmt_num(row["avg_holding_days_proxy"]),
            )
        )

    all_neutral_non_positive = (
        bool((neutral["excess_ann_return_with_cost"] <= 0).all()) if not neutral.empty else False
    )
    has_suspicious = (
        bool(neutral.get("has_suspicious_daily_return", pd.Series(False, index=neutral.index)).fillna(False).any())
        if not neutral.empty
        else False
    )
    lines.extend(
        [
            "",
            (
                "警告：至少一组中性成本 baseline 出现绝对值超过 20% 的单日组合收益，需要先审计成交价、复权和持仓明细，不能直接视为有效策略。"
                if has_suspicious
                else "单日组合收益未触发 20% 异常阈值。"
            ),
            "",
            "## 成本敏感性",
            "",
            "| baseline | cost | 成本后超额年化 | 相对低成本差异 | 年化成本 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for _, row in cost_sensitivity.sort_values(["breakout_window", "deal_price", "cost_scenario"]).iterrows():
        lines.append(
            "| {baseline} | {cost} | {excess} | {delta} | {cost_ann} |".format(
                baseline=row["baseline"],
                cost=row["cost_scenario"],
                excess=_fmt_pct(row["excess_ann_return_with_cost"]),
                delta=_fmt_pct(row["delta_vs_low_cost_excess_ann_return"]),
                cost_ann=_fmt_pct(row["annualized_cost"]),
            )
        )

    audit_all = audit[audit["board"] == "ALL"] if not audit.empty else audit
    lines.extend(
        [
            "",
            "## Open/VWAP 可成交性审计",
            "",
            "| window | deal_price | execution rows | 缺成交价率 | 可交易代理率 | 缺 close | 成交量缺失或为 0 |",
            "|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in audit_all.sort_values(["breakout_window", "deal_price"]).iterrows():
        lines.append(
            "| {window} | {price} | {rows} | {missing} | {tradable} | {missing_close} | {volume} |".format(
                window=int(row["breakout_window"]),
                price=row["deal_price"],
                rows=int(row["execution_rows"]),
                missing=_fmt_pct(row["missing_deal_price_rate"]),
                tradable=_fmt_pct(row["tradable_proxy_rate"]),
                missing_close=int(row["missing_close"]),
                volume=int(row["zero_or_missing_volume"]),
            )
        )

    lines.extend(
        [
            "",
            "## 结论门槛",
            "",
            (
                "中性成本下四组 baseline 的成本后超额年化均不为正；按计划应暂停进入阶段 7，回到事件研究和过滤规则修正。"
                if all_neutral_non_positive
                else "至少一组中性成本 baseline 的成本后超额年化为正；仍需结合年度、板块、成交价和成本压力测试后再决定是否进入阶段 7。"
            ),
            "",
            "## 输出文件",
            "",
            f"- `{_output_name('baseline_backtest_summary.csv', output_prefix)}`：组合回测摘要。",
            f"- `{_output_name('cost_sensitivity.csv', output_prefix)}`：成本敏感性长表。",
            f"- `{_output_name('baseline_yearly_returns.csv', output_prefix)}`：分年度收益、基准和成本。",
            f"- `{_output_name('baseline_board_exposure.csv', output_prefix)}`：持仓板块暴露，非收益贡献归因。",
            f"- `{_output_name('deal_price_availability_audit.csv', output_prefix)}`：open/vwap 可成交性审计。",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
