import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "a_share_breakout" / "breakout_events.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("a_share_breakout_breakout_events", MODULE_PATH)
assert SPEC is not None
breakout_events = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = breakout_events
SPEC.loader.exec_module(breakout_events)

BreakoutParams = breakout_events.BreakoutParams
build_window_events_for_instrument = breakout_events.build_window_events_for_instrument
classify_breakout_labels = breakout_events.classify_breakout_labels
future_window_extremes = breakout_events.future_window_extremes
rolling_past_max = breakout_events.rolling_past_max
rolling_past_percentile_rank = breakout_events.rolling_past_percentile_rank


def test_rolling_breakout_helpers_exclude_current_row():
    values = np.array([1.0, 2.0, 3.0, 2.0, 5.0])

    past_max = rolling_past_max(values, 3)
    rank = rolling_past_percentile_rank(values, 3)

    assert np.isnan(past_max[:3]).all()
    assert past_max[3] == 3.0
    assert past_max[4] == 3.0
    assert rank[4] == 1.0


def test_future_window_extremes_require_complete_future_window():
    values = np.array([10.0, 11.0, 9.0, 12.0, np.nan, 13.0])

    future_max, future_min, complete = future_window_extremes(values, 2)

    assert complete[0]
    assert future_max[0] == 11.0
    assert future_min[0] == 9.0
    assert not complete[2]
    assert not complete[-1]


def test_classify_breakout_labels_keeps_drawdown_as_false_even_after_rally():
    params = BreakoutParams(breakout_window=3, weak_follow_return=0.03, false_breakout_drawdown=-0.06)
    vol_ok = np.array([True, True, False])
    amount_ok = np.array([False, False, False])
    retest_fail = np.array([False, False, False])
    future_max = np.array([0.10, 0.10, 0.02])
    future_min = np.array([-0.02, -0.07, -0.01])

    labels = classify_breakout_labels(vol_ok, amount_ok, retest_fail, future_max, future_min, params)

    assert labels.tolist() == ["true_breakout", "false_breakout", "false_breakout"]


def test_build_window_events_filters_incomplete_future_rows():
    close = np.array(
        [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 11.5, 12.5, 12.7, 12.8, 12.9, 13.0, 13.1, 15.0, 15.2]
    )
    slices = {
        "open": close - 0.1,
        "high": close + 0.2,
        "low": close - 0.2,
        "close": close,
        "volume": np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 220.0, 230.0, 220.0, 210.0, 200.0, 190.0, 180.0, 170.0, 160.0]),
        "amount": np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 220.0, 230.0, 220.0, 210.0, 200.0, 190.0, 180.0, 170.0, 160.0]),
        "factor": np.ones(len(close)),
        "change": np.zeros(len(close)),
    }
    params = BreakoutParams(
        breakout_window=3,
        atr_window=2,
        volume_window=2,
        amount_rank_window=3,
        retest_window=2,
        holding_window=3,
        first_days=0,
        min_history_days=3,
        volume_ratio_threshold=1.0,
        amount_rank_threshold=0.5,
        true_breakout_return=0.05,
    )

    events, stats = build_window_events_for_instrument(
        instrument="SH600000",
        board="main_board",
        calendar=pd.date_range("2024-01-01", periods=len(close), freq="D", name="datetime"),
        start_idx=0,
        analysis_start_idx=0,
        analysis_end_idx=len(close) - 1,
        slices=slices,
        params=params,
    )

    assert stats["candidate_count"] > stats["events_written"]
    assert stats["insufficient_future_count"] > 0
    assert "true_breakout" in set(events["label"])
    assert events["special_event_flags"].eq("none").all()
