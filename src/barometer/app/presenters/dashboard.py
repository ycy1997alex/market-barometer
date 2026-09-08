"""桌面儀表板的 Presenter（ToDo §9 Day 27 第 1 項）。

**這一層不認得 SQLite，也不認得 yfinance。** 它拿到的是
`domain/ports.py` 的 MacroRepository，以及一個可呼叫的 refresher ——
兩個都由 `app/main.py`（組裝根）注入。tests/test_layer_boundary.py 會用 AST
掃描確認這件事，不靠自律（§3.2）。

好處在測試那邊看得最清楚：整組 Presenter 測試離線、幾毫秒跑完，一次網路都
不用打。這正是 §3.2 說的「傳一個 InMemory 進去就能測完整流程」。

---

**三種動作，行為必須明確不同**（Day 27 第 1 項的驗收）：

    load()           切分頁、開視窗   → **只讀快取，一次網路都不打**
    auto_refresh()   到期才抓         → 只有真的有序列到期才打網路
    force_refresh()  按「強制重抓」   → 一定打網路，而且忽略快取

為什麼要把這件事釘死：從畫面上看不出差別，三個動作都只是「畫面刷新了」，
使用者分不出哪一次偷偷打了網路。既有專案就是這樣一路多打的，額度也是這樣
用完的（§6）。

**「到期」是按各序列自己的公布頻率算的**（domain/freshness.py），不是按一個
固定的時間間隔。CPI 每月出一次，每小時去問它二十四次不會讓它早一點出現，
只會把額度花在必定落空的請求上。而央行重貼現率沒有預期時間，就用一個慢節奏
去掃 —— 不能永遠不抓，不然真的調息了也不會知道。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Callable, Protocol

from barometer.domain import freshness, macro_spec, weighting
from barometer.domain.ports import MacroRepository, ScoreHistoryRepository


class Refresher(Protocol):
    """打網路的那件事。Presenter 只知道「可以呼叫它」，不知道它怎麼做。

    `force=True` 代表忽略快取重新掃一次；`False` 代表讓資料源自己的 TTL
    決定要不要真的出去。
    """

    def __call__(self, force: bool = False) -> None: ...


@dataclass(frozen=True, slots=True)
class ViewRow:
    key: str
    label: str
    value: str | None
    data_date: str | None
    freq: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class RefreshResult:
    ok: bool
    message: str


TABS: dict[str, tuple] = {
    "world": macro_spec.WORLD + macro_spec.OBSERVE,
    "tw": macro_spec.TAIWAN,
}

# 大盤與 ETF 分頁。標的清單刻意寫在這裡而不是 import config ——
# config 是外層的東西，Presenter 只該認 domain 與 Port（§3.2）。
INDEX_TABS: dict[str, tuple[str, ...]] = {
    "tw_index": ("^TWII", "0050.TW", "006208.TW"),
    "us_index": ("^GSPC", "SPY", "VOO"),
}
INDEX_SCOPE = "index"
WINDOW = 5  # 五日視窗（§8.1）

# 分項的中文名。分數本身不解釋方向，只說「哪一維落在不尋常的地方」。
DIMENSION_NAMES = {
    "ma_stack": "均線排列", "rsi": "RSI", "bollinger": "布林通道",
    "volatility": "波動度", "drawdown": "距高點回撤",
}


class DashboardPresenter:
    def __init__(
        self,
        repo: MacroRepository,
        refresher: Callable[..., None] | None = None,
        today: dt.date | None = None,
        scores: ScoreHistoryRepository | None = None,
    ) -> None:
        self._repo = repo
        self._refresh = refresher
        # 評分歷史。不給就用同一個 repo —— SqliteRepo 與 InMemoryRepo
        # 都同時實作了這幾個 Port，分開傳只是為了測試時能各餵各的。
        self._scores = scores if scores is not None else (
            repo if hasattr(repo, "get_scores") else None
        )
        # today 可注入，測試才不必等到明天才驗得了「到期」
        self._today = today

    # ---------------- 只讀快取，不打網路 ----------------

    def load(self, tab: str = "world") -> list[ViewRow]:
        if tab in INDEX_TABS:
            return self._load_index(tab)
        rows: list[ViewRow] = []
        for ind in TABS.get(tab, ()):
            cached = self._repo.get_macro(ind.key)
            if cached is None or not cached.series:
                rows.append(
                    ViewRow(ind.key, ind.name, None, None, ind.freq,
                            note="尚未抓取")
                )
                continue
            last = cached.series[-1][1]
            note = ind.note
            if cached.stale_reason:
                note = (f"{note}｜更新失敗，顯示快取（{cached.stale_reason}）"
                        ).lstrip("｜")
            rows.append(
                ViewRow(
                    key=ind.key,
                    label=ind.name,
                    value=ind.fmt.format(last) if last is not None else None,
                    data_date=(cached.data_date.isoformat()
                               if cached.data_date else cached.series[-1][0]),
                    freq=ind.freq,
                    note=note,
                )
            )
        return rows

    def _load_index(self, tab: str) -> list[ViewRow]:
        """大盤與 ETF 的評分。**只讀 score_history，不重算、不打網路。**

        分數是 pipeline/run_scores.py 算好寫進去的。這裡重算一次的話，
        畫面上的數字跟網頁上的就可能對不起來 —— 同一個問題兩個答案，
        比沒有答案更難查。
        """
        rows: list[ViewRow] = []
        for symbol in INDEX_TABS[tab]:
            history = (self._scores.get_scores(INDEX_SCOPE, symbol)
                       if self._scores is not None else [])
            if not history:
                rows.append(
                    ViewRow(symbol, symbol, None, None, "每日",
                            note="尚未評分（先跑 tools/score_index.py）")
                )
                continue

            latest = history[-1]
            alerts = [DIMENSION_NAMES.get(k, k)
                      for k, v in latest.subscores.items() if v == 0.0]
            # 不滿五天就不算。`weighted_average` 的契約是「長度必須恰好是 5」，
            # 少一天它會丟 ValueError —— 而「管線剛開始跑」與「標的剛加進清單」
            # 都會產生不滿五天的歷史，那是常態不是異常。不擋的話整個分頁會炸，
            # 而且是在使用者切到大盤分頁的那一刻才炸。
            recent = [r.score for r in history[-WINDOW:]]
            wavg = (weighting.weighted_average(recent)
                    if len(recent) == WINDOW else None)

            note = (f"五日加權 {wavg:.1f}" if wavg is not None
                    else f"五日加權：資料不足（{len(recent)}/{WINDOW} 天）")
            note += "｜警示：" + ("、".join(alerts) if alerts else "無")
            note += f"｜{len(latest.subscores)} 個維度"

            rows.append(
                ViewRow(
                    key=symbol,
                    label=symbol,
                    value=f"{latest.score:.1f}",
                    data_date=latest.as_of.isoformat(),
                    freq="每日",
                    note=note,
                )
            )
        return rows

    def status(self) -> str:
        """狀態列。

        **刻意不是一行「最後更新：…」** —— 那 21 條序列有 8 種資料日期，
        印一個時間戳等於宣稱它們都是那天的（§9 Day 25 第 3 項）。
        所以這裡列的是「有幾條序列、資料日期各自落在哪些天」。
        """
        dates: set[str] = set()
        n = 0
        for indicators in TABS.values():
            for ind in indicators:
                cached = self._repo.get_macro(ind.key)
                if cached and cached.data_date:
                    dates.add(cached.data_date.isoformat())
                    n += 1
        if not dates:
            return "尚無快取 —— 按「更新」抓一次"
        return (f"{n} 條序列，資料日期 {len(dates)} 種："
                + "、".join(sorted(dates)))

    # ---------------- 到期判定 ----------------

    def _now(self) -> dt.date:
        return self._today or dt.date.today()

    def due_keys(self) -> list[str]:
        """現在該去抓的那幾條（按各自的公布頻率算）。"""
        rows = [
            (ind.key, ind.freq,
             cached.data_date if (cached := self._repo.get_macro(ind.key)) else None)
            for ind in macro_spec.ALL
        ]
        return freshness.due_keys(rows, today=self._now())

    def due_summary(self) -> str:
        due = self.due_keys()
        if not due:
            return "沒有序列到期，下次自動更新會跳過"
        names = [macro_spec.BY_KEY[k].name for k in due if k in macro_spec.BY_KEY]
        head = "、".join(names[:4])
        more = f" 等 {len(due)} 條" if len(due) > 4 else ""
        return f"{len(due)} 條到期：{head}{more}"

    # ---------------- 兩種更新：這裡才打網路 ----------------

    def _call(self, force: bool) -> RefreshResult:
        if self._refresh is None:
            return RefreshResult(False, "唯讀模式：沒有注入 refresher，不打網路")
        try:
            self._refresh(force=force)
        except Exception as exc:  # noqa: BLE001
            # 失敗不得清空畫面 —— 舊值留著並標明失敗（§7.3 最後一段）
            return RefreshResult(False, f"更新失敗，畫面維持快取：{exc}")
        return RefreshResult(True, "已重新掃描全部序列" if force else "已更新到期的序列")

    def auto_refresh(self) -> RefreshResult:
        """**到期才抓。** 沒有任何序列到期就一次網路都不打。"""
        due = self.due_keys()
        if not due:
            return RefreshResult(False, "沒有序列到期，這次不打網路")
        return self._call(force=False)

    def force_refresh(self) -> RefreshResult:
        """**一定抓。** 忽略快取，真的重新去掃一次有沒有更新。"""
        return self._call(force=True)

    # 舊名稱保留成強制重抓的別名，免得其他呼叫端悄悄變成「有時候不抓」
    def refresh(self) -> RefreshResult:
        return self.force_refresh()
