import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "a_share_breakout"


def _load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


handler_mod = _load_module("a_share_breakout_rule_handler", EXAMPLE_DIR / "mylib" / "handler.py")
model_mod = _load_module("a_share_breakout_rule_model", EXAMPLE_DIR / "mylib" / "model.py")

RuleSignalModel = model_mod.RuleSignalModel
build_rule_feature_config = handler_mod.build_rule_feature_config


class _Dataset:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def prepare(self, segment, col_set, data_key):
        assert segment in {"train", "test"}
        assert col_set == "feature"
        return self.frame.copy()


def _feature_frame() -> pd.DataFrame:
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2025-01-02", "2025-01-03"]), ["SH600000", "SZ000001", "SH600010"]],
        names=["datetime", "instrument"],
    )
    frame = pd.DataFrame(index=idx)
    frame["BREAKOUT_STRENGTH_60D"] = [1.2, 0.6, 3.0, 0.9, 0.4, 2.0]
    frame["CANDIDATE_60D"] = [1, 1, 0, 1, 0, 1]
    frame["MA20_GT_MA60"] = [1, 1, 1, 0, 1, 1]
    frame["MA20_SLOPE_20"] = [0.05, 0.01, 0.08, -0.02, 0.03, 0.02]
    frame["REL_STRENGTH_20D"] = [0.10, 0.03, 0.20, -0.01, 0.08, 0.05]
    frame["VOL_RATIO_3D"] = [2.0, 1.1, 3.0, 1.2, 0.8, 1.5]
    frame["AMOUNT_RANK_252"] = [0.8, 0.4, 0.9, 0.5, 0.7, 0.9]
    frame["ATR_NOISE_RANK_252"] = [0.2, 0.6, 0.1, 0.5, 0.4, 0.3]
    frame["BB_WIDTH_RANK_252"] = [0.3, 0.5, 0.2, 0.4, 0.8, 0.3]
    frame["FAKE_PROB_DAILY_T_RAW_60D"] = [0.1, 0.8, 0.1, 0.3, 0.2, 0.1]
    frame["LIMIT_DEPENDENCY_SCORE"] = [0.1, 0.8, 0.0, 0.2, 0.1, 0.0]
    return frame


def test_rule_signal_model_scores_only_current_candidates():
    dataset = _Dataset(_feature_frame())
    model = RuleSignalModel(breakout_window=60, signal_mode="current")

    assert model.fit(dataset) is model
    pred = model.predict(dataset)

    assert pred.name == "trend_score"
    assert len(pred) == 4
    assert (pd.Timestamp("2025-01-02"), "SH600010") not in pred.index
    assert (pd.Timestamp("2025-01-03"), "SZ000001") not in pred.index
    assert pred.loc[(pd.Timestamp("2025-01-02"), "SH600000")] > pred.loc[
        (pd.Timestamp("2025-01-02"), "SZ000001")
    ]


def test_rule_signal_model_keeps_recent_breakouts_active_for_holding():
    frame = _feature_frame()
    idx = pd.MultiIndex.from_product(
        [pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]), ["SH600000"]],
        names=["datetime", "instrument"],
    )
    active_frame = frame.iloc[:1].reindex(idx).ffill()
    active_frame["CANDIDATE_60D"] = [1, 0, 0, 0]
    active_frame["BREAKOUT_STRENGTH_60D"] = [1.2, 0.2, -0.6, -0.4]
    model = RuleSignalModel(breakout_window=60, signal_mode="active", active_window=3, hold_atr_buffer=1.2)

    pred = model.predict(_Dataset(active_frame))

    assert (pd.Timestamp("2025-01-02"), "SH600000") in pred.index
    assert (pd.Timestamp("2025-01-03"), "SH600000") in pred.index
    assert (pd.Timestamp("2025-01-06"), "SH600000") in pred.index
    assert (pd.Timestamp("2025-01-07"), "SH600000") not in pred.index


def test_rule_signal_model_applies_quality_filters():
    dataset = _Dataset(_feature_frame())
    model = RuleSignalModel(
        breakout_window=60,
        signal_mode="current",
        min_amount_rank=0.7,
        min_volume_persistence_rank=0.5,
        max_limit_dependency=0.5,
    )

    pred = model.predict(dataset)

    assert (pd.Timestamp("2025-01-02"), "SH600000") in pred.index
    assert (pd.Timestamp("2025-01-02"), "SZ000001") not in pred.index
    assert (pd.Timestamp("2025-01-03"), "SH600000") not in pred.index
    assert (pd.Timestamp("2025-01-03"), "SH600010") in pred.index


def test_rule_signal_model_reports_missing_feature_columns():
    frame = _feature_frame().drop(columns=["REL_STRENGTH_20D"])
    model = RuleSignalModel(breakout_window=60)

    with pytest.raises(ValueError, match="REL_STRENGTH_20D"):
        model.fit(_Dataset(frame))


def test_rule_feature_config_uses_t_visible_fields_for_features():
    fields, names = build_rule_feature_config(breakout_window=120, benchmark_instrument="SH000300")
    joined_fields = "\n".join(fields)

    assert "CANDIDATE_120D" in names
    assert "FAKE_PROB_DAILY_T_RAW_120D" in names
    assert "Ref(Max($close, 120), 1)" in joined_fields
    assert "ChangeInstrument('SH000300'" in joined_fields
    assert "Ref($open, -1)" not in joined_fields
    assert "Ref($close, -1)" not in joined_fields


def test_workflow_config_uses_no_training_rule_model():
    workflow = (EXAMPLE_DIR / "workflow_rule_breakout.yaml").read_text(encoding="utf-8")

    assert "class: RuleSignalModel" in workflow
    assert "signal_mode: current" in workflow
    assert "hold_thresh: 20" in workflow
    assert "class: AShareBreakoutRuleHandler" in workflow
    assert "class: SignalRecord" in workflow
    assert "class: PortAnaRecord" in workflow
    assert "LGBModel" not in workflow
    assert "LightGBM" not in workflow
