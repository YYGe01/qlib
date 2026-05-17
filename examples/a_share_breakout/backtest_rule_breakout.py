# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Stage 6 portfolio backtest runner for the A-share breakout study."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from mylib.stage6_config import (
    DEFAULT_ACTIVE_WINDOW,
    DEFAULT_BACKTEST_END,
    DEFAULT_BACKTEST_START,
    DEFAULT_BENCHMARK,
    DEFAULT_COST_SCENARIO_PATH,
    DEFAULT_COST_SCENARIOS,
    DEFAULT_DATA_END,
    DEFAULT_DATA_START,
    DEFAULT_DEAL_PRICES,
    DEFAULT_FIT_END,
    DEFAULT_FIT_START,
    DEFAULT_HOLD_ATR_BUFFER,
    DEFAULT_HOLD_REQUIRES_MA,
    DEFAULT_HOLD_THRESH,
    DEFAULT_MARKET,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROVIDER_URI,
    DEFAULT_SIGNAL_MODE,
    DEFAULT_TEST_START,
    DEFAULT_VALID_END,
    DEFAULT_VALID_START,
    DEFAULT_WINDOWS,
    generate_prediction,
    init_qlib,
    load_cost_scenarios,
    run_id,
)
from mylib.stage6_metrics import (
    audit_deal_price_availability,
    build_cost_sensitivity,
    run_portfolio_backtest,
)
from mylib.stage6_report import write_markdown_report


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-uri", default=DEFAULT_PROVIDER_URI)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--cost-scenarios", default=str(DEFAULT_COST_SCENARIO_PATH))
    parser.add_argument("--mlruns-dir", default="mlruns")
    parser.add_argument("--market", default=DEFAULT_MARKET)
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--data-start", default=DEFAULT_DATA_START)
    parser.add_argument("--data-end", default=DEFAULT_DATA_END)
    parser.add_argument("--fit-start", default=DEFAULT_FIT_START)
    parser.add_argument("--fit-end", default=DEFAULT_FIT_END)
    parser.add_argument("--valid-start", default=DEFAULT_VALID_START)
    parser.add_argument("--valid-end", default=DEFAULT_VALID_END)
    parser.add_argument("--test-start", default=DEFAULT_TEST_START)
    parser.add_argument("--backtest-start", default=DEFAULT_BACKTEST_START)
    parser.add_argument("--backtest-end", default=DEFAULT_BACKTEST_END)
    parser.add_argument("--breakout-window", type=int, nargs="+", default=list(DEFAULT_WINDOWS))
    parser.add_argument("--deal-price", nargs="+", default=list(DEFAULT_DEAL_PRICES))
    parser.add_argument("--cost-scenario", nargs="+", default=list(DEFAULT_COST_SCENARIOS))
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--n-drop", type=int, default=3)
    parser.add_argument("--hold-thresh", type=int, default=DEFAULT_HOLD_THRESH)
    parser.add_argument("--signal-mode", choices=["current", "active"], default=DEFAULT_SIGNAL_MODE)
    parser.add_argument("--active-window", type=int, default=DEFAULT_ACTIVE_WINDOW)
    parser.add_argument("--hold-atr-buffer", type=float, default=DEFAULT_HOLD_ATR_BUFFER)
    parser.add_argument(
        "--hold-requires-ma",
        action=argparse.BooleanOptionalAction,
        default=DEFAULT_HOLD_REQUIRES_MA,
    )
    parser.add_argument("--risk-degree", type=float, default=0.95)
    parser.add_argument("--account", type=int, default=100000000)
    parser.add_argument("--output-prefix", default="")
    return parser.parse_args(argv)


def run_stage6(args: argparse.Namespace) -> Dict[str, pd.DataFrame]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = load_cost_scenarios(Path(args.cost_scenarios))
    missing = sorted(set(args.cost_scenario) - set(scenarios))
    if missing:
        raise ValueError(f"Unknown cost scenarios: {missing}")
    selected_scenarios = [scenarios[name] for name in args.cost_scenario]

    init_qlib(args.provider_uri, Path(args.mlruns_dir))

    summaries: List[Dict[str, object]] = []
    yearly_frames: List[pd.DataFrame] = []
    board_frames: List[pd.DataFrame] = []
    audit_frames: List[pd.DataFrame] = []

    for window in args.breakout_window:
        print(f"[stage6] generating {window}d prediction")
        pred = generate_prediction(
            breakout_window=window,
            benchmark=args.benchmark,
            market=args.market,
            data_start=args.data_start,
            data_end=args.data_end,
            fit_start=args.fit_start,
            fit_end=args.fit_end,
            valid_start=args.valid_start,
            valid_end=args.valid_end,
            test_start=args.test_start,
            signal_mode=args.signal_mode,
            active_window=args.active_window,
            hold_atr_buffer=args.hold_atr_buffer,
            hold_requires_ma=args.hold_requires_ma,
        )
        print(
            f"[stage6] {window}d prediction rows={len(pred)}, "
            f"instruments={pred.index.get_level_values('instrument').nunique()}"
        )
        audit = audit_deal_price_availability(pred, deal_prices=args.deal_price, backtest_end=args.backtest_end)
        audit.insert(0, "breakout_window", int(window))
        audit_frames.append(audit)

        for deal_price in args.deal_price:
            for scenario in selected_scenarios:
                print(f"[stage6] running {run_id(window, deal_price, scenario.name)}")
                summary, yearly, board = run_portfolio_backtest(
                    pred=pred,
                    breakout_window=window,
                    deal_price=deal_price,
                    scenario=scenario,
                    backtest_start=args.backtest_start,
                    backtest_end=args.backtest_end,
                    benchmark=args.benchmark,
                    topk=args.topk,
                    n_drop=args.n_drop,
                    hold_thresh=args.hold_thresh,
                    risk_degree=args.risk_degree,
                    account=args.account,
                    signal_mode=args.signal_mode,
                    active_window=args.active_window,
                    hold_atr_buffer=args.hold_atr_buffer,
                    hold_requires_ma=args.hold_requires_ma,
                )
                summaries.append(summary)
                yearly_frames.append(yearly)
                if not board.empty:
                    board_frames.append(board)

    summary_df = pd.DataFrame(summaries).sort_values(["breakout_window", "deal_price", "cost_scenario"])
    yearly_df = pd.concat(yearly_frames, ignore_index=True) if yearly_frames else pd.DataFrame()
    board_df = pd.concat(board_frames, ignore_index=True) if board_frames else pd.DataFrame()
    audit_df = pd.concat(audit_frames, ignore_index=True) if audit_frames else pd.DataFrame()
    sensitivity_df = build_cost_sensitivity(summary_df)

    prefix = args.output_prefix
    summary_df.to_csv(output_dir / f"{prefix}baseline_backtest_summary.csv", index=False)
    sensitivity_df.to_csv(output_dir / f"{prefix}cost_sensitivity.csv", index=False)
    yearly_df.to_csv(output_dir / f"{prefix}baseline_yearly_returns.csv", index=False)
    board_df.to_csv(output_dir / f"{prefix}baseline_board_exposure.csv", index=False)
    audit_df.to_csv(output_dir / f"{prefix}deal_price_availability_audit.csv", index=False)
    write_markdown_report(
        summary=summary_df,
        cost_sensitivity=sensitivity_df,
        audit=audit_df,
        output_path=output_dir / f"{prefix}baseline_backtest_report.md",
        output_prefix=prefix,
    )
    return {
        "summary": summary_df,
        "yearly": yearly_df,
        "board": board_df,
        "audit": audit_df,
        "sensitivity": sensitivity_df,
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    run_stage6(parse_args(argv))


if __name__ == "__main__":
    main()
