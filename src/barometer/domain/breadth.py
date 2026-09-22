"""市場廣度（ToDo §7.1、§9 第八批 8-2）。純函式、零 I/O、不引 pandas。

⚠️ **這是 proxy，不是真的 advance/decline。** 它量的是「11 檔 SPDR 類股 ETF
裡有幾檔站上自己的 200 日均線」，不是上漲家數除以下跌家數。兩者在方向上常常
一致，但它們不是同一個東西 —— 頁面與判定文字都要照實說。

⚠️ **分母要跟著比例一起出去。** 缺一檔的時候比例用剩下的算，7/10 與 7/11
是兩件事；分母自己是一條 OBSERVE 序列，不進分數。
"""
from __future__ import annotations

Series = list[tuple[str, float]]


def breadth_series(closes_by_symbol: dict[str, Series], window: int = 200,
                   days: int = 30) -> tuple[Series, Series]:
    """回 (站上均線的比例%, 當日有效分母)，兩條都由舊到新。

    一檔標的在某一天只有在**它自己**湊得出 `window` 根收盤時才進得了那一天的
    分母 —— 湊不出來就兩邊都不算，不是當成「跌破均線」。
    """
    by_symbol = {symbol: sorted(rows) for symbol, rows in closes_by_symbol.items()}
    labels = sorted({label for rows in by_symbol.values() for label, _ in rows})

    ratio: Series = []
    cover: Series = []
    for label in labels[-days:] if days else labels:
        above = 0
        available = 0
        for rows in by_symbol.values():
            history = [value for day, value in rows if day <= label]
            if len(history) < window:
                continue
            available += 1
            if history[-1] > sum(history[-window:]) / window:
                above += 1
        if available == 0:
            continue
        ratio.append((label, 100.0 * above / available))
        cover.append((label, float(available)))
    return ratio, cover
