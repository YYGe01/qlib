#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Sync a selected Qlib universe into a lightweight prediction data directory."""

from __future__ import annotations

import argparse
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger("update_predict_data")


@dataclass(frozen=True)
class SyncStats:
    instruments: int = 0
    copied_files: int = 0
    skipped_files: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy selected instruments from a source Qlib data directory into a prediction data directory."
    )
    parser.add_argument("--source-uri", default="~/.qlib/qlib_data/cn_data", help="Full or upstream Qlib data dir.")
    parser.add_argument(
        "--target-uri",
        default="~/.qlib/qlib_data/cn_predict_csi300",
        help="Lightweight Qlib data dir used by daily prediction.",
    )
    parser.add_argument("--market", default="csi300", help="Instrument file name under source instruments/.")
    parser.add_argument("--instruments-file", default=None, help="Optional custom instrument list file.")
    parser.add_argument(
        "--target-market-name",
        default=None,
        help="Instrument file name to write under target instruments/. Defaults to --market or predict.",
    )
    parser.add_argument(
        "--delete-stale",
        action="store_true",
        help="Delete target feature directories that are not in the selected universe.",
    )
    return parser.parse_args()


def resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def read_symbols(path: Path) -> list[str]:
    symbols: list[str] = []
    with path.open("r", encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.split("#", maxsplit=1)[0].replace(",", " ").strip()
            if not line:
                continue
            symbols.append(line.split()[0].upper())
    if not symbols:
        raise ValueError(f"No instruments were found in {path}")
    return sorted(dict.fromkeys(symbols))


def read_instrument_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.strip()
            if not line:
                continue
            symbol = line.split()[0].upper()
            rows[symbol] = line
    return rows


def load_selected_symbols(source_uri: Path, market: str, instruments_file: str | None) -> list[str]:
    if instruments_file:
        return read_symbols(resolve_path(instruments_file))

    market_path = source_uri / "instruments" / f"{market.lower()}.txt"
    if not market_path.exists():
        raise FileNotFoundError(f"Source market instruments file not found: {market_path}")
    return read_symbols(market_path)


def write_target_instruments(source_uri: Path, target_uri: Path, symbols: list[str], target_market_name: str) -> None:
    target_inst_dir = target_uri / "instruments"
    target_inst_dir.mkdir(parents=True, exist_ok=True)

    source_all = source_uri / "instruments" / "all.txt"
    source_rows = read_instrument_rows(source_all) if source_all.exists() else {}
    rows = [
        source_rows.get(symbol, f"{symbol}\t1900-01-01\t2099-12-31")
        for symbol in symbols
    ]
    content = "\n".join(rows) + "\n"
    (target_inst_dir / "all.txt").write_text(content, encoding="utf-8")
    (target_inst_dir / f"{target_market_name.lower()}.txt").write_text(content, encoding="utf-8")


def copy_file_if_changed(src: Path, dst: Path) -> bool:
    if dst.exists() and dst.stat().st_size == src.stat().st_size and dst.stat().st_mtime_ns >= src.stat().st_mtime_ns:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def copy_tree_incremental(src_dir: Path, dst_dir: Path) -> tuple[int, int]:
    copied = 0
    skipped = 0
    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        dst_file = dst_dir / src_file.relative_to(src_dir)
        if copy_file_if_changed(src_file, dst_file):
            copied += 1
        else:
            skipped += 1
    return copied, skipped


def sync_prediction_data(
    source_uri: Path,
    target_uri: Path,
    market: str = "csi300",
    instruments_file: str | None = None,
    target_market_name: str | None = None,
    delete_stale: bool = False,
) -> SyncStats:
    source_uri = resolve_path(source_uri)
    target_uri = resolve_path(target_uri)
    if not source_uri.exists():
        raise FileNotFoundError(f"Source Qlib data directory not found: {source_uri}")

    symbols = load_selected_symbols(source_uri, market, instruments_file)
    target_market_name = target_market_name or (market if not instruments_file else "predict")

    calendars_src = source_uri / "calendars"
    if calendars_src.exists():
        copy_tree_incremental(calendars_src, target_uri / "calendars")
    else:
        raise FileNotFoundError(f"Source calendars directory not found: {calendars_src}")

    write_target_instruments(source_uri, target_uri, symbols, target_market_name)

    copied = 0
    skipped = 0
    target_features = target_uri / "features"
    target_features.mkdir(parents=True, exist_ok=True)
    selected_feature_dirs = {symbol.lower() for symbol in symbols}

    for symbol in symbols:
        src_feature_dir = source_uri / "features" / symbol.lower()
        if not src_feature_dir.exists():
            LOGGER.warning("Feature directory is missing for %s: %s", symbol, src_feature_dir)
            continue
        copied_i, skipped_i = copy_tree_incremental(src_feature_dir, target_features / symbol.lower())
        copied += copied_i
        skipped += skipped_i

    if delete_stale:
        for feature_dir in target_features.iterdir():
            if feature_dir.is_dir() and feature_dir.name not in selected_feature_dirs:
                shutil.rmtree(feature_dir)

    return SyncStats(instruments=len(symbols), copied_files=copied, skipped_files=skipped)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    stats = sync_prediction_data(
        source_uri=Path(args.source_uri),
        target_uri=Path(args.target_uri),
        market=args.market,
        instruments_file=args.instruments_file,
        target_market_name=args.target_market_name,
        delete_stale=args.delete_stale,
    )
    LOGGER.info(
        "Synced %s instruments into %s, copied=%s, skipped=%s",
        stats.instruments,
        resolve_path(args.target_uri),
        stats.copied_files,
        stats.skipped_files,
    )


if __name__ == "__main__":
    main()
