#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Run one-day local inference from a trained Qlib recorder.

The script is intentionally focused on daily prediction.  It does not retrain
models and it does not assume that the prediction data directory is the same as
the full-market training data directory.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
from ruamel.yaml import YAML

import qlib
from qlib.config import C
from qlib.data import D
from qlib.data.dataset.handler import DataHandlerLP
from qlib.workflow import R


LOGGER = logging.getLogger("daily_predict")
DEFAULT_CONFIG = "examples/benchmarks/LightGBM/daily_predict_lightgbm_Alpha158_2026.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily prediction CSV from a trained Qlib recorder.")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to the daily prediction YAML config.")
    parser.add_argument(
        "--date",
        default=None,
        help="Prediction date. Use 'latest' or omit to use latest calendar date.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing result file.")
    parser.add_argument(
        "--skip-data-update",
        action="store_true",
        help="Skip the optional data_update command declared in the config.",
    )
    return parser.parse_args()


def load_config(path: str | Path) -> dict[str, Any]:
    yaml = YAML(typ="safe", pure=True)
    with Path(path).expanduser().open("r", encoding="utf-8") as fp:
        config = yaml.load(fp) or {}
    if not isinstance(config, dict):
        raise TypeError(f"Daily prediction config must be a mapping: {path}")
    return config


def resolve_path(value: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base_dir or Path.cwd()).joinpath(path)


def _resolve_provider_uri(value: Any, base_dir: Path) -> Any:
    if isinstance(value, str):
        return str(resolve_path(value, base_dir))
    if isinstance(value, Mapping):
        return {freq: str(resolve_path(uri, base_dir)) for freq, uri in value.items()}
    return value


def init_qlib_from_config(config: Mapping[str, Any], base_dir: Path) -> None:
    qlib_init = copy.deepcopy(config.get("qlib_init", {}))
    if "provider_uri" in qlib_init:
        qlib_init["provider_uri"] = _resolve_provider_uri(qlib_init["provider_uri"], base_dir)

    if "exp_manager" not in qlib_init:
        exp_uri = config.get("experiment", {}).get("uri", "mlruns")
        exp_manager = copy.deepcopy(C["exp_manager"])
        exp_manager["kwargs"]["uri"] = "file:" + str(resolve_path(exp_uri, base_dir).resolve())
        qlib.init(**qlib_init, exp_manager=exp_manager)
    else:
        qlib.init(**qlib_init)


def run_data_update(config: Mapping[str, Any], base_dir: Path, skip: bool = False) -> None:
    update_config = config.get("data_update", {})
    if skip or not update_config or not update_config.get("enabled", False):
        return

    command = update_config.get("command")
    if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
        raise TypeError("data_update.command must be a list, for example: ['python', 'scripts/update.py']")
    if not all(isinstance(part, str) for part in command):
        raise TypeError("Every item in data_update.command must be a string.")

    cwd = resolve_path(update_config.get("cwd", "."), base_dir)
    LOGGER.info("Running data update command: %s", " ".join(command))
    subprocess.run(list(command), cwd=str(cwd), check=True)


def read_instruments_file(path: str | Path, base_dir: Path) -> list[str]:
    instruments: list[str] = []
    with resolve_path(path, base_dir).open("r", encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.split("#", maxsplit=1)[0].replace(",", " ").strip()
            if not line:
                continue
            instruments.extend(part for part in line.split() if part)
    if not instruments:
        raise ValueError(f"No instruments were found in {path}")
    return instruments


def resolve_instruments(prediction_config: Mapping[str, Any], base_dir: Path) -> str | list[str] | dict[str, Any]:
    if prediction_config.get("instruments_file"):
        return read_instruments_file(prediction_config["instruments_file"], base_dir)

    instruments = prediction_config.get("instruments", "csi300")
    if isinstance(instruments, Mapping) and instruments.get("file"):
        return read_instruments_file(instruments["file"], base_dir)
    if isinstance(instruments, (str, list, tuple, dict)):
        return instruments
    raise TypeError("prediction.instruments must be a market string, list, dict, or instruments_file.")


def resolve_prediction_date(date_value: Any, freq: str) -> pd.Timestamp:
    if date_value is None or str(date_value).lower() == "latest":
        calendar = D.calendar(freq=freq)
    else:
        calendar = D.calendar(end_time=pd.Timestamp(date_value), freq=freq)
    if len(calendar) == 0:
        raise ValueError(f"No trading calendar is available for date={date_value!r}.")
    return pd.Timestamp(calendar[-1])


def resolve_start_date(end_date: pd.Timestamp, history_window: int, freq: str) -> pd.Timestamp:
    if history_window < 0:
        raise ValueError("prediction.history_window must be greater than or equal to 0.")
    calendar = D.calendar(end_time=end_date, freq=freq)
    if len(calendar) == 0:
        raise ValueError(f"No trading calendar is available before {end_date}.")
    return pd.Timestamp(calendar[max(0, len(calendar) - history_window - 1)])


def output_path_for_date(
    prediction_config: Mapping[str, Any],
    base_dir: Path,
    predict_date: pd.Timestamp,
    experiment_name: str,
    recorder_id: str,
) -> Path:
    output_dir = resolve_path(prediction_config.get("output_dir", "predictions/daily"), base_dir)
    filename_template = prediction_config.get("output_filename", "{date}.csv")
    date_text = predict_date.strftime("%Y-%m-%d")
    filename = filename_template.format(date=date_text, experiment_name=experiment_name, recorder_id=recorder_id)
    return output_dir / filename


def configure_dataset_for_prediction(
    dataset: Any,
    instruments: str | list[str] | dict[str, Any],
    start_date: pd.Timestamp,
    predict_date: pd.Timestamp,
) -> Any:
    dataset.config(
        handler_kwargs={
            "instruments": instruments,
            "start_time": start_date,
            "end_time": predict_date,
        },
        segments={"test": (predict_date, predict_date)},
    )
    dataset.setup_data(handler_kwargs={"init_type": DataHandlerLP.IT_LS})
    return dataset


def prediction_to_result_frame(
    pred: pd.Series | pd.DataFrame,
    predict_date: pd.Timestamp,
    topk: int | None,
) -> pd.DataFrame:
    if isinstance(pred, pd.Series):
        pred = pred.to_frame("score")
    if not isinstance(pred, pd.DataFrame):
        raise TypeError(f"model.predict must return a pandas Series or DataFrame, got {type(pred).__name__}.")

    frame = pred.copy()
    if "score" not in frame.columns:
        if len(frame.columns) != 1:
            raise ValueError("Prediction DataFrame must contain a 'score' column or exactly one score column.")
        frame = frame.rename(columns={frame.columns[0]: "score"})

    if not isinstance(frame.index, pd.MultiIndex):
        raise ValueError("Prediction result must use a MultiIndex with datetime and instrument levels.")

    result = frame.reset_index()
    if "datetime" not in result.columns or "instrument" not in result.columns:
        raise ValueError("Prediction index must contain 'datetime' and 'instrument' levels.")

    result["datetime"] = pd.to_datetime(result["datetime"])
    result = result[result["datetime"] == pd.Timestamp(predict_date)].copy()
    if result.empty:
        raise ValueError(f"No prediction rows were generated for {predict_date:%Y-%m-%d}.")

    result = result.sort_values(["score", "instrument"], ascending=[False, True], na_position="last")
    if topk is not None:
        if topk <= 0:
            raise ValueError("prediction.topk must be greater than 0 when it is set.")
        result = result.head(topk).copy()
    result.insert(0, "rank", range(1, len(result) + 1))
    result["datetime"] = result["datetime"].dt.strftime("%Y-%m-%d")
    return result[["datetime", "rank", "instrument", "score"]]


def save_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    manifest_path = path.with_suffix(".json")
    with manifest_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2, sort_keys=True)


def run_daily_prediction(config: Mapping[str, Any], base_dir: Path, date_override: str | None, force: bool) -> Path:
    prediction_config = config.get("prediction", {})
    experiment_config = config.get("experiment", {})

    experiment_name = experiment_config.get("name")
    recorder_id = experiment_config.get("recorder_id")
    if not experiment_name or not recorder_id:
        raise ValueError("experiment.name and experiment.recorder_id are required.")

    freq = prediction_config.get("freq", "day")
    predict_date = resolve_prediction_date(date_override or prediction_config.get("date", "latest"), freq)
    output_path = output_path_for_date(prediction_config, base_dir, predict_date, experiment_name, recorder_id)

    if output_path.exists() and not force and not prediction_config.get("overwrite", False):
        LOGGER.info("Prediction file already exists, skip: %s", output_path)
        return output_path

    instruments = resolve_instruments(prediction_config, base_dir)
    history_window = int(prediction_config.get("history_window", 0))
    start_date = resolve_start_date(predict_date, history_window, freq)

    recorder = R.get_recorder(experiment_name=experiment_name, recorder_id=recorder_id)
    model = recorder.load_object("params.pkl")
    dataset = recorder.load_object("dataset")
    dataset = configure_dataset_for_prediction(dataset, instruments, start_date, predict_date)
    pred = model.predict(dataset)

    topk = prediction_config.get("topk")
    result = prediction_to_result_frame(pred, predict_date, int(topk) if topk is not None else None)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path, index=False)

    if prediction_config.get("write_manifest", True):
        save_manifest(
            output_path,
            {
                "date": predict_date.strftime("%Y-%m-%d"),
                "experiment_name": experiment_name,
                "recorder_id": recorder_id,
                "provider_uri": config.get("qlib_init", {}).get("provider_uri"),
                "instruments": instruments if isinstance(instruments, str) else f"{len(instruments)} instruments",
                "rows": int(len(result)),
                "score_nan_count": int(result["score"].isna().sum()),
                "output": str(output_path),
            },
        )

    LOGGER.info("Saved %s prediction rows to %s", len(result), output_path)
    return output_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    base_dir = Path.cwd()
    config = load_config(args.config)

    run_data_update(config, base_dir, skip=args.skip_data_update)
    init_qlib_from_config(config, base_dir)
    run_daily_prediction(config, base_dir, date_override=args.date, force=args.force)


if __name__ == "__main__":
    main()
