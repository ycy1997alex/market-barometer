"""§6 規則 1：節流放在資料源層，不放呼叫端 —— 任何呼叫路徑都繞不過去。

Day 24 第 8 項驗收：「_last_request_ts 在 module level，繞不過去」。
測試不打真的 API，只驗節流器本身的行為（§3.3）。
"""
from __future__ import annotations

import pytest

from barometer.datasources.base import Throttle, RateLimitError


class FakeClock:
    """自己推進的時鐘 —— 測節流不該真的 sleep 掉幾秒。"""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


def test_first_call_does_not_wait(clock):
    t = Throttle(min_interval=1.0, clock=clock)
    t.wait()
    assert clock.now == 0.0, "第一次呼叫不該等"


def test_second_call_waits_the_full_interval(clock):
    t = Throttle(min_interval=1.0, clock=clock)
    t.wait()
    t.wait()
    assert clock.now == pytest.approx(1.0)


def test_no_wait_when_enough_time_already_passed(clock):
    t = Throttle(min_interval=1.0, clock=clock)
    t.wait()
    clock.now += 5.0
    t.wait()
    assert clock.now == pytest.approx(5.0), "已經過了 5 秒就不必再等"


def test_interval_is_honoured_across_many_calls(clock):
    t = Throttle(min_interval=0.6, clock=clock)  # TWSE 的 >= 0.6 秒
    for _ in range(5):
        t.wait()
    assert clock.now == pytest.approx(0.6 * 4)


def test_throttle_state_is_shared_per_instance_not_per_call(clock):
    """節流器是有狀態的物件；同一個實例才擋得住連發。"""
    t = Throttle(min_interval=1.0, clock=clock)
    t.wait()
    t.wait()
    assert t.last_ts == pytest.approx(1.0)


class TestRetryPolicy:
    def test_retries_once_then_gives_up(self, clock):
        """§6 規則 3：重試上限 1 次、固定退避。排程每天跑，今天失敗明天會再試。"""
        from barometer.datasources.base import retry_once

        calls = []

        def always_fails():
            calls.append(1)
            raise RateLimitError("429")

        with pytest.raises(RateLimitError):
            retry_once(always_fails, backoff=3.0, clock=clock)

        assert len(calls) == 2, "只重試一次 —— 共 2 次呼叫"
        assert clock.now == pytest.approx(3.0), "固定退避 3 秒"

    def test_succeeds_on_retry(self, clock):
        from barometer.datasources.base import retry_once

        calls = []

        def fails_once():
            calls.append(1)
            if len(calls) == 1:
                raise RateLimitError("429")
            return "ok"

        assert retry_once(fails_once, backoff=3.0, clock=clock) == "ok"
        assert len(calls) == 2

    def test_no_backoff_when_first_try_succeeds(self, clock):
        from barometer.datasources.base import retry_once

        assert retry_once(lambda: "ok", backoff=3.0, clock=clock) == "ok"
        assert clock.now == 0.0
