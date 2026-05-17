import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


def load_script_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
daily_predict = load_script_module("daily_predict", SCRIPTS_DIR / "daily_predict.py")


def test_resolve_instruments_defaults_to_all(tmp_path):
    assert daily_predict.resolve_instruments({}, tmp_path) == "all"


def test_resolve_instruments_from_file(tmp_path):
    instruments_file = tmp_path / "predict_universe.txt"
    instruments_file.write_text(
        """
        # manual universe
        SH600000
        SZ000001, SH600519
        """,
        encoding="utf-8",
    )

    instruments = daily_predict.resolve_instruments({"instruments_file": str(instruments_file)}, tmp_path)

    assert instruments == ["SH600000", "SZ000001", "SH600519"]


def test_run_data_update_rejects_empty_command(tmp_path):
    config = {"data_update": {"enabled": True, "command": []}}

    with pytest.raises(TypeError, match="data_update.command"):
        daily_predict.run_data_update(config, tmp_path)


def test_run_data_update_formats_update_pool(monkeypatch, tmp_path):
    calls = {}

    def fake_run(command, cwd, check):
        calls["command"] = command
        calls["cwd"] = cwd
        calls["check"] = check

    monkeypatch.setattr(daily_predict.subprocess, "run", fake_run)
    config = {
        "qlib_init": {"provider_uri": "~/.qlib/qlib_data/cn_data"},
        "data_update": {
            "enabled": True,
            "cwd": ".",
            "instruments": ["SH600000", "SZ000001"],
            "command": [
                "python",
                "update.py",
                "--provider-uri",
                "{provider_uri}",
                "--instruments",
                "{data_update_instruments}",
            ],
        },
        "prediction": {"instruments": "all", "date": "latest"},
    }

    daily_predict.run_data_update(config, tmp_path)

    assert calls["command"] == [
        "python",
        "update.py",
        "--provider-uri",
        str(Path("~/.qlib/qlib_data/cn_data").expanduser()),
        "--instruments",
        "SH600000,SZ000001",
    ]
    assert calls["cwd"] == str(tmp_path)
    assert calls["check"] is True


def test_output_path_for_date_uses_template(tmp_path):
    output_path = daily_predict.output_path_for_date(
        {"output_dir": "preds", "output_filename": "{experiment_name}_{date}_{recorder_id}.csv"},
        tmp_path,
        pd.Timestamp("2026-04-17"),
        "lightgbm",
        "abc123",
    )

    assert output_path == tmp_path / "preds" / "lightgbm_2026-04-17_abc123.csv"


def test_prediction_to_result_frame_filters_sorts_and_limits():
    index = pd.MultiIndex.from_tuples(
        [
            (pd.Timestamp("2026-04-16"), "SH600000"),
            (pd.Timestamp("2026-04-17"), "SH600000"),
            (pd.Timestamp("2026-04-17"), "SZ000001"),
            (pd.Timestamp("2026-04-17"), "SH600519"),
        ],
        names=["datetime", "instrument"],
    )
    pred = pd.DataFrame({"score": [0.1, 0.2, 0.4, 0.3]}, index=index)

    result = daily_predict.prediction_to_result_frame(pred, pd.Timestamp("2026-04-17"), topk=2)

    assert result.to_dict("records") == [
        {"datetime": "2026-04-17", "rank": 1, "instrument": "SZ000001", "score": 0.4},
        {"datetime": "2026-04-17", "rank": 2, "instrument": "SH600519", "score": 0.3},
    ]


def test_prediction_to_result_frame_renames_single_score_column():
    index = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2026-04-17"), "SH600000")],
        names=["datetime", "instrument"],
    )
    pred = pd.DataFrame({"prediction": [0.2]}, index=index)

    result = daily_predict.prediction_to_result_frame(pred, pd.Timestamp("2026-04-17"), topk=None)

    assert result.columns.tolist() == ["datetime", "rank", "instrument", "score"]
    assert result.loc[0, "score"] == 0.2
