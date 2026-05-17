import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "a_share_breakout" / "daily_features.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("a_share_breakout_daily_features", MODULE_PATH)
assert SPEC is not None
daily_features = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = daily_features
SPEC.loader.exec_module(daily_features)

FeatureParams = daily_features.FeatureParams
build_feature_dictionary = daily_features.build_feature_dictionary
build_feature_frame_for_instrument = daily_features.build_feature_frame_for_instrument


def _base_slices(next_open: float):
    close = np.array([10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 11.5, 11.6, 11.7, 11.8, 11.9, 12.0])
    open_ = close - 0.05
    open_[7] = next_open
    return {
        "open": open_,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 220.0, 120.0, 120.0, 120.0, 120.0, 120.0]),
        "amount": np.full(len(close), np.nan),
        "factor": np.ones(len(close)),
        "change": np.r_[np.nan, close[1:] / close[:-1] - 1.0],
    }


def _feature_frame(next_open: float) -> pd.DataFrame:
    slices = _base_slices(next_open=next_open)
    params = FeatureParams(
        atr_window=2,
        volume_window=2,
        amount_rank_window=3,
        ma_fast_window=2,
        ma_slow_window=3,
        ma_slope_window=1,
        bb_window=3,
        return_window=2,
        first_days=0,
        min_history_days=3,
        breakout_atr_multiple=0.5,
    )
    return build_feature_frame_for_instrument(
        instrument="SH600000",
        board="main_board",
        calendar=pd.date_range("2024-01-01", periods=len(slices["close"]), freq="D", name="datetime"),
        start_idx=0,
        analysis_start_idx=0,
        analysis_end_idx=len(slices["close"]) - 1,
        slices=slices,
        params=params,
        breakout_windows=(3,),
        benchmark_return=np.zeros(len(slices["close"])),
        benchmark_base_idx=0,
    )


def test_daily_feature_frame_marks_candidate_and_amount_proxy():
    frame = _feature_frame(next_open=10.0)
    event_row = frame.loc[frame["datetime"].eq(pd.Timestamp("2024-01-07"))].iloc[0]

    assert event_row["candidate_3d"]
    assert event_row["amount_rank_source"] == "volume_proxy"
    assert event_row["breakout_level_3d"] == 10.5
    assert event_row["breakout_strength_3d_atr"] > 0.5
    assert np.isfinite(event_row["fake_prob_daily_t_3d"])


def test_t_day_fake_probability_does_not_use_next_open_reversal():
    low_next_open = _feature_frame(next_open=10.0)
    high_next_open = _feature_frame(next_open=12.0)
    low_row = low_next_open.loc[low_next_open["datetime"].eq(pd.Timestamp("2024-01-07"))].iloc[0]
    high_row = high_next_open.loc[high_next_open["datetime"].eq(pd.Timestamp("2024-01-07"))].iloc[0]

    assert low_row["next_open_return_research"] != high_row["next_open_return_research"]
    assert low_row["fake_prob_daily_t_3d"] == high_row["fake_prob_daily_t_3d"]
    assert low_row["fake_prob_daily_research_3d"] != high_row["fake_prob_daily_research_3d"]


def test_feature_dictionary_flags_research_only_and_missing_items():
    dictionary = build_feature_dictionary((3,), benchmark_status="missing")

    relative_strength = dictionary.loc[dictionary["feature_name"].eq("relative_strength_20d")].iloc[0]
    next_open = dictionary.loc[dictionary["feature_name"].eq("next_open_return_research")].iloc[0]
    tail_volume = dictionary.loc[dictionary["feature_name"].eq("tail_30m_volume_share")].iloc[0]

    assert not relative_strength["usable_for_trade_signal"]
    assert next_open["implementation_status"] == "research_only"
    assert not next_open["usable_for_trade_signal"]
    assert tail_volume["implementation_status"] == "not_implemented"
