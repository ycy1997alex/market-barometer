"""總經管線（ToDo §9 Day 25 第 1、2 項）。

驗收：17 項評分指標 + 7 項觀測指標都有值或**明確的失敗原因**，
沒有任何一項讓整輪中止。

失敗策略（§7.3）：
  有舊快取 → 顯示快取值並標「更新失敗，顯示快取（原因）」
  無快取   → 顯示「—」與失敗原因
**單一指標失敗不擋整頁。**
"""
from __future__ import annotations

import datetime as dt
import sys

from barometer import config
from barometer.datasources import (
    cboe_src, cftc_src, eia_src, fred_src, tw_gov_src, yfinance_src)
from barometer.datasources.base import COUNTER, FetchError
from barometer.domain import breadth, freshness, futures
from barometer.domain.coverage import Coverage
from barometer.domain.macro_spec import ALL, SCORED, WORLD, TAIWAN
from barometer.domain.ports import MacroSeries
from barometer.domain.scoring_macro import ALERT_FUNCS, INSUFFICIENT, score_layer, summarize
from barometer.pipeline.runlog import RunLog
from barometer.storage.sqlite_repo import SqliteRepo

YF_PERIOD = "6mo"  # 近 6 個月日線收盤（§7.3）


# 8-1：WALCL 的單位是百萬美元，RRPONTSYD 是十億美元 —— 差一千倍。
# 直接相減不會報錯，只會得到一個看起來很正常的錯數字。
WALCL_MILLIONS_PER_BILLION = 1000.0


# 8-2：11 檔 SPDR 類股 ETF。廣度與它的分母共用同一次抓取。
SECTOR_ETFS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
               "XLP", "XLRE", "XLU", "XLV", "XLY")
BREADTH_PERIOD = "2y"      # 200MA 加上 30 天的歷史
BREADTH_DAYS = 30
_SECTOR_CACHE: dict[dt.date, dict[str, list[tuple[str, float]]]] = {}


def sector_closes(today: dt.date) -> dict[str, list[tuple[str, float]]]:
    """同一天只抓一次（§2.6）。抓失敗的那幾檔直接缺席，由分母反映。"""
    if today in _SECTOR_CACHE:
        return _SECTOR_CACHE[today]
    closes: dict[str, list[tuple[str, float]]] = {}
    for symbol in SECTOR_ETFS:
        try:
            bars = yfinance_src.fetch_daily(symbol, period=BREADTH_PERIOD)
        except Exception:  # noqa: BLE001 — 缺一檔就少一檔分母，不擋整項
            continue
        rows = [(b.date.isoformat(), b.close) for b in bars if b.close is not None]
        if rows:
            closes[symbol] = rows
    if not closes:
        raise FetchError("11 檔類股 ETF 一檔都沒抓到")
    _SECTOR_CACHE[today] = closes
    return closes


def curve_spread_series(near: list[tuple[str, float]],
                        far: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """遠月相對近月的價差百分比，只取兩邊都有的交易日。"""
    deferred = dict(far)
    out: list[tuple[str, float]] = []
    for label, front in sorted(near):
        back = deferred.get(label)
        if front in (None, 0) or back is None:
            continue
        out.append((label, (back / front - 1.0) * 100.0))
    return out


def ratio_series(numerator: list[tuple[str, float]],
                 denominator: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """兩條日頻序列相除，只留兩邊都有的交易日。

    ⚠️ 分母缺料或為 0 的那一天**整天不算** —— 不補舊值、不回 0。少一天看得出來，
    一個用昨天油價湊出來的金油比看不出來。
    """
    bottom = dict(denominator)
    out: list[tuple[str, float]] = []
    for label, top in sorted(numerator):
        low = bottom.get(label)
        if top is None or low in (None, 0):
            continue
        out.append((label, top / low))
    return out


def policy_path_series(quotes: list[tuple[str, float]],
                       target: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """隱含利率（`100 − 報價`）減現行上限，單位是百分點。

    `DFEDTARU` 是階梯狀的政策值，不是日資料 —— 所以每個期貨交易日配的是
    「那天或那天之前最後一次公布的上限」。**上限還沒出現過的日子直接丟掉**，
    不往後借一個未來才存在的數字（§7.2 的同一條原則）。
    """
    steps = sorted(target)
    out: list[tuple[str, float]] = []
    for label, quote in sorted(quotes):
        standing = [value for day, value in steps if day <= label]
        if not standing or quote is None:
            continue
        out.append((label, (100.0 - quote) - standing[-1]))
    return out


def vix_term_series(vix: list[tuple[str, float]],
                    vix3m: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """近月 ÷ 三個月，只取兩邊都有的那些交易日。

    對不上的日子直接不算 —— 拿前一天的三個月去配今天的近月，等於自己造一個
    沒有發生過的期限結構。分母 0 也一樣丟掉，不做除法。
    """
    three_month = dict(vix3m)
    out: list[tuple[str, float]] = []
    for label, near in sorted(vix):
        far = three_month.get(label)
        if far is None or far == 0 or near is None:
            continue
        out.append((label, near / far))
    return out


def net_liquidity_series(walcl: list[tuple[str, float]],
                         rrp: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """`WALCL − RRPONTSYD`，兩邊都換算成十億美元。

    WALCL 是每週三一筆、RRP 是每個營業日一筆，所以對齊方式是「取該日或該日之前
    最近的一筆 RRP」。**前面沒有任何一筆 RRP 的那幾列直接丟掉，不往後借、不補 0**
    —— 補 0 會讓淨流動性憑空多出一塊。
    """
    rrp_sorted = sorted(rrp)
    out: list[tuple[str, float]] = []
    for label, millions in walcl:
        earlier = [value for day, value in rrp_sorted if day <= label]
        if not earlier:
            continue
        out.append((label, round(millions / WALCL_MILLIONS_PER_BILLION - earlier[-1], 6)))
    return out


def _fetch_one(ind) -> list[tuple[str, float]]:
    """依 source 分派。回 (日期, 值) 由舊到新。"""
    if ind.source == "yfinance":
        bars = yfinance_src.fetch_daily(ind.sid, period=YF_PERIOD)
        out = [
            (b.date.isoformat(), b.close) for b in bars if b.close is not None
        ]
        if not out:
            raise FetchError(f"{ind.sid}: 沒有任何有效收盤")
        return out
    if ind.source == "fred":
        return fred_src.fetch(ind.sid)
    if ind.source == "yfinance_breadth":
        ratio, cover = breadth.breadth_series(
            sector_closes(dt.date.today()), days=BREADTH_DAYS)
        series = ratio if ind.sid.endswith("_BREADTH") else cover
        if not series:
            raise FetchError(f"{ind.sid}: 沒有任何一天湊得出 200 根收盤")
        return series
    if ind.source == "cftc":
        return cftc_src.fetch_net_positions(cftc_src.MARKETS[ind.sid])
    if ind.source == "curve_derived":
        near = yfinance_src.fetch_daily("CL=F", period=YF_PERIOD)
        far = yfinance_src.fetch_daily(
            futures.deferred_crude_symbol(dt.date.today()), period=YF_PERIOD)
        series = curve_spread_series(
            [(b.date.isoformat(), b.close) for b in near if b.close is not None],
            [(b.date.isoformat(), b.close) for b in far if b.close is not None])
        if not series:
            raise FetchError(f"{ind.sid}: 近月與遠月沒有任何共同交易日")
        return series
    if ind.source == "ratio_derived":
        left, right = ind.sid.split("-", 1)
        def closes(symbol: str) -> list[tuple[str, float]]:
            bars = yfinance_src.fetch_daily(f"{symbol}=F", period=YF_PERIOD)
            return [(b.date.isoformat(), b.close) for b in bars if b.close is not None]
        series = ratio_series(closes(left), closes(right))
        if not series:
            raise FetchError(f"{ind.sid}: 分子分母沒有任何共同交易日")
        return series
    if ind.source == "policy_derived":
        left, right = ind.sid.split("-", 1)
        bars = yfinance_src.fetch_daily(f"{left}=F", period=YF_PERIOD)
        quotes = [(b.date.isoformat(), b.close) for b in bars if b.close is not None]
        series = policy_path_series(quotes, fred_src.fetch(right))
        if not series:
            raise FetchError(f"{ind.sid}: 沒有任何一天同時有期貨報價與已公布的上限")
        return series
    if ind.source == "cboe_derived":
        bars = yfinance_src.fetch_daily("^VIX", period=YF_PERIOD)
        vix = [(b.date.isoformat(), b.close) for b in bars if b.close is not None]
        series = vix_term_series(vix, cboe_src.fetch_vix3m())
        if not series:
            raise FetchError("VIX 與 VIX3M 沒有任何共同交易日")
        return series
    if ind.source == "fred_derived":
        left, right = ind.sid.split("-", 1)
        return net_liquidity_series(fred_src.fetch(left), fred_src.fetch(right))
    if ind.source == "ndc":
        if ind.key == "tw_light":
            return tw_gov_src.fetch_tw_light()
        return tw_gov_src.fetch_tw_export()
    if ind.source == "dgbas":
        return tw_gov_src.fetch_tw_gdp()
    if ind.source == "cbc":
        return tw_gov_src.fetch_cbc_rate()
    if ind.source == "eia":
        # WPSR 是一張比較表不是序列，只給上週與本週兩個真實的點，
        # 中間不補（見 datasources/eia_src 的說明）
        return eia_src.fetch().as_series()
    raise FetchError(f"未知的資料源 {ind.source}")


def _data_date(series: list[tuple[str, float]]) -> dt.date | None:
    """把序列最後一格的標籤轉成日期。

    刻意容忍三種格式，因為頻率就是混雜的：日頻 2026-09-04、月頻 2026-07、
    季頻 2026Q2。轉不出來就回 None —— 顯示層照原字串標，不要瞎猜一個日期。
    """
    if not series:
        return None
    label = series[-1][0]
    try:
        return dt.date.fromisoformat(label)
    except ValueError:
        pass
    try:
        y, m = label.split("-")
        return dt.date(int(y), int(m), 1)
    except (ValueError, IndexError):
        pass
    if "Q" in label:
        try:
            y, q = label.split("Q")
            return dt.date(int(y), (int(q) - 1) * 3 + 1, 1)
        except (ValueError, IndexError):
            pass
    return None


def run(force: bool = False) -> tuple[RunLog, dict]:
    log = RunLog(task="macro")
    COUNTER.reset()
    config.ensure_dirs()
    repo = SqliteRepo(config.db_path())
    repo.init_schema()

    now = dt.datetime.now()
    results: dict[str, dict] = {}

    try:
        for ind in ALL:
            cached: MacroSeries | None = repo.get_macro(ind.key)
            cached_state = (
                freshness.assess_source_series(
                    ind.freq, cached.data_date, now.date(),
                    [value for _, value in cached.series], key=ind.key,
                ) if cached is not None else None
            )
            if not force and cached is not None:
                age_h = (now - cached.fetched_at).total_seconds() / 3600
                if age_h < ind.ttl_hours and cached_state is not None and cached_state.usable:
                    results[ind.key] = {
                        "series": cached.series,
                        "data_date": cached.data_date,
                        "source": cached.source,
                        "fetched_at": cached.fetched_at,
                        "status": "cached",
                        "note": f"快取（{age_h:.1f} 小時前）",
                    }
                    log.count("from_cache")
                    continue

            try:
                series = _fetch_one(ind)
                dd = _data_date(series)
                source_state = freshness.assess_source_series(
                    ind.freq, dd, now.date(), [value for _, value in series], key=ind.key,
                )
                if not source_state.usable:
                    raise FetchError(source_state.reason)
                repo.put_macro(ind.key, series, fetched_at=now, data_date=dd,
                               source=ind.source)
                results[ind.key] = {
                    "series": series, "data_date": dd,
                    "source": ind.source, "fetched_at": now,
                    "status": "fresh", "note": "",
                }
                log.count("fetched")
            except Exception as exc:  # noqa: BLE001 — 單一指標失敗不擋整輪
                # FetchError 自己就寫了一句人看得懂的中文，直接用。
                # 其他例外要帶上型別 —— 一個 KeyError 的 str() 只有 'series'
                # 四個字，寫進 run log 之後完全查不出發生了什麼事。
                # 這是失敗演練跑出來才看見的（Day 28 第 4 項）。
                reason = (str(exc) if isinstance(exc, FetchError)
                          else f"{type(exc).__name__}: {exc}")
                log.count("failed")
                log.note(f"{ind.key}（{ind.name}）: {reason}")
                if cached is not None and cached_state is not None and cached_state.usable:
                    results[ind.key] = {
                        "series": cached.series,
                        "data_date": cached.data_date,
                        "source": cached.source,
                        "fetched_at": cached.fetched_at,
                        "status": "stale",
                        "note": f"更新失敗，降級到較新快取（{reason}）",
                    }
                else:
                    if cached_state is not None and not cached_state.usable:
                        reason = f"{reason}；快取也不可用（{cached_state.reason}）"
                    results[ind.key] = {
                        "series": [], "data_date": None,
                        "source": None, "fetched_at": None,
                        "status": "missing", "note": f"缺料：{reason}",
                    }

        # ---- 第一層：逐項警示判定 ----
        verdicts: dict[str, tuple[bool, str]] = {}
        for ind in SCORED:
            series = results[ind.key]["series"]
            if not series:
                continue  # 沒有值的指標不計入該層（權重自動正規化）
            verdict = ALERT_FUNCS[ind.key](series)
            if verdict[1] == INSUFFICIENT:
                continue
            verdicts[ind.key] = verdict

        # ---- 第二層：層別評分 ----
        world = score_layer(
            {i.key: verdicts[i.key][0] for i in WORLD if i.key in verdicts}
        )
        taiwan = score_layer(
            {i.key: verdicts[i.key][0] for i in TAIWAN if i.key in verdicts}
        )
        summary = summarize(world, taiwan)
        summary["world_coverage"] = Coverage(world.valid, len(WORLD))
        summary["taiwan_coverage"] = Coverage(taiwan.valid, len(TAIWAN))

        for scope, layer in (("macro_world", world), ("macro_tw", taiwan)):
            if layer.score is not None:
                repo.put_score(
                    scope=scope, symbol="-", as_of=now.date(),
                    score=layer.score,
                    subscores={k: float(verdicts[k][0]) for k in layer.alert_keys},
                    price_version="macro",
                )

        log.quota["requests"] = COUNTER.snapshot()
        log.set_count("scored_indicators", len(verdicts))
        log.finish("partial" if log.counts.get("failed") else "ok")
        repo.record_run(
            run_id=log.run_id, task=log.task, started_at=log.started_at,
            ended_at=log.ended_at, status=log.status,
            counts=log.counts, quota=log.quota,
        )
    finally:
        repo.close()

    log.append()
    return log, {"results": results, "verdicts": verdicts, "summary": summary}


def main() -> int:
    """排程任務 `Barometer-Macro`（每天 09:05）的進入點。

    `force=False` 是刻意的：TTL 由每條序列自己的更新頻率決定（§7.3），
    每小時去問一條每月才出一次的序列，只會把額度花在必定落空的請求上。
    """
    log, _ = run()
    print(f"[{log.started_at:%Y-%m-%d %H:%M}] macro "
          f"status={log.status} counts={log.counts}")
    for n in log.notes:
        print(f"  ! {n}")
    # partial 不算失敗 —— 單一指標失敗不該讓排程任務標成錯誤
    return 0 if log.status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
