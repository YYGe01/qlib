import importlib.util
import sys
from pathlib import Path

import pandas as pd


def load_script_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
daily_predict = load_script_module("daily_predict", SCRIPTS_DIR / "daily_predict.py")
update_predict_data = load_script_module("update_predict_data", SCRIPTS_DIR / "update_predict_data.py")


def test_resolve_instruments_defaults_to_csi300(tmp_path):
    assert daily_predict.resolve_instruments({}, tmp_path) == "csi300"


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


def test_sync_prediction_data_copies_only_selected_universe(tmp_path):
    source = tmp_path / "cn_data"
    target = tmp_path / "cn_predict_csi300"
    (source / "calendars").mkdir(parents=True)
    (source / "calendars" / "day.txt").write_text("2026-04-16\n2026-04-17\n", encoding="utf-8")
    (source / "instruments").mkdir()
    (source / "instruments" / "all.txt").write_text(
        "SH600000\t2000-01-01\t2099-12-31\n"
        "SZ000001\t2000-01-01\t2099-12-31\n"
        "SH600001\t2000-01-01\t2099-12-31\n",
        encoding="utf-8",
    )
    (source / "instruments" / "csi300.txt").write_text(
        "SH600000\t2000-01-01\t2099-12-31\n"
        "SZ000001\t2000-01-01\t2099-12-31\n",
        encoding="utf-8",
    )
    for symbol in ["sh600000", "sz000001", "sh600001"]:
        feature_dir = source / "features" / symbol
        feature_dir.mkdir(parents=True)
        (feature_dir / "close.day.bin").write_bytes(symbol.encode("utf-8"))

    stats = update_predict_data.sync_prediction_data(source, target, market="csi300")

    assert stats.instruments == 2
    assert stats.copied_files == 2
    assert (target / "calendars" / "day.txt").exists()
    assert (target / "features" / "sh600000" / "close.day.bin").exists()
    assert (target / "features" / "sz000001" / "close.day.bin").exists()
    assert not (target / "features" / "sh600001").exists()
    assert (target / "instruments" / "csi300.txt").read_text(encoding="utf-8").splitlines() == [
        "SH600000\t2000-01-01\t2099-12-31",
        "SZ000001\t2000-01-01\t2099-12-31",
    ]

    second_stats = update_predict_data.sync_prediction_data(source, target, market="csi300")

    assert second_stats.copied_files == 0
    assert second_stats.skipped_files == 2
