"""Day 24 第 5 項：台股用 shioaji 再抓一次做交叉比對（§4.2）。

驗收：price_conflict 表有內容或明確為空，且 api.usage() 的 remaining_bytes
進了 run log。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config, secrets_store  # noqa: E402
from barometer.datasources import shioaji_src  # noqa: E402
from barometer.datasources.base import FetchError  # noqa: E402
from barometer.domain.reconcile import cross_check  # noqa: E402
from barometer.pipeline.runlog import RunLog  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402
from barometer.storage.sqlite_repo import SqliteRepo  # noqa: E402

# 只比對最近這段 —— shioaji 按流量計費，不要整年重抓
LOOKBACK_DAYS = 30


def main() -> int:
    if not secrets_store.has_shioaji():
        print("FAIL shioaji 憑證不可用 —— 先跑 tools/setup_secrets.py")
        return 1

    log = RunLog(task="crosscheck_tw")
    repo = SqliteRepo(config.db_path())
    repo.init_schema()
    as_of = dt.datetime.now()
    end = dt.date.today()
    start = end - dt.timedelta(days=LOOKBACK_DAYS)

    total_conflicts = 0
    try:
        for symbol in config.TW_SYMBOLS:
            print(f"\n--- {symbol} ---")
            try:
                sj_bars, usage = shioaji_src.fetch_daily(
                    symbol, start=start, end=end, as_of=as_of
                )
            except FetchError as exc:
                print(f"  shioaji 抓取失敗：{exc}")
                log.note(f"{symbol}: shioaji 失敗 — {exc}")
                log.count("failed")
                continue
            except Exception as exc:  # noqa: BLE001
                print(f"  shioaji 例外：{type(exc).__name__}: {exc}")
                log.note(f"{symbol}: shioaji 例外 — {exc}")
                log.count("failed")
                continue

            log.quota.setdefault("shioaji_usage", usage)
            yf_bars = [
                b for b in csv_audit.read_current(symbol) if start <= b.date <= end
            ]
            print(f"  shioaji {len(sj_bars)} 根 / yfinance {len(yf_bars)} 根")

            # 指數的量兩家定義不同，只比價格（見 tests/domain/test_index_volume.py）
            compare_volume = not config.is_index(symbol)
            if not compare_volume:
                print("  （指數：只比價格，量的定義兩家不同，不比對）")
            merged, conflicts = cross_check(
                sj_bars, yf_bars, compare_volume=compare_volume
            )
            for c in conflicts:
                repo.record_conflict(
                    symbol=c["symbol"], date=c["date"], field=c["field"],
                    shioaji_value=c["shioaji_value"], yf_value=c["yf_value"],
                    taken=c["taken"], as_of=as_of,
                )
            total_conflicts += len(conflicts)
            log.set_count(f"conflicts::{symbol}", len(conflicts))
            print(f"  衝突 {len(conflicts)} 筆（超過容忍：價格 0.1%、量 1%）")
            for c in conflicts[:5]:
                print(f"    {c['date']} {c['field']:6} "
                      f"shioaji={c['shioaji_value']} yf={c['yf_value']} → 取 shioaji")

        log.set_count("conflicts_total", total_conflicts)
        log.finish("partial" if log.counts.get("failed") else "ok")
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    finally:
        repo.close()
    log.append()

    print(f"\n=== 結果 ===")
    print(f"衝突總筆數：{total_conflicts}"
          f"{'（明確為空）' if total_conflicts == 0 else ''}")
    usage = log.quota.get("shioaji_usage", {})
    print(f"shioaji usage：{usage}")
    rb = usage.get("remaining_bytes")
    print(f"remaining_bytes 進 run log：{'是' if rb is not None else '否（' + str(usage.get('error', '未取得')) + '）'}")
    print(f"run log：{config.runlog_path(log.started_at.strftime('%Y-%m'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
