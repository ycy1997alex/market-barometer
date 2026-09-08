"""Day 26 第 4 項：三組對照算出來。

驗收：`^TWII` vs `0050`、`0050` vs `006208`、`^GSPC` vs `SPY` vs `VOO`
三組差值有數字。

⚠️ **每次撰稿前都要重跑。** §7.1 那張表的台股數字在寫計畫與實作之間就變過
一次（0050 的 2026-09-04 從 NaN 被 Yahoo 補成 107.90，一年報酬因此位移 3.2
個百分點）。任何要寫進文章的數字都不能沿用記在文件裡的那一版。

⚠️ **一個必須講明的近似**：0050 追蹤的是**臺灣 50 指數**，不是加權指數，
而 yfinance 拿不到臺灣 50 指數。拿 `^TWII` 當對照本身就是一個近似，這支
腳本每次都會把這句話印出來 —— 不是禮貌，是怕自己久了就忘記。
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.domain import scoring_index, windows  # noqa: E402
from barometer.storage import csv_audit  # noqa: E402

APPROXIMATION_NOTE = (
    "0050 追蹤的是「臺灣 50 指數」，不是加權指數；yfinance 拿不到臺灣 50 指數"
    "（^TAIEX、0050.TWO 都回空），所以拿 ^TWII 當對照是一個近似，不是等價物。"
)

GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("台股：指數 vs ETF", (config.TW_INDEX, "0050.TW")),
    ("台股：同一指數的兩檔 ETF", ("0050.TW", "006208.TW")),
    ("美股：指數 vs 兩檔 ETF", (config.US_INDEX, "SPY", "VOO")),
)


def _closes(symbol: str) -> tuple[list, list]:
    bars = csv_audit.read_current(symbol)
    return bars, [b.close for b in bars if b.close is not None]


def _year_return(closes: list[float]) -> float | None:
    if len(closes) < 2 or not closes[0]:
        return None
    return (closes[-1] / closes[0] - 1.0) * 100.0


def main() -> int:
    print("=== Day 26 第 4 項：三組對照 ===")
    print(f"注意：{APPROXIMATION_NOTE}\n")

    returns: dict[str, float | None] = {}
    rows: list[tuple[str, int, float, float | None]] = []

    for symbol in config.ALL_SYMBOLS:
        bars, closes = _closes(symbol)
        if not closes:
            print(f"{symbol}: 本機沒有序列 —— 先跑 tools/fetch_day24.py")
            returns[symbol] = None
            continue
        r = _year_return(closes)
        returns[symbol] = r
        rows.append((symbol, len(bars), closes[-1], r))

    print(f"{'標的':<12}{'筆數':>6}{'期末收盤':>14}{'近一年':>10}")
    print("-" * 44)
    for symbol, n, last, r in rows:
        r_txt = f"{r:+.1f}%" if r is not None else "—"
        print(f"{symbol:<12}{n:>6}{last:>14,.2f}{r_txt:>10}")

    print("\n--- 三組差值 ---")
    ok = True
    for title, members in GROUPS:
        vals = [(m, returns.get(m)) for m in members]
        if any(v is None for _, v in vals):
            print(f"{title}: 資料不足，無法比 —— {[m for m, v in vals if v is None]}")
            ok = False
            continue
        base_sym, base = vals[0]
        print(f"\n{title}")
        for sym, v in vals:
            print(f"  {sym:<12}{v:+.1f}%")
        for sym, v in vals[1:]:
            print(f"  → {sym} 對 {base_sym} 差 {abs(v - base):.1f}pp")

    # 追蹤誤差：ETF 特有五項裡唯一算得出來的那一項（§8.2）
    print("\n--- 追蹤誤差（重疊交易日對齊後計算） ---")
    for index_sym, etfs in ((config.TW_INDEX, config.TW_ETFS),
                            (config.US_INDEX, config.US_ETFS)):
        ibars, _ = _closes(index_sym)
        idx_by_date = {b.date: b.close for b in ibars if b.close is not None}
        for etf in etfs:
            ebars, _ = _closes(etf)
            etf_by_date = {b.date: b.close for b in ebars if b.close is not None}
            shared = sorted(set(idx_by_date) & set(etf_by_date))
            if len(shared) < 2:
                print(f"  {etf:<12}資料不足")
                continue
            te = scoring_index.tracking_error(
                [etf_by_date[d] for d in shared], [idx_by_date[d] for d in shared]
            )
            print(f"  {etf:<12}對 {index_sym} {te:+.2f}pp"
                  f"（重疊 {len(shared)} 個交易日）")

    # §10：兩個市場的日期不會對齊，把它印出來而不是假裝沒這回事
    tw_bars, _ = _closes(config.TW_INDEX)
    us_bars, _ = _closes(config.US_INDEX)
    tw_days = windows.last_n_sessions([b.date for b in tw_bars], 5)
    us_days = windows.last_n_sessions([b.date for b in us_bars], 5)
    print("\n--- 最近五個交易日（兩市場不對齊，§10） ---")
    print(f"  台股：{[d.isoformat() for d in tw_days]}")
    print(f"  美股：{[d.isoformat() for d in us_days]}")
    only_tw = sorted(set(tw_days) - set(us_days))
    only_us = sorted(set(us_days) - set(tw_days))
    if only_tw or only_us:
        print(f"  只有台股有：{[d.isoformat() for d in only_tw]}")
        print(f"  只有美股有：{[d.isoformat() for d in only_us]}")
    print("  台股每一天面對的美股收盤：")
    for tw_d, us_d in windows.pair_sessions(tw_days, [b.date for b in us_bars]):
        print(f"    {tw_d} → {us_d if us_d else '（之前沒有美股資料）'}")

    print("\n=== 驗收 ===")
    print("OK 三組差值都有數字" if ok else "FAIL 有組別算不出來")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
