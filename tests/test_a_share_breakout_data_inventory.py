import importlib.util
import sys
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).resolve().parents[1] / "examples" / "a_share_breakout" / "data_inventory.py"
SPEC = importlib.util.spec_from_file_location("a_share_breakout_data_inventory", MODULE_PATH)
assert SPEC is not None
data_inventory = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = data_inventory
SPEC.loader.exec_module(data_inventory)

classify_board = data_inventory.classify_board
read_feature_slice = data_inventory.read_feature_slice


def test_classify_board_by_a_share_prefix():
    assert classify_board("SH600000") == "main_board"
    assert classify_board("SZ000001") == "main_board"
    assert classify_board("SZ002001") == "main_board"
    assert classify_board("SZ300001") == "chinext"
    assert classify_board("SH688001") == "star_market"
    assert classify_board("BJ430017") == "beijing"
    assert classify_board("SH900901") == "b_share"
    assert classify_board("SZ200001") == "b_share"
    assert classify_board("SZ399300") == "index_or_fund_or_other"


def test_read_feature_slice_aligns_qlib_binary_to_requested_calendar_window(tmp_path: Path):
    feature_dir = tmp_path / "features" / "sh600000"
    feature_dir.mkdir(parents=True)
    np.hstack([[2], [10.0, np.nan, 12.0]]).astype("<f").tofile(feature_dir / "close.day.bin")

    result = read_feature_slice(tmp_path, "SH600000", "close", start_idx=0, end_idx=5)

    assert result.exists is True
    assert result.storage_start_idx == 2
    assert result.storage_end_idx == 4
    np.testing.assert_allclose(result.values[[2, 4]], np.array([10.0, 12.0]))
    assert np.isnan(result.values[[0, 1, 3, 5]]).all()
