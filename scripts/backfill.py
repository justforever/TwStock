#!/usr/bin/env python3
"""TwStock 歷史資料回補工具（保留相容用的薄包裝）。

真正的實作在 `python -m twstock_etl.cli backfill …`，這支只是把參數原樣轉過去，
讓 M1 時期寫下的指令與 README 範例繼續能用。用法見 `--help`。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "etl"))

from twstock_etl.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main(["backfill", *sys.argv[1:]]))
