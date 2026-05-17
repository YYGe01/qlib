import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "a_share_breakout" / "event_study.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("a_share_breakout_event_study", MODULE_PATH)
assert SPEC is not None
event_study = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = event_study
SPEC.loader.exec_module(event_study)

aggregate_forward_returns = event_study.aggregate_forward_returns
attach_event_features = event_study.attach_event_features
compute_feature_diagnostics = event_study.compute_feature_diagnostics
enrich_for_segments = event_study.enrich_for_segments
summarize_hac = event_study.summarize_hac
summarize_segments = event_study.summarize_segments


def test_attach_event_features_uses_matching_breakout_window_fake_probability():
    events = pd.DataFrame(
        {
            "event_date": pd.to_datetime(["2024-01-03", "2024-01-03"]),
            "instrument": ["SH600000", "SH600000"],
            "breakout_window": [60, 120],
            "label": ["true_breakout", "false_breakout"],
        }
    )
    feature_rows = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2024-01-03"]),
            "instrument": ["SH600000"],
            "fake_prob_daily_t_60d": [0.25],
            "fake_prob_daily_t_120d": [0.75],
            "relative_strength_20d": [0.03],
        }
    )

    enriched = attach_event_features(events, feature_rows, windows=(60, 120))

    assert enriched.loc[enriched["breakout_window"].eq(60), "fake_prob_daily_t"].iloc[0] == 0.25
    assert enriched.loc[enriched["breakout_window"].eq(120), "fake_prob_daily_t"].iloc[0] == 0.75
    assert enriched["relative_strength_20d"].notna().all()


def test_feature_diagnostics_reports_directional_auc_and_fdr_q_value():
    frame = pd.DataFrame(
        {
            "breakout_window": [60] * 50,
            "event_date": pd.date_range("2024-01-01", periods=50, freq="D"),
            "instrument": [f"SH600{i:03d}" for i in range(50)],
            "label": ["true_breakout"] * 25 + ["false_breakout"] * 25,
            "vol_ratio_3d": np.r_[np.linspace(2.0, 3.0, 25), np.linspace(0.5, 1.0, 25)],
        }
    )

    diagnostics = compute_feature_diagnostics(frame)
    row = diagnostics.loc[diagnostics["feature"].eq("vol_ratio_3d")].iloc[0]

    assert row["true_higher_auc"] == 1.0
    assert row["directional_auc"] == 1.0
    assert row["ks_q_value"] <= 0.05


def test_forward_return_curve_and_hac_summary_use_complete_future_window():
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    events = pd.DataFrame(
        {
            "breakout_window": [60, 60],
            "event_date": pd.to_datetime(["2024-01-02", "2024-01-05"]),
            "instrument": ["SH600000", "SH600000"],
            "label": ["true_breakout", "false_breakout"],
        }
    )
    close = pd.Series([10.0, 11.0, 12.0, 13.2, 12.0, 11.0], index=dates)

    curve, final_returns = aggregate_forward_returns(events, {"SH600000": close}, horizon=2)
    hac = summarize_hac(final_returns, horizon=2)

    true_day2 = curve[
        curve["label"].eq("true_breakout") & curve["relative_day"].eq(2)
    ]["mean_return"].iloc[0]
    assert np.isclose(true_day2, 13.2 / 11.0 - 1.0)
    assert not (curve["label"] == "false_breakout").any()
    assert hac.loc[hac["label"].eq("true_breakout"), "events"].iloc[0] == 1


def test_segment_summary_ignores_ambiguous_when_calculating_true_rate():
    events = pd.DataFrame(
        {
            "breakout_window": [60, 60, 60],
            "event_date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "instrument": ["SH600000", "SH600001", "SH600002"],
            "board": ["main_board", "main_board", "main_board"],
            "label": ["true_breakout", "false_breakout", "ambiguous"],
            "amount_rank_252": [0.9, 0.8, 0.7],
            "atr_pct": [0.03, 0.04, 0.05],
            "breakout_strength_atr": [1.0, 1.2, 1.4],
            "fake_prob_daily_t": [0.2, 0.5, 0.8],
        }
    )

    enriched = enrich_for_segments(events, market_env=pd.DataFrame())
    summary = summarize_segments(enriched)
    board = summary[(summary["section"].eq("board")) & (summary["segment"].eq("main_board"))].iloc[0]

    assert board["events"] == 3
    assert board["true_rate_labeled"] == 0.5
