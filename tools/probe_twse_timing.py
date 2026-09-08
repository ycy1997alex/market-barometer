"""Day 24 第 12 項：實測 18:00 抓台股會不會太早（TWSE 盤後資料公佈時間）。

§3.3 例外：這是一次性的探索腳本，驗收靠眼睛，不寫測試 —— 但它也不進 src/。

跑法：在交易日的不同時間各跑一次，看 T86 什麼時候才有東西。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer.datasources import twse_src  # noqa: E402
from barometer.datasources.base import FetchError  # noqa: E402

LOOKBACK = 7


def main() -> int:
    now = dt.datetime.now()
    print(f"現在時間：{now:%Y-%m-%d %H:%M:%S}（星期{'一二三四五六日'[now.weekday()]}）")
    print(f"排程預定時間：台股 18:00\n")

    print(f"{'日期':<12}{'星期':<6}{'結果':<10}筆數 / 說明")
    print("-" * 76)

    latest_available: dt.date | None = None
    for i in range(LOOKBACK):
        d = now.date() - dt.timedelta(days=i)
        wd = "一二三四五六日"[d.weekday()]
        try:
            rows = twse_src.fetch_t86(d)
            if latest_available is None:
                latest_available = d
            print(f"{d.isoformat():<12}{wd:<6}{'有資料':<10}{len(rows)} 檔")
        except twse_src.NotPublishedYet as exc:
            print(f"{d.isoformat():<12}{wd:<6}{'尚未公布':<10}{exc}")
        except FetchError as exc:
            print(f"{d.isoformat():<12}{wd:<6}{'抓取失敗':<10}{exc}")

    print(f"\n=== 判讀 ===")
    if latest_available is None:
        print("最近 7 天都沒抓到 T86 —— 端點或解析可能有問題，需人工確認")
        return 1

    print(f"最新一個有 T86 的日期：{latest_available}")
    if now.hour < 18:
        print(f"目前是 {now.hour}:{now.minute:02d}，還沒到 18:00 —— "
              f"這一輪測不出「18:00 夠不夠晚」")
    else:
        print(f"目前 {now.hour}:{now.minute:02d} 已過 18:00。")

    if now.weekday() >= 5:
        print("今天是週末，台股沒有開盤 —— "
              "「18:00 會不會太早」只有平日 18:00 整跑一次才答得出來。")
        print("→ 待 9/7–9/10 的排程各跑一次後回頭確認（§11 第 2 項）。")
    else:
        today_ok = latest_available == now.date()
        print(f"今天（{now.date()}）的 T86："
              f"{'已公布' if today_ok else '尚未公布 → 18:00 太早，要往後調'}")

    print("\n提醒：空 CSV 一律當「這天還沒有」，不要當成 0（§10）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
