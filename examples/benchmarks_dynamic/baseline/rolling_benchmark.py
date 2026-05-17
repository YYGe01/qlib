# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
import os
from pathlib import Path
from typing import Union

import fire

from qlib import auto_init
from qlib.contrib.rolling.base import Rolling
from qlib.tests.data import GetData
from qlib.utils.pickle_utils import add_safe_class

DIRNAME = Path(__file__).absolute().resolve().parent


class RollingBenchmark(Rolling):
    # The config in the README.md
    CONF_LIST = [DIRNAME / "workflow_config_linear_Alpha158.yaml", DIRNAME / "workflow_config_lightgbm_Alpha158.yaml"]

    DEFAULT_CONF = CONF_LIST[0]

    def __init__(self, conf_path: Union[str, Path] = DEFAULT_CONF, horizon=20, **kwargs) -> None:
        # This code is for being compatible with the previous old code
        conf_path = Path(conf_path)
        super().__init__(conf_path=conf_path, horizon=horizon, **kwargs)

        for f in self.CONF_LIST:
            if conf_path.samefile(f):
                break
        else:
            self.logger.warning("Model type is not in the benchmark!")


def allow_benchmark_handler_cache() -> None:
    """Allow benchmark handler caches created by the rolling workflow."""
    for module, name in [
        ("qlib.contrib.data.handler", "Alpha158"),
        ("qlib.contrib.data.loader", "QlibDataLoader"),
        ("qlib.data.dataset.loader", "QlibDataLoader"),
        ("qlib.data.dataset.processor", "DropnaLabel"),
        ("qlib.data.dataset.processor", "CSZScoreNorm"),
        ("qlib.data.dataset.processor", "DropnaProcessor"),
        ("qlib.data.dataset.processor", "ProcessInf"),
        ("qlib.data.dataset.processor", "Fillna"),
        ("qlib.utils.data", "zscore"),
    ]:
        add_safe_class(module, name)


if __name__ == "__main__":
    kwargs = {}
    if os.environ.get("PROVIDER_URI", "") == "":
        GetData().qlib_data(exists_skip=True)
    else:
        kwargs["provider_uri"] = os.environ["PROVIDER_URI"]
    allow_benchmark_handler_cache()
    auto_init(**kwargs)
    fire.Fire(RollingBenchmark)
