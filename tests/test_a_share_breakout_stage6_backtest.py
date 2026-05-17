import sys
from pathlib import Path

import pandas as pd
import pytest
from ruamel.yaml import YAML


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "a_share_breakout"
sys.path.insert(0, str(EXAMPLE_DIR))

from mylib.stage6_config import (  # noqa: E402
    CostScenario,
    build_port_analysis_config,
    load_cost_scenarios,
)
from mylib.stage6_metrics import build_cost_sensitivity, extract_portfolio_summary  # noqa: E402
from mylib.stage6_report import write_markdown_report  # noqa: E402


def test_cost_scenarios_load_exchange_costs():
    scenarios = load_cost_scenarios(EXAMPLE_DIR / "configs" / "cost_scenarios.yaml")

    assert set(scenarios) == {"low", "neutral", "high"}
    assert scenarios["neutral"].to_exchange_kwargs("vwap") == {
        "limit_threshold": 0.095,
        "deal_price": "vwap",
        "open_cost": 0.0005,
        "close_cost": 0.0015,
        "impact_cost": 0.0005,
        "min_cost": 5.0,
    }


def test_port_analysis_config_uses_topk_dropout_and_impact_cost():
    scenario = CostScenario("neutral", "中性成本", 0.0005, 0.0015, 0.0005, 5)
    config = build_port_analysis_config(
        deal_price="open",
        scenario=scenario,
        backtest_start="2025-01-02",
        backtest_end="2026-04-17",
        benchmark="SH000300",
        hold_thresh=5,
    )

    assert config["strategy"]["class"] == "TopkDropoutStrategy"
    assert config["strategy"]["kwargs"]["only_tradable"] is True
    assert config["strategy"]["kwargs"]["hold_thresh"] == 5
    assert config["backtest"]["exchange_kwargs"]["deal_price"] == "open"
    assert config["backtest"]["exchange_kwargs"]["impact_cost"] == 0.0005


def test_extract_summary_and_cost_sensitivity_from_sample_report():
    idx = pd.date_range("2025-01-02", periods=3, freq="D", name="datetime")
    report = pd.DataFrame(
        {
            "return": [0.01, -0.02, 0.03],
            "cost": [0.001, 0.002, 0.001],
            "bench": [0.005, -0.01, 0.01],
            "turnover": [0.2, 0.1, 0.3],
            "account": [101.0, 99.0, 102.0],
        },
        index=idx,
    )
    analysis_index = pd.MultiIndex.from_tuples(
        [
            ("excess_return_without_cost", "annualized_return"),
            ("excess_return_without_cost", "information_ratio"),
            ("excess_return_without_cost", "max_drawdown"),
            ("excess_return_with_cost", "annualized_return"),
            ("excess_return_with_cost", "information_ratio"),
            ("excess_return_with_cost", "max_drawdown"),
        ]
    )
    analysis = pd.DataFrame({"risk": [0.30, 1.2, -0.05, 0.20, 0.8, -0.06]}, index=analysis_index)
    pred_idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2025-01-01", "2025-01-02"]), ["SH600000", "SZ300001"]],
        names=["datetime", "instrument"],
    )
    pred = pd.DataFrame({"score": [1.0, 2.0, 3.0, 4.0]}, index=pred_idx)
    positions = {
        idx[0]: {
            "SH600000": {"weight": 0.5, "count_day": 2},
            "SZ300001": {"weight": 0.4, "count_day": 1},
            "cash": 0.1,
        }
    }
    scenario = CostScenario("neutral", "中性成本", 0.0005, 0.0015, 0.0005, 5)

    summary, yearly, board = extract_portfolio_summary(
        report=report,
        analysis_df=analysis,
        positions=positions,
        recorder_path="mlruns/1/abc",
        pred=pred,
        breakout_window=60,
        deal_price="open",
        scenario=scenario,
        backtest_start="2025-01-02",
        backtest_end="2026-04-17",
    )
    sensitivity = build_cost_sensitivity(pd.DataFrame([summary | {"cost_scenario": "low"}, summary]))

    assert summary["baseline"] == "baseline_60d_open"
    assert summary["excess_ann_return_with_cost"] == 0.20
    assert summary["avg_holding_days_proxy"] == pytest.approx(5.0)
    assert yearly.loc[0, "year"] == 2025
    assert set(board["board"]) == {"主板", "创业板"}
    assert "delta_vs_low_cost_excess_ann_return" in sensitivity.columns


def test_stage6_workflow_configs_cover_four_neutral_baselines():
    yaml = YAML(typ="safe", pure=True)
    expected = {
        "workflow_baseline_60d_open.yaml": (60, "open"),
        "workflow_baseline_60d_vwap.yaml": (60, "vwap"),
        "workflow_baseline_120d_open.yaml": (120, "open"),
        "workflow_baseline_120d_vwap.yaml": (120, "vwap"),
    }

    for filename, (window, deal_price) in expected.items():
        with (EXAMPLE_DIR / "configs" / filename).open(encoding="utf-8") as fp:
            config = yaml.load(fp)
        handler = config["task"]["dataset"]["kwargs"]["handler"]["kwargs"]
        model = config["task"]["model"]["kwargs"]
        exchange = config["port_analysis_config"]["backtest"]["exchange_kwargs"]

        assert config["experiment_name"] == f"a_share_breakout_baseline_{window}d_{deal_price}_neutral"
        assert handler["breakout_window"] == window
        assert model["breakout_window"] == window
        assert exchange["deal_price"] == deal_price
        assert exchange["open_cost"] == 0.0005
        assert exchange["close_cost"] == 0.0015
        assert exchange["impact_cost"] == 0.0005


def test_stage6_report_includes_strategy_params_and_output_prefix(tmp_path):
    summary = pd.DataFrame(
        [
            {
                "baseline": "baseline_60d_open",
                "recorder": "mlruns/1/abc",
                "cost_scenario": "neutral",
                "breakout_window": 60,
                "deal_price": "open",
                "topk": 10,
                "n_drop": 1,
                "hold_thresh": 5,
                "annualized_return_with_cost": -0.10,
                "excess_ann_return_with_cost": -0.20,
                "max_drawdown_with_cost": -0.30,
                "excess_information_ratio_with_cost": -1.5,
                "avg_turnover": 0.04,
                "avg_holding_days_proxy": 25.0,
            }
        ]
    )
    cost_sensitivity = pd.DataFrame(
        [
            {
                "baseline": "baseline_60d_open",
                "breakout_window": 60,
                "deal_price": "open",
                "cost_scenario": "neutral",
                "excess_ann_return_with_cost": -0.20,
                "delta_vs_low_cost_excess_ann_return": -0.05,
                "annualized_cost": 0.03,
            }
        ]
    )
    audit = pd.DataFrame(
        [
            {
                "breakout_window": 60,
                "deal_price": "open",
                "board": "ALL",
                "execution_rows": 100,
                "missing_deal_price_rate": 0.01,
                "tradable_proxy_rate": 0.99,
                "missing_close": 0,
                "zero_or_missing_volume": 1,
            }
        ]
    )

    output_path = tmp_path / "report.md"
    write_markdown_report(
        summary=summary,
        cost_sensitivity=cost_sensitivity,
        audit=audit,
        output_path=output_path,
        output_prefix="turnover_hold5_",
    )

    report = output_path.read_text(encoding="utf-8")
    assert "| baseline_60d_open | `mlruns/1/abc` | 10 | 1 | 5 |" in report
    assert "`turnover_hold5_baseline_backtest_summary.csv`" in report
