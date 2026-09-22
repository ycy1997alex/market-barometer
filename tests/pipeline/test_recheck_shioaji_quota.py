"""回補批 R-5：Shioaji 剩餘流量那一格一直是空的。

`tools/crosscheck_tw.py` 每天都有把 `api.usage()` 記進 run log，但記的是巢狀的
`quota.shioaji_usage.remaining_bytes`；報表讀的是平的 `quota.shioaji_remaining_bytes`
—— 那個 key **從來沒有人寫過**。所以不是沒記，是兩邊的 key 對不上。

超流量的後果是行情查詢回空值、不是報錯（§6），這格空著就是不知道離上限多遠。
"""
from tools.quota_report import MB, latest_shioaji_remaining, shioaji_alert


def _run(quota: dict) -> dict:
    return {"task": "crosscheck_tw", "quota": quota}


def test_reads_the_nested_key_that_crosscheck_actually_writes():
    runs = [
        _run({"shioaji_usage": {"bytes": 1, "limit_bytes": 500 * MB,
                                "remaining_bytes": 400 * MB}}),
        _run({"shioaji_usage": {"bytes": 2, "limit_bytes": 500 * MB,
                                "remaining_bytes": 380 * MB}}),
    ]
    assert latest_shioaji_remaining(runs) == 380 * MB


def test_flat_legacy_key_still_counts():
    assert latest_shioaji_remaining([_run({"shioaji_remaining_bytes": 123})]) == 123


def test_usage_that_failed_is_unknown_not_zero():
    runs = [_run({"shioaji_usage": {"error": "api.usage() 失敗：timeout"}}),
            _run({"requests": {"twse": 3}}),
            {"task": "macro"}]
    assert latest_shioaji_remaining(runs) is None


def test_low_remaining_is_flagged_and_healthy_is_not():
    assert shioaji_alert(30 * MB) is not None
    assert shioaji_alert(400 * MB) is None
    assert shioaji_alert(None) is None      # 不知道 ≠ 告警，兩件事分開講
