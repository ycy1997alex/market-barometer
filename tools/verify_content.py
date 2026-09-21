"""Compare yesterday's and today's visible site content without changing data.

No arguments captures today's live view into STOCKDATA_ROOT/build/content_snapshots
and compares it to the latest snapshot from an earlier calendar day.
--previous/--current compare two saved JSON snapshots without live reads or writes.
Review findings are reported to people and always exit 0.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402
from barometer.pipeline.build_page import build_tabs  # noqa: E402
from barometer.pipeline.content_check import (  # noqa: E402
    capture_tabs, compare_snapshots, format_report,
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--snapshot-dir", type=Path,
                        default=config.build_dir() / "content_snapshots")
    parser.add_argument("--output", type=Path, help="also save the Markdown report")
    parser.add_argument("--change-pct", type=float, default=25.0)
    parser.add_argument("--min-absolute", type=float, default=5.0)
    parser.add_argument("--score-points", type=float, default=15.0)
    args = parser.parse_args(argv)
    if (args.previous is None) != (args.current is None):
        parser.error("--previous and --current must be provided together")
    if args.change_pct < 0 or args.min_absolute < 0 or args.score_points < 0:
        parser.error("thresholds must be nonnegative")

    if args.current:
        before, today = _read(args.previous), _read(args.current)
    else:
        now = dt.datetime.now(ZoneInfo("Asia/Taipei"))
        today = capture_tabs(build_tabs(), now)
        date = now.date().isoformat()
        older = sorted(path for path in args.snapshot_dir.glob("*.json")
                       if path.stem < date)
        before = _read(older[-1]) if older else None
        _write(args.snapshot_dir / f"{date}.json", today)

    if before is None:
        report = ("# 內容逐格比對\n\n"
                  "目前只有本次快照，已建立比較基準；下個日期再執行即可比對。\n")
    else:
        issues = compare_snapshots(
            before, today, change_pct=args.change_pct,
            min_absolute=args.min_absolute, score_points=args.score_points)
        report = format_report(before, today, issues)
    print(report, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    # The Windows default stdout codec here is cp950. Force UTF-8 before
    # printing Chinese so subprocess callers decoding UTF-8 stay reliable
    # even when PYTHONIOENCODING was not set by the launching shell.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
