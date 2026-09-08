"""Shioaji adapter（ToDo §6、§4.2）。

額度（不得調低）：
  日流量 **500MB**（08:00 重置）
  行情查詢 10 秒 ≤ 50 次
  盤中 ticks ≤ 10 次、kbars ≤ 270 次
  同 ID 連線 ≤ 5、每日登入 ≤ 1000 次

**超流量的後果不是報錯，是行情查詢直接回空值** —— 程式會以為「那天沒資料」。
所以每次跑完必須呼叫 api.usage() 把 remaining_bytes 記進 run log，
不然不知道離上限多遠。這是這個 adapter 最重要的一條規則。

只在本機、只在每日對帳那一次抓（§4.4 第 4 點：shioaji 不做每日比對）。
K 線分批每批 ≤ 30 日曆日。
"""
from __future__ import annotations

import datetime as dt

from barometer.datasources.base import COUNTER, FetchError, Throttle
from barometer.domain.ports import PriceBar

SOURCE = "shioaji"

# 行情查詢 10 秒 ≤ 50 次 → 0.2 秒/次是上限，這裡取 0.3 留餘裕
_THROTTLE = Throttle(min_interval=0.3)

MAX_BATCH_DAYS = 30  # K 線每批 ≤ 30 日曆日


def _contract(api, symbol: str):
    """把本專案的代號對到 shioaji 合約。

    加權指數不是 ^TWII —— 要走 Indexs，代號是 TSE001（§11 待確認第 6 項，
    這裡實作時確認）。個股與 ETF 走 Stocks。
    """
    code = symbol.replace(".TW", "").replace(".TWO", "")
    if symbol == "^TWII":
        return api.Contracts.Indexs.TSE["001"]
    stock = api.Contracts.Stocks[code]
    if stock is None:
        raise FetchError(f"shioaji 找不到合約 {code}")
    return stock


def _login(api_key: str, secret_key: str, simulation: bool):
    import shioaji as sj

    api = sj.Shioaji(simulation=simulation)
    api.login(api_key=api_key, secret_key=secret_key, fetch_contract=True)
    return api


def fetch_daily(
    symbol: str,
    start: dt.date,
    end: dt.date,
    as_of: dt.datetime | None = None,
) -> tuple[list[PriceBar], dict]:
    """抓一檔的日 K。回 (bars, usage)。

    usage 一定要往上傳到 run log —— 見模組 docstring 的理由。
    """
    from barometer import secrets_store

    api_key, secret_key, simulation = secrets_store.shioaji_credentials()
    if not (api_key and secret_key):
        raise FetchError("shioaji 憑證不可用（可能是換了機器，需重新輸入）")

    as_of = as_of or dt.datetime.now()
    api = _login(api_key, secret_key, simulation)
    try:
        contract = _contract(api, symbol)
        bars: list[PriceBar] = []

        # 分批，每批 <= 30 日曆日
        cursor = start
        while cursor <= end:
            batch_end = min(cursor + dt.timedelta(days=MAX_BATCH_DAYS - 1), end)
            _THROTTLE.wait()
            COUNTER.bump(SOURCE)
            kb = api.kbars(
                contract,
                start=cursor.isoformat(),
                end=batch_end.isoformat(),
            )
            bars.extend(_kbars_to_daily(symbol, kb, as_of))
            cursor = batch_end + dt.timedelta(days=1)

        usage = _usage(api)
        return bars, usage
    finally:
        try:
            api.logout()
        except Exception:  # noqa: BLE001 — 登出失敗不該蓋掉真正的結果
            pass


def _usage(api) -> dict:
    """api.usage() 的結果。抓不到就明說抓不到，不要回 0 假裝沒事。"""
    try:
        u = api.usage()
        return {
            "connections": getattr(u, "connections", None),
            "bytes": getattr(u, "bytes", None),
            "limit_bytes": getattr(u, "limit_bytes", None),
            "remaining_bytes": getattr(u, "remaining_bytes", None),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"api.usage() 失敗：{exc}"}


def _kbars_to_daily(symbol: str, kb, as_of: dt.datetime) -> list[PriceBar]:
    """shioaji 回的是分 K，這裡聚合成日 K。

    量的單位：個股與 ETF 的 K 線量是**張**，這裡乘 1000 換成股 ——
    內部一律存股（§1 第 10 條）。既有專案在這裡留過一個「標題寫張、資料
    其實是股」的 bug，所以換算只做一次、只在這裡做。

    **指數不套這個換算**：指數的「量」不是張數，乘 1000 只會得到一個沒有
    意義的大數字。實測 ^TWII 兩家的量差約 2000 倍而價格完全對得上 ——
    差的是定義，不是資料品質（見 tests/domain/test_index_volume.py）。
    """
    from barometer.config import is_index

    import pandas as pd

    lot_multiplier = 1 if is_index(symbol) else 1000

    df = pd.DataFrame({**kb})
    if df.empty:
        return []

    df["ts"] = pd.to_datetime(df["ts"])
    df["date"] = df["ts"].dt.date

    out: list[PriceBar] = []
    for date, g in df.groupby("date"):
        g = g.sort_values("ts")
        volume_raw = float(g["Volume"].sum())
        out.append(
            PriceBar(
                symbol=symbol,
                date=date,
                open=float(g["Open"].iloc[0]),
                high=float(g["High"].max()),
                low=float(g["Low"].min()),
                close=float(g["Close"].iloc[-1]),
                volume_shares=volume_raw * lot_multiplier,  # 張 → 股（指數不換算）
                source=SOURCE,
                as_of=as_of,
            )
        )
    return sorted(out, key=lambda b: b.date)
