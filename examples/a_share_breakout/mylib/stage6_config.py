# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Configuration helpers for stage 6 A-share breakout backtests."""

from __future__ import annotations

import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Optional

import pandas as pd
from ruamel.yaml import YAML

import qlib
from qlib.config import C
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config


EXAMPLE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROVIDER_URI = "~/.qlib/qlib_data/cn_data"
DEFAULT_OUTPUT_DIR = EXAMPLE_DIR / "outputs"
DEFAULT_COST_SCENARIO_PATH = EXAMPLE_DIR / "configs" / "cost_scenarios.yaml"
DEFAULT_WINDOWS = (60, 120)
DEFAULT_DEAL_PRICES = ("open", "vwap")
DEFAULT_COST_SCENARIOS = ("low", "neutral", "high")
DEFAULT_BENCHMARK = "SH000300"
DEFAULT_MARKET = "all"
DEFAULT_DATA_START = "2021-01-01"
DEFAULT_DATA_END = "2026-04-17"
DEFAULT_FIT_START = "2021-01-01"
DEFAULT_FIT_END = "2023-12-31"
DEFAULT_VALID_START = "2024-01-01"
DEFAULT_VALID_END = "2024-12-31"
DEFAULT_TEST_START = "2025-01-01"
DEFAULT_BACKTEST_START = "2025-01-02"
DEFAULT_BACKTEST_END = "2026-04-17"
DEFAULT_SIGNAL_MODE = "current"
DEFAULT_ACTIVE_WINDOW = 20
DEFAULT_HOLD_ATR_BUFFER = 1.2
DEFAULT_HOLD_REQUIRES_MA = True
DEFAULT_HOLD_THRESH = 20
FILTER_KWARGS = (
    "min_score",
    "min_breakout_strength",
    "min_relative_strength_rank",
    "min_volume_persistence_rank",
    "min_amount_rank",
    "max_atr_noise_rank",
    "max_fake_prob",
    "max_limit_dependency",
)


@dataclass(frozen=True)
class CostScenario:
    name: str
    label: str
    open_cost: float
    close_cost: float
    impact_cost: float
    min_cost: float
    note: str = ""

    def to_exchange_kwargs(self, deal_price: str, limit_threshold: float = 0.095) -> Dict[str, object]:
        return {
            "limit_threshold": limit_threshold,
            "deal_price": deal_price,
            "open_cost": self.open_cost,
            "close_cost": self.close_cost,
            "impact_cost": self.impact_cost,
            "min_cost": self.min_cost,
        }


def _read_yaml(path: Path) -> MutableMapping[str, object]:
    yaml = YAML(typ="safe", pure=True)
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.load(fp)
    if not isinstance(data, MutableMapping):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def load_cost_scenarios(path: Path = DEFAULT_COST_SCENARIO_PATH) -> Dict[str, CostScenario]:
    raw = _read_yaml(path)
    scenarios = raw.get("cost_scenarios")
    if not isinstance(scenarios, Mapping):
        raise ValueError(f"Missing cost_scenarios mapping in {path}")

    parsed: Dict[str, CostScenario] = {}
    required = {"open_cost", "close_cost", "impact_cost", "min_cost"}
    for name, values in scenarios.items():
        if not isinstance(values, Mapping):
            raise ValueError(f"Cost scenario {name!r} must be a mapping")
        missing = required - set(values)
        if missing:
            raise ValueError(f"Cost scenario {name!r} missing keys: {sorted(missing)}")
        parsed[str(name)] = CostScenario(
            name=str(name),
            label=str(values.get("label", name)),
            open_cost=float(values["open_cost"]),
            close_cost=float(values["close_cost"]),
            impact_cost=float(values["impact_cost"]),
            min_cost=float(values["min_cost"]),
            note=str(values.get("note", "")),
        )
    return parsed


def baseline_id(breakout_window: int, deal_price: str) -> str:
    return f"baseline_{int(breakout_window)}d_{deal_price}"


def run_id(breakout_window: int, deal_price: str, scenario_name: str) -> str:
    return f"{baseline_id(breakout_window, deal_price)}_{scenario_name}_cost"


def infer_board(instrument: str) -> str:
    code = str(instrument).upper()
    if code.startswith("SH68"):
        return "科创板"
    if code.startswith("SZ30"):
        return "创业板"
    if code.startswith("BJ"):
        return "北交所"
    if code.startswith(("SH60", "SZ00")):
        return "主板"
    return "其他"


def build_dataset_config(
    *,
    breakout_window: int,
    benchmark: str,
    market: str,
    data_start: str,
    data_end: str,
    fit_start: str,
    fit_end: str,
    valid_start: str,
    valid_end: str,
    test_start: str,
) -> Dict[str, object]:
    data_handler_config = {
        "start_time": data_start,
        "end_time": data_end,
        "fit_start_time": fit_start,
        "fit_end_time": fit_end,
        "instruments": market,
        "breakout_window": int(breakout_window),
        "benchmark_instrument": benchmark,
        "infer_processors": [],
        "learn_processors": [],
    }
    return {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": "AShareBreakoutRuleHandler",
                "module_path": "mylib.handler",
                "kwargs": data_handler_config,
            },
            "segments": {
                "train": [data_start, fit_end],
                "valid": [valid_start, valid_end],
                "test": [test_start, data_end],
            },
        },
    }


def build_model_config(
    breakout_window: int,
    *,
    signal_mode: str = DEFAULT_SIGNAL_MODE,
    active_window: int = DEFAULT_ACTIVE_WINDOW,
    hold_atr_buffer: float = DEFAULT_HOLD_ATR_BUFFER,
    hold_requires_ma: bool = DEFAULT_HOLD_REQUIRES_MA,
    min_score: Optional[float] = None,
    min_breakout_strength: Optional[float] = None,
    min_relative_strength_rank: Optional[float] = None,
    min_volume_persistence_rank: Optional[float] = None,
    min_amount_rank: Optional[float] = None,
    max_atr_noise_rank: Optional[float] = None,
    max_fake_prob: Optional[float] = None,
    max_limit_dependency: Optional[float] = None,
) -> Dict[str, object]:
    kwargs = {
        "breakout_window": int(breakout_window),
        "signal_mode": signal_mode,
        "active_window": int(active_window),
        "hold_atr_buffer": float(hold_atr_buffer),
        "hold_requires_ma": bool(hold_requires_ma),
    }
    filter_values = {
        "min_score": min_score,
        "min_breakout_strength": min_breakout_strength,
        "min_relative_strength_rank": min_relative_strength_rank,
        "min_volume_persistence_rank": min_volume_persistence_rank,
        "min_amount_rank": min_amount_rank,
        "max_atr_noise_rank": max_atr_noise_rank,
        "max_fake_prob": max_fake_prob,
        "max_limit_dependency": max_limit_dependency,
    }
    kwargs.update({key: float(value) for key, value in filter_values.items() if value is not None})
    return {
        "class": "RuleSignalModel",
        "module_path": "mylib.model",
        "kwargs": kwargs,
    }


def build_port_analysis_config(
    *,
    pred: Optional[pd.DataFrame] = None,
    deal_price: str,
    scenario: CostScenario,
    backtest_start: str,
    backtest_end: str,
    benchmark: str,
    topk: int = 10,
    n_drop: int = 3,
    hold_thresh: int = DEFAULT_HOLD_THRESH,
    risk_degree: float = 0.95,
    account: int = 100000000,
) -> Dict[str, object]:
    signal = "<PRED>" if pred is None else pred
    return {
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy",
            "kwargs": {
                "signal": signal,
                "topk": int(topk),
                "n_drop": int(n_drop),
                "hold_thresh": int(hold_thresh),
                "risk_degree": float(risk_degree),
                "only_tradable": True,
            },
        },
        "backtest": {
            "start_time": backtest_start,
            "end_time": backtest_end,
            "account": int(account),
            "benchmark": benchmark,
            "exchange_kwargs": scenario.to_exchange_kwargs(deal_price=deal_price),
        },
    }


def init_qlib(provider_uri: str, mlruns_dir: Path) -> None:
    if str(EXAMPLE_DIR) not in sys.path:
        sys.path.insert(0, str(EXAMPLE_DIR))
    exp_manager = copy.deepcopy(C["exp_manager"])
    exp_manager["kwargs"]["uri"] = "file:" + str(mlruns_dir.resolve())
    qlib.init(provider_uri=provider_uri, region=REG_CN, exp_manager=exp_manager)


def generate_prediction(
    *,
    breakout_window: int,
    benchmark: str,
    market: str,
    data_start: str,
    data_end: str,
    fit_start: str,
    fit_end: str,
    valid_start: str,
    valid_end: str,
    test_start: str,
    signal_mode: str = DEFAULT_SIGNAL_MODE,
    active_window: int = DEFAULT_ACTIVE_WINDOW,
    hold_atr_buffer: float = DEFAULT_HOLD_ATR_BUFFER,
    hold_requires_ma: bool = DEFAULT_HOLD_REQUIRES_MA,
    min_score: Optional[float] = None,
    min_breakout_strength: Optional[float] = None,
    min_relative_strength_rank: Optional[float] = None,
    min_volume_persistence_rank: Optional[float] = None,
    min_amount_rank: Optional[float] = None,
    max_atr_noise_rank: Optional[float] = None,
    max_fake_prob: Optional[float] = None,
    max_limit_dependency: Optional[float] = None,
) -> pd.DataFrame:
    dataset = init_instance_by_config(
        build_dataset_config(
            breakout_window=breakout_window,
            benchmark=benchmark,
            market=market,
            data_start=data_start,
            data_end=data_end,
            fit_start=fit_start,
            fit_end=fit_end,
            valid_start=valid_start,
            valid_end=valid_end,
            test_start=test_start,
        )
    )
    model = init_instance_by_config(
        build_model_config(
            breakout_window,
            signal_mode=signal_mode,
            active_window=active_window,
            hold_atr_buffer=hold_atr_buffer,
            hold_requires_ma=hold_requires_ma,
            min_score=min_score,
            min_breakout_strength=min_breakout_strength,
            min_relative_strength_rank=min_relative_strength_rank,
            min_volume_persistence_rank=min_volume_persistence_rank,
            min_amount_rank=min_amount_rank,
            max_atr_noise_rank=max_atr_noise_rank,
            max_fake_prob=max_fake_prob,
            max_limit_dependency=max_limit_dependency,
        )
    )
    model.fit(dataset)
    pred = model.predict(dataset, segment="test")
    if isinstance(pred, pd.Series):
        pred = pred.to_frame("score")
    pred = pred.sort_index()
    pred.index = pred.index.set_names(["datetime", "instrument"])
    return pred
