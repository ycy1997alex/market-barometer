"""資料源共用基底：節流與重試（ToDo §6）。

**額度是會被用完的東西。** 節流放在這一層，不放呼叫端 —— 每個 client 自己持有
module-level 的節流器實例，任何呼叫路徑都繞不過去。呼叫端不必記得要 sleep，
也不該有辦法跳過。

禁止併發抓同一個來源：threads=True、asyncio.gather 一律不用（§6 規則 2）。
"""
from __future__ import annotations

import time
from typing import Callable, Protocol, TypeVar

T = TypeVar("T")


class RateLimitError(RuntimeError):
    """429 / 403 —— 視為「這條序列今天 stale」，不是 crash（§6 規則 4）。"""


class FetchError(RuntimeError):
    """單一序列抓取失敗。任何單一標的的失敗都不得中止整批（§4.3）。"""


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class _RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


REAL_CLOCK = _RealClock()


class Throttle:
    """固定間隔節流器。

    clock 可注入，測試才不必真的 sleep 掉幾秒 —— 但正式路徑走的是真時鐘。
    """

    def __init__(self, min_interval: float, clock: Clock | None = None):
        if min_interval < 0:
            raise ValueError("min_interval 不得為負")
        self.min_interval = min_interval
        self._clock = clock or REAL_CLOCK
        self.last_ts: float | None = None

    def wait(self) -> None:
        now = self._clock.monotonic()
        if self.last_ts is not None:
            remaining = self.min_interval - (now - self.last_ts)
            if remaining > 0:
                self._clock.sleep(remaining)
        self.last_ts = self._clock.monotonic()


def retry_once(
    fn: Callable[[], T],
    backoff: float = 3.0,
    clock: Clock | None = None,
) -> T:
    """重試上限 1 次、固定退避（§6 規則 3）。

    刻意不做指數退避、不做多次重試：排程每天跑，今天失敗明天會再試，
    在這裡纏鬥只會多消耗別人的額度。
    """
    c = clock or REAL_CLOCK
    try:
        return fn()
    except (RateLimitError, FetchError):
        c.sleep(backoff)
        return fn()


class RequestCounter:
    """每個來源當天打了幾次網路 —— 進 run log（§6 規則 6）。"""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def bump(self, source: str, n: int = 1) -> None:
        self._counts[source] = self._counts.get(source, 0) + n

    def snapshot(self) -> dict[str, int]:
        return dict(self._counts)

    def reset(self) -> None:
        self._counts.clear()


# 全域計數器：pipeline 跑完把 snapshot 寫進 run log
COUNTER = RequestCounter()
