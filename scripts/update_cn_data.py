#!/usr/bin/env python
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Incrementally update local CN daily Qlib data from public data sources."""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

import qlib
from qlib.data import D

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from dump_bin import DumpDataUpdate


LOGGER = logging.getLogger("update_cn_data")
PRICE_COLUMNS = ("open", "high", "low", "close")
NORMALIZED_COLUMNS = ("open", "high", "low", "close", "volume", "factor", "change")


@dataclass
class SourceState:
    name: str
    max_workers: int
    consecutive_failures: int = 0
    cooldowns: int = 0
    cooldown_until: float = 0.0
    disabled: bool = False
    attempt_count: int = 0
    stats: Counter = field(default_factory=Counter)

    def is_available(self, now: float, active_count: int) -> bool:
        return not self.disabled and now >= self.cooldown_until and active_count < self.max_workers

    def record_attempt(self) -> None:
        self.attempt_count += 1
        self.stats["attempts"] += 1

    def record_success(self) -> None:
        self.stats["success"] += 1
        self.consecutive_failures = 0

    def record_failure(self, reason: str) -> None:
        self.stats[reason] += 1
        self.consecutive_failures += 1

    def record_nonfatal(self, reason: str) -> None:
        self.stats[reason] += 1
        self.consecutive_failures = 0

    @property
    def attempts(self) -> int:
        return int(self.attempt_count)

    @property
    def failures(self) -> int:
        return int(sum(count for key, count in self.stats.items() if key.startswith("error:")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update CN daily Qlib data from Yahoo, Baostock, or AkShare.")
    parser.add_argument("--provider-uri", required=True, help="Qlib data directory to update.")
    parser.add_argument(
        "--source",
        choices=["pool", "akshare", "baostock", "yahoo"],
        default="pool",
        help="Data source used for incremental daily bars. Use pool to load-balance across --sources.",
    )
    parser.add_argument(
        "--sources",
        default="baostock,yahoo,akshare",
        help="Source pool used when --source=pool.",
    )
    parser.add_argument("--instruments", default="all", help="Market name, comma-separated codes, or 'all'.")
    parser.add_argument("--instruments-file", default=None, help="Optional file containing instruments to update.")
    parser.add_argument("--start-date", default=None, help="Inclusive start date. Defaults to one calendar day before latest Qlib date.")
    parser.add_argument(
        "--end-date",
        default="today",
        help="Exclusive end date. Use 'today' to update through the latest available trading day before today.",
    )
    parser.add_argument("--work-dir", default="~/.qlib/stock_data/cn_daily_update", help="Working directory for CSVs.")
    parser.add_argument("--limit", type=int, default=None, help="Limit instruments for benchmark/probe runs.")
    parser.add_argument("--max-workers", type=int, default=4, help="Parallel workers for downloading data.")
    parser.add_argument(
        "--source-workers",
        default="baostock=1,yahoo=3,akshare=2",
        help="Per-source concurrency, for example: baostock=1,yahoo=3,akshare=2.",
    )
    parser.add_argument("--delay", type=float, default=0.0, help="Delay before each source request, in seconds.")
    parser.add_argument("--retry-count", type=int, default=4, help="Maximum attempts per instrument.")
    parser.add_argument("--source-cooldown", type=float, default=30.0, help="Initial cooldown seconds after source degradation.")
    parser.add_argument("--max-source-cooldown", type=float, default=300.0, help="Maximum source cooldown seconds.")
    parser.add_argument(
        "--source-consecutive-failures",
        type=int,
        default=5,
        help="Consecutive source failures before cooldown.",
    )
    parser.add_argument(
        "--source-min-attempts",
        type=int,
        default=20,
        help="Minimum source attempts before error-rate degradation can trigger.",
    )
    parser.add_argument(
        "--source-error-rate",
        type=float,
        default=0.8,
        help="Source error rate threshold for cooldown after --source-min-attempts.",
    )
    parser.add_argument(
        "--source-disable-after-cooldowns",
        type=int,
        default=3,
        help="Disable a source for this run after this many cooldowns.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Download and normalize only; do not write Qlib bin files.")
    parser.add_argument("--keep-work-dir", action="store_true", help="Keep existing work-dir files instead of cleaning them.")
    parser.add_argument("--report-path", default=None, help="Optional JSON report path.")
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def normalize_instrument_code(value: Any) -> str:
    text = str(value).strip().upper()
    if not text:
        return ""
    if "." in text:
        left, right = text.split(".", maxsplit=1)
        if left.isdigit() and right in {"SH", "SS", "SZ", "BJ"}:
            exchange = "SH" if right == "SS" else right
            return f"{exchange}{left.zfill(6)}"
        if right.isdigit() and left in {"SH", "SZ", "BJ"}:
            return f"{left}{right.zfill(6)}"
    if len(text) == 8 and text[:2] in {"SH", "SZ", "BJ"}:
        return text
    if len(text) == 6 and text.isdigit():
        if text.startswith(("60", "68", "90", "00")):
            return f"SH{text}" if text.startswith(("60", "68", "90")) else f"SZ{text}"
        if text.startswith(("20", "30")):
            return f"SZ{text}"
        if text.startswith(("43", "83", "87", "88", "92")):
            return f"BJ{text}"
    return text


def qlib_symbol(instrument: str) -> str:
    return normalize_instrument_code(instrument).lower()


def yahoo_symbol(instrument: str) -> str | None:
    code = normalize_instrument_code(instrument)
    if code.startswith("SH"):
        return f"{code[2:]}.SS"
    if code.startswith("SZ"):
        return f"{code[2:]}.SZ"
    return None


def baostock_symbol(instrument: str) -> str | None:
    code = normalize_instrument_code(instrument)
    if code.startswith("SH"):
        return f"sh.{code[2:]}"
    if code.startswith("SZ"):
        return f"sz.{code[2:]}"
    return None


def read_qlib_calendar(provider_uri: Path) -> list[pd.Timestamp]:
    calendar_path = provider_uri / "calendars" / "day.txt"
    calendar = pd.read_csv(calendar_path, header=None).iloc[:, 0]
    return [pd.Timestamp(item) for item in calendar]


def read_instrument_file(path: Path) -> list[str]:
    instruments: list[str] = []
    with path.open("r", encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.split("#", maxsplit=1)[0].replace(",", " ").strip()
            if not line:
                continue
            first = line.split()[0]
            instrument = normalize_instrument_code(first)
            if instrument:
                instruments.append(instrument)
    return instruments


def resolve_instruments(args: argparse.Namespace, provider_uri: Path) -> list[str]:
    if args.instruments_file:
        instruments = read_instrument_file(resolve_path(args.instruments_file))
    else:
        name = str(args.instruments).strip()
        market_file = provider_uri / "instruments" / f"{name}.txt"
        if name and "," not in name and " " not in name and market_file.exists():
            instruments = read_instrument_file(market_file)
        else:
            instruments = [normalize_instrument_code(item) for item in name.replace(",", " ").split()]
    instruments = sorted({instrument for instrument in instruments if instrument})
    if not instruments:
        raise ValueError("No instruments were resolved for update.")
    return instruments


def resolve_market_name(args: argparse.Namespace, provider_uri: Path) -> str | None:
    if args.instruments_file:
        return None
    name = str(args.instruments).strip()
    if not name or name == "all" or "," in name or " " in name:
        return None
    market_file = provider_uri / "instruments" / f"{name}.txt"
    return name if market_file.exists() else None


def source_supports_instrument(source: str, instrument: str) -> bool:
    code = normalize_instrument_code(instrument)
    if source in {"baostock", "yahoo"}:
        return code.startswith(("SH", "SZ"))
    if source == "akshare":
        return code.startswith(("SH", "SZ"))
    raise ValueError(f"Unsupported source: {source}")


def resolve_source_order(source: str, sources: str) -> list[str]:
    if source != "pool":
        return [source]
    source_order = [item.strip() for item in sources.replace(" ", ",").split(",") if item.strip()]
    invalid = sorted(set(source_order) - {"akshare", "baostock", "yahoo"})
    if invalid:
        raise ValueError(f"Unsupported data sources in --sources: {', '.join(invalid)}")
    if not source_order:
        raise ValueError("--sources must contain at least one source when --source=pool.")
    return list(dict.fromkeys(source_order))


def parse_source_workers(value: str, sources: Iterable[str], max_workers: int) -> dict[str, int]:
    defaults = {"baostock": 1, "yahoo": 3, "akshare": 2}
    workers = {source: min(defaults.get(source, 1), max_workers) for source in sources}
    for item in str(value).replace(",", " ").split():
        if "=" not in item:
            continue
        source, raw_count = item.split("=", maxsplit=1)
        source = source.strip()
        if source not in workers:
            continue
        workers[source] = max(1, min(int(raw_count), max_workers))
    return workers


def resolve_end_date(value: str) -> pd.Timestamp:
    if str(value).lower() == "today":
        return pd.Timestamp.today().normalize()
    return pd.Timestamp(value).normalize()


def default_start_date(calendar: list[pd.Timestamp]) -> pd.Timestamp:
    if not calendar:
        raise ValueError("Qlib calendar is empty.")
    return pd.Timestamp(calendar[-1]) - pd.Timedelta(days=1)


def clean_work_dir(work_dir: Path, keep: bool) -> tuple[Path, Path]:
    source_dir = work_dir / "source"
    normalize_dir = work_dir / "normalize"
    for directory in (source_dir, normalize_dir):
        directory.mkdir(parents=True, exist_ok=True)
        if keep:
            continue
        for path in directory.glob("*.csv"):
            path.unlink()
    return source_dir, normalize_dir


def to_source_frame(raw: pd.DataFrame, instrument: str) -> pd.DataFrame:
    if raw.empty:
        return raw
    frame = raw.copy()
    frame["symbol"] = qlib_symbol(instrument)
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    frame = frame[["symbol", "date", "open", "high", "low", "close", "volume", "adjclose"]]
    for column in ["open", "high", "low", "close", "volume", "adjclose"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["date"]).sort_values("date")


def fetch_yahoo(instrument: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    symbol = yahoo_symbol(instrument)
    if symbol is None:
        return pd.DataFrame()
    from yahooquery import Ticker

    raw = Ticker(symbol, asynchronous=False).history(
        interval="1d",
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
    )
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return pd.DataFrame()
    frame = raw.reset_index()
    if "date" not in frame.columns:
        return pd.DataFrame()
    frame["adjclose"] = frame.get("adjclose", frame["close"])
    return to_source_frame(frame, instrument)


def fetch_baostock(instrument: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    symbol = baostock_symbol(instrument)
    if symbol is None:
        return pd.DataFrame()
    import baostock as bs

    query_end = (end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    rs = bs.query_history_k_data_plus(
        symbol,
        "date,code,open,high,low,close,volume,amount,adjustflag",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=query_end,
        frequency="d",
        adjustflag="3",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=rs.fields)
    frame["adjclose"] = frame["close"]
    return to_source_frame(frame, instrument)


def fetch_akshare(instrument: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    code = normalize_instrument_code(instrument)
    import akshare as ak

    start_text = start.strftime("%Y%m%d")
    end_text = (end - pd.Timedelta(days=1)).strftime("%Y%m%d")
    if code in {"SH000300", "SH000903", "SH000905"}:
        raw = ak.stock_zh_index_daily(symbol=code.lower())
        if raw.empty:
            return raw
        raw["date"] = pd.to_datetime(raw["date"])
        raw = raw[(raw["date"] >= start) & (raw["date"] < end)]
        raw["adjclose"] = raw["close"]
        return to_source_frame(raw, instrument)
    if code.startswith(("SH", "SZ")):
        raw = ak.stock_zh_a_hist(symbol=code[2:], period="daily", start_date=start_text, end_date=end_text, adjust="")
        if raw.empty:
            return raw
        frame = raw.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
            }
        )
        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce") * 100
        frame["adjclose"] = frame["close"]
        return to_source_frame(frame, instrument)
    return pd.DataFrame()


def load_old_data(provider_uri: Path, instruments: list[str], latest_date: pd.Timestamp) -> pd.DataFrame:
    qlib.init(provider_uri=str(provider_uri), expression_cache=None, dataset_cache=None, region="cn")
    fields = [f"${column}" for column in NORMALIZED_COLUMNS]
    data = D.features(instruments, fields, start_time=latest_date, end_time=latest_date, freq="day")
    data.columns = list(NORMALIZED_COLUMNS)
    return data


def normalize_frame(source_frame: pd.DataFrame, old_data: pd.DataFrame, latest_date: pd.Timestamp) -> pd.DataFrame:
    frame = source_frame.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.drop_duplicates("date").sort_values("date")
    frame = frame[frame["date"] >= latest_date]
    if frame.empty or latest_date not in set(frame["date"]):
        return pd.DataFrame()

    for column in ["open", "high", "low", "close", "volume", "adjclose"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame.loc[(frame["volume"] <= 0) | frame["volume"].isna(), [*PRICE_COLUMNS, "volume", "adjclose"]] = np.nan
    frame["change"] = frame["close"].ffill() / frame["close"].ffill().shift(1) - 1
    frame["factor"] = frame["adjclose"] / frame["close"]
    frame["factor"] = frame["factor"].ffill().fillna(1)
    for column in PRICE_COLUMNS:
        frame[column] = frame[column] * frame["factor"]
    frame["volume"] = frame["volume"] / frame["factor"]

    first_close = frame["close"].dropna().iloc[0]
    for column in NORMALIZED_COLUMNS:
        if column == "change":
            continue
        if column == "volume":
            frame[column] = frame[column] * first_close
        else:
            frame[column] = frame[column] / first_close

    instrument = normalize_instrument_code(frame["symbol"].iloc[0])
    if instrument not in old_data.index.get_level_values("instrument"):
        normalized = frame[frame["date"] > latest_date].copy()
    else:
        old_symbol = old_data.loc[instrument]
        if latest_date not in old_symbol.index:
            return pd.DataFrame()
        old_latest = old_symbol.loc[latest_date]
        new_latest = frame.loc[frame["date"] == latest_date].iloc[0]
        for column in NORMALIZED_COLUMNS[:-1]:
            if pd.isna(new_latest[column]) or pd.isna(old_latest[column]):
                continue
            if column == "volume":
                frame[column] = frame[column] / (new_latest[column] / old_latest[column])
            else:
                frame[column] = frame[column] * (old_latest[column] / new_latest[column])
        normalized = frame[frame["date"] > latest_date].copy()

    if normalized.empty:
        return normalized
    normalized["date"] = normalized["date"].dt.strftime("%Y-%m-%d")
    return normalized[["date", "symbol", *NORMALIZED_COLUMNS]].reset_index(drop=True)


def fetch_from_source(
    source: str,
    instrument: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    delay: float,
) -> pd.DataFrame:
    if delay > 0:
        time.sleep(delay)
    fetchers = {"akshare": fetch_akshare, "baostock": fetch_baostock, "yahoo": fetch_yahoo}
    return fetchers[source](instrument, start, end)


def select_source(
    instrument: str,
    states: Mapping[str, SourceState],
    source_order: list[str],
    active_counts: Counter,
    tried_sources: set[str],
    rng: random.Random,
) -> tuple[str | None, str]:
    now = time.monotonic()
    supporting = [source for source in source_order if source_supports_instrument(source, instrument)]
    if not supporting:
        return None, "unsupported"
    usable = [source for source in supporting if not states[source].disabled]
    if not usable:
        return None, "disabled"
    available = [source for source in usable if states[source].is_available(now, active_counts[source])]
    if not available:
        return None, "wait"
    untried = [source for source in available if source not in tried_sources]
    return rng.choice(untried or available), "selected"


def maybe_degrade_source(state: SourceState, args: argparse.Namespace) -> None:
    now = time.monotonic()
    attempts = state.attempts
    failure_rate = state.failures / attempts if attempts else 0.0
    should_cooldown = state.consecutive_failures >= args.source_consecutive_failures
    should_cooldown = should_cooldown or (
        attempts >= args.source_min_attempts and failure_rate >= args.source_error_rate
    )
    if not should_cooldown:
        return

    state.cooldowns += 1
    state.consecutive_failures = 0
    if state.cooldowns >= args.source_disable_after_cooldowns:
        state.disabled = True
        LOGGER.warning("Disable source=%s for this run after %s cooldowns.", state.name, state.cooldowns)
        return

    cooldown = min(args.max_source_cooldown, args.source_cooldown * (2 ** max(0, state.cooldowns - 1)))
    state.cooldown_until = now + cooldown
    LOGGER.warning("Cooldown source=%s for %.1fs after failures.", state.name, cooldown)


def wait_for_next_source(states: Mapping[str, SourceState]) -> None:
    now = time.monotonic()
    wakeups = [
        state.cooldown_until
        for state in states.values()
        if not state.disabled and state.cooldown_until > now
    ]
    if not wakeups:
        time.sleep(0.1)
        return
    time.sleep(min(max(min(wakeups) - now, 0.1), 5.0))


def load_balanced_update(
    instruments: list[str],
    source_order: list[str],
    source_dir: Path,
    normalize_dir: Path,
    provider_uri: Path,
    start: pd.Timestamp,
    end: pd.Timestamp,
    args: argparse.Namespace,
) -> dict[str, Any]:
    calendar = read_qlib_calendar(provider_uri)
    latest_date = pd.Timestamp(calendar[-1])
    old_data = load_old_data(provider_uri, instruments, latest_date)
    source_workers = parse_source_workers(args.source_workers, source_order, max(1, args.max_workers))
    states = {
        source: SourceState(source, source_workers[source])
        for source in source_order
    }
    active_counts: Counter = Counter()
    attempts: Counter = Counter()
    tried_sources: dict[str, set[str]] = defaultdict(set)
    source_counts: Counter = Counter()
    unresolved: dict[str, str] = {}
    completed: dict[str, str] = {}
    stats: dict[str, Any] = {
        "downloaded": 0,
        "normalized": 0,
        "rows": 0,
        "unsupported": 0,
        "unresolved": 0,
    }

    shuffled_instruments = list(instruments)
    random.shuffle(shuffled_instruments)
    pending = deque(shuffled_instruments)
    rng = random.Random()
    in_flight: dict[Any, tuple[str, str]] = {}

    if "baostock" in source_order:
        import baostock as bs

        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"Baostock login failed: {login.error_code} {login.error_msg}")

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as executor:
            while pending or in_flight:
                scheduled = False
                scan_count = len(pending)
                for _ in range(scan_count):
                    if len(in_flight) >= max(1, args.max_workers):
                        break
                    instrument = pending.popleft()
                    if instrument in completed or instrument in unresolved:
                        continue
                    source, status = select_source(
                        instrument,
                        states,
                        source_order,
                        active_counts,
                        tried_sources[instrument],
                        rng,
                    )
                    if status == "unsupported":
                        unresolved[instrument] = "unsupported"
                        stats["unsupported"] += 1
                        continue
                    if status == "disabled":
                        unresolved[instrument] = "all_sources_disabled"
                        continue
                    if source is None:
                        pending.append(instrument)
                        continue

                    attempts[instrument] += 1
                    tried_sources[instrument].add(source)
                    active_counts[source] += 1
                    states[source].record_attempt()
                    future = executor.submit(fetch_from_source, source, instrument, start, end, args.delay)
                    in_flight[future] = (instrument, source)
                    scheduled = True

                if not in_flight:
                    if pending and not scheduled:
                        wait_for_next_source(states)
                    continue

                done, _ = wait(in_flight.keys(), timeout=1.0, return_when=FIRST_COMPLETED)
                for future in done:
                    instrument, source = in_flight.pop(future)
                    active_counts[source] -= 1
                    reason = ""
                    try:
                        source_frame = future.result()
                        if source_frame.empty:
                            reason = "empty"
                        else:
                            normalized = normalize_frame(source_frame, old_data, latest_date)
                            if normalized.empty:
                                reason = "normalize_empty"
                            else:
                                source_frame.to_csv(source_dir / f"{qlib_symbol(instrument)}.csv", index=False)
                                normalized.to_csv(normalize_dir / f"{qlib_symbol(instrument)}.csv", index=False)
                                states[source].record_success()
                                completed[instrument] = source
                                source_counts[source] += 1
                                stats["downloaded"] += 1
                                stats["normalized"] += 1
                                stats["rows"] += int(len(normalized))
                                continue
                    except Exception as exc:  # noqa: BLE001
                        reason = f"error:{type(exc).__name__}"

                    if reason.startswith("error:"):
                        states[source].record_failure(reason)
                        maybe_degrade_source(states[source], args)
                    else:
                        states[source].record_nonfatal(reason)

                    if attempts[instrument] < args.retry_count:
                        pending.append(instrument)
                    else:
                        unresolved[instrument] = reason
    finally:
        if "baostock" in source_order:
            import baostock as bs

            bs.logout()

    stats["unresolved"] = len(unresolved)
    return {
        "stats": stats,
        "source_counts": dict(source_counts),
        "source_states": {
            source: {
                "max_workers": state.max_workers,
                "disabled": state.disabled,
                "cooldowns": state.cooldowns,
                "stats": dict(state.stats),
            }
            for source, state in states.items()
        },
        "unresolved": unresolved,
        "attempts": dict(attempts),
        "completed": completed,
    }


def dump_update(normalize_dir: Path, provider_uri: Path, max_workers: int) -> None:
    DumpDataUpdate(
        data_path=str(normalize_dir),
        qlib_dir=str(provider_uri),
        freq="day",
        max_workers=max_workers,
        exclude_fields="symbol,date",
    ).dump()


def sync_market_instrument_file(
    provider_uri: Path,
    market_name: str,
    anchor_date: pd.Timestamp,
    target_date: pd.Timestamp,
    updated_instruments: Iterable[str],
) -> dict[str, Any]:
    market_file = provider_uri / "instruments" / f"{market_name}.txt"
    if not market_file.exists():
        raise FileNotFoundError(f"Market instrument file not found: {market_file}")

    frame = pd.read_csv(
        market_file,
        sep=r"\s+",
        header=None,
        names=["instrument", "start", "end"],
        dtype=str,
    )
    if frame.empty:
        raise ValueError(f"Market instrument file is empty: {market_file}")

    updated_set = {normalize_instrument_code(instrument) for instrument in updated_instruments}
    file_instruments = frame["instrument"].map(normalize_instrument_code)
    start_dates = pd.to_datetime(frame["start"], errors="coerce")
    end_dates = pd.to_datetime(frame["end"], errors="coerce")
    anchor = pd.Timestamp(anchor_date).normalize()
    target = pd.Timestamp(target_date).normalize()
    mask = file_instruments.isin(updated_set) & start_dates.le(anchor) & end_dates.ge(anchor)

    updated_rows = int(mask.sum())
    if updated_rows > 0:
        frame.loc[mask, "end"] = target.strftime("%Y-%m-%d")
        frame.to_csv(market_file, sep="\t", header=False, index=False)

    return {
        "market_name": market_name,
        "path": str(market_file),
        "anchor_date": anchor.strftime("%Y-%m-%d"),
        "target_date": target.strftime("%Y-%m-%d"),
        "updated_rows": updated_rows,
    }


def write_report(report: Mapping[str, Any], path: str | Path | None) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        report_path = resolve_path(path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(payload + "\n", encoding="utf-8")
    LOGGER.info("Update report:\n%s", payload)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    start_time = time.perf_counter()

    provider_uri = resolve_path(args.provider_uri)
    calendar = read_qlib_calendar(provider_uri)
    old_latest_date = pd.Timestamp(calendar[-1])
    start = pd.Timestamp(args.start_date).normalize() if args.start_date else default_start_date(calendar)
    end = resolve_end_date(args.end_date)
    if end <= start:
        raise ValueError(f"end-date must be after start-date: start={start:%Y-%m-%d}, end={end:%Y-%m-%d}")

    source_order = resolve_source_order(args.source, args.sources)
    source_dir, normalize_dir = clean_work_dir(resolve_path(args.work_dir) / args.source, args.keep_work_dir)
    market_name = resolve_market_name(args, provider_uri)
    resolved_instruments = resolve_instruments(args, provider_uri)
    unsupported_instruments = [
        instrument
        for instrument in resolved_instruments
        if not any(source_supports_instrument(source, instrument) for source in source_order)
    ]
    instruments = [
        instrument
        for instrument in resolved_instruments
        if any(source_supports_instrument(source, instrument) for source in source_order)
    ]
    if args.limit is not None:
        instruments = instruments[: args.limit]
    if not instruments:
        raise ValueError(f"No instruments are supported by source_order={source_order}.")
    LOGGER.info(
        "Updating %s instruments from %s, range=[%s, %s), dry_run=%s, skipped_unsupported=%s",
        len(instruments),
        ",".join(source_order),
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        args.dry_run,
        len(unsupported_instruments),
    )

    update_start = time.perf_counter()
    update_result = load_balanced_update(
        instruments,
        source_order,
        source_dir,
        normalize_dir,
        provider_uri,
        start,
        end,
        args,
    )
    update_seconds = time.perf_counter() - update_start

    dump_seconds = 0.0
    market_instrument_sync: dict[str, Any] | None = None
    if not args.dry_run and update_result["stats"]["normalized"] > 0:
        dump_start = time.perf_counter()
        dump_update(normalize_dir, provider_uri, max_workers=max(1, args.max_workers))
        dump_seconds = time.perf_counter() - dump_start
        if market_name and args.limit is not None:
            market_instrument_sync = {"market_name": market_name, "skipped": "limit_set"}
        elif market_name:
            new_latest_date = pd.Timestamp(read_qlib_calendar(provider_uri)[-1])
            if new_latest_date > old_latest_date:
                market_instrument_sync = sync_market_instrument_file(
                    provider_uri,
                    market_name,
                    old_latest_date,
                    new_latest_date,
                    update_result["completed"].keys(),
                )
            else:
                market_instrument_sync = {"market_name": market_name, "skipped": "calendar_not_advanced"}
    elif market_name:
        market_instrument_sync = {
            "market_name": market_name,
            "skipped": "dry_run" if args.dry_run else "no_normalized_data",
        }

    total_seconds = time.perf_counter() - start_time
    report = {
        "source": args.source,
        "sources": source_order,
        "provider_uri": str(provider_uri),
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date_exclusive": end.strftime("%Y-%m-%d"),
        "instruments_requested": len(instruments),
        "instruments_resolved": len(resolved_instruments),
        "instruments_unsupported": len(unsupported_instruments),
        "update": update_result["stats"],
        "source_counts": update_result["source_counts"],
        "source_states": update_result["source_states"],
        "unresolved": update_result["unresolved"],
        "dry_run": args.dry_run,
        "seconds": {
            "update": round(update_seconds, 3),
            "dump": round(dump_seconds, 3),
            "total": round(total_seconds, 3),
        },
    }
    if market_instrument_sync is not None:
        report["market_instrument_sync"] = market_instrument_sync
    write_report(report, args.report_path)


if __name__ == "__main__":
    main()
