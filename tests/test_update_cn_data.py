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
update_cn_data = load_script_module("update_cn_data", SCRIPTS_DIR / "update_cn_data.py")


def test_source_symbol_normalization():
    assert update_cn_data.normalize_instrument_code("000001.SZ") == "SZ000001"
    assert update_cn_data.normalize_instrument_code("600000.SH") == "SH600000"
    assert update_cn_data.yahoo_symbol("SH600000") == "600000.SS"
    assert update_cn_data.baostock_symbol("SZ000001") == "sz.000001"
    assert update_cn_data.source_supports_instrument("baostock", "BJ430047") is False


def test_pool_source_helpers_degrade_unhealthy_source():
    sources = update_cn_data.resolve_source_order("pool", "baostock,yahoo,akshare")
    assert sources == ["baostock", "yahoo", "akshare"]
    assert update_cn_data.parse_source_workers("baostock=1,yahoo=3", sources, max_workers=4) == {
        "baostock": 1,
        "yahoo": 3,
        "akshare": 2,
    }

    args = type(
        "Args",
        (),
        {
            "source_consecutive_failures": 2,
            "source_min_attempts": 20,
            "source_error_rate": 0.8,
            "source_cooldown": 1.0,
            "max_source_cooldown": 10.0,
            "source_disable_after_cooldowns": 2,
        },
    )()
    state = update_cn_data.SourceState("akshare", max_workers=1)
    state.record_attempt()
    state.record_failure("error:ConnectionError")
    update_cn_data.maybe_degrade_source(state, args)
    assert state.disabled is False
    state.record_attempt()
    state.record_failure("error:ConnectionError")
    update_cn_data.maybe_degrade_source(state, args)
    assert state.cooldowns == 1
    assert state.disabled is False
    state.record_attempt()
    state.record_failure("error:ConnectionError")
    state.record_attempt()
    state.record_failure("error:ConnectionError")
    update_cn_data.maybe_degrade_source(state, args)
    assert state.disabled is True


def test_normalize_frame_aligns_to_existing_qlib_scale():
    source_frame = pd.DataFrame(
        {
            "symbol": ["sz000001", "sz000001"],
            "date": ["2026-04-17", "2026-04-20"],
            "open": [11.09, 11.2],
            "high": [11.11, 11.3],
            "low": [10.99, 11.1],
            "close": [11.01, 11.22],
            "volume": [72253042, 80000000],
            "adjclose": [11.01, 11.22],
        }
    )
    index = pd.MultiIndex.from_tuples(
        [("SZ000001", pd.Timestamp("2026-04-17"))],
        names=["instrument", "datetime"],
    )
    old_data = pd.DataFrame(
        {
            "open": [3.766995824950907],
            "high": [3.7737890224487356],
            "low": [3.7330281951666953],
            "close": [3.7398217178108224],
            "volume": [2127122.917398982],
            "factor": [0.3396749794483185],
            "change": [-0.007213699062698975],
        },
        index=index,
    )

    result = update_cn_data.normalize_frame(source_frame, old_data, pd.Timestamp("2026-04-17"))

    assert result["date"].tolist() == ["2026-04-20"]
    assert result["symbol"].tolist() == ["sz000001"]
    assert result.loc[0, "close"] > old_data.iloc[0]["close"]
