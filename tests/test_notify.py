"""失敗通知（ToDo §9 Day 28 第 4 項）。

驗收句：**「故意讓一個資料源失敗，其他格照常更新、失敗那格標 stale 並顯示
停在哪一天，通知有送出」**。

三個設計決定，每一個都有對應的測試：

1. **通知失敗絕不能拖垮管線。** 通知是附屬品；為了送不出一則通知而讓當天的
   資料整批沒抓到，是本末倒置。這跟 §5.6 遙測那條「掛掉不得影響解鎖」同一個
   道理，而且這裡更嚴重 —— 遙測掛了只是少一筆統計。
2. **「停在哪一天」要寫進通知本文。** 只說「vix 失敗」沒有用；要說它停在
   2026-08-20，才知道是今天剛壞還是壞了三週沒人發現。
3. **外部通知管道用環境變數注入，不寫進 repo。** 任何 API Key 只放在本機
   （§9 Day 28 第 3 項的文章重點），所以這一層只認一個「要跑什麼命令」，
   命令本身跟它的金鑰都在本機。
"""
from __future__ import annotations

import datetime as dt
import json

from barometer.pipeline import notify


def test_alert_is_appended_as_one_line_per_event(tmp_path):
    n = notify.Notifier(tmp_path / "alerts.jsonl", tmp_path / "ALERT.md")
    n.send("vix 抓取失敗", "停在 2026-08-20", severity="error")
    n.send("cpi 抓取失敗", "停在 2026-07-01", severity="error")

    lines = (tmp_path / "alerts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["title"] == "vix 抓取失敗"


def test_alert_body_says_where_the_series_stopped(tmp_path):
    n = notify.Notifier(tmp_path / "alerts.jsonl", tmp_path / "ALERT.md")
    n.send("vix 抓取失敗", "停在 2026-08-20", severity="error")
    assert "2026-08-20" in (tmp_path / "ALERT.md").read_text(encoding="utf-8")


def test_marker_file_is_obvious_and_holds_the_latest(tmp_path):
    """排程是無人值守的 —— 要有一個一眼看得到的東西，不能只躺在 jsonl 裡。"""
    n = notify.Notifier(tmp_path / "alerts.jsonl", tmp_path / "ALERT.md")
    n.send("第一則", "aaa", severity="error")
    n.send("第二則", "bbb", severity="error")
    text = (tmp_path / "ALERT.md").read_text(encoding="utf-8")
    assert "第二則" in text


def test_clear_removes_the_marker_but_keeps_the_history(tmp_path):
    n = notify.Notifier(tmp_path / "alerts.jsonl", tmp_path / "ALERT.md")
    n.send("壞了", "x", severity="error")
    n.clear()
    assert not (tmp_path / "ALERT.md").exists()
    assert (tmp_path / "alerts.jsonl").exists()


def test_external_command_failure_never_breaks_the_pipeline(tmp_path):
    """通知管道掛掉不得影響管線 —— 這是硬規定。"""
    n = notify.Notifier(tmp_path / "alerts.jsonl", tmp_path / "ALERT.md",
                        external_cmd="this-command-does-not-exist-12345")
    result = n.send("壞了", "x", severity="error")
    assert result.recorded is True       # 本機那份一定要寫成功
    assert result.external_ok is False   # 外部那份失敗
    assert "this-command-does-not-exist" in (result.external_error or "")


def test_unwritable_path_is_swallowed_not_raised(tmp_path):
    """連本機檔案都寫不了的時候也不准丟例外出去 —— 管線比通知重要。"""
    n = notify.Notifier(tmp_path / "nope" / "x" / "alerts.jsonl",
                        tmp_path / "nope" / "x" / "ALERT.md")
    # 目錄不存在時 Notifier 會自己建；改成指向一個已存在的檔案當目錄
    bad = tmp_path / "afile"
    bad.write_text("x", encoding="utf-8")
    n2 = notify.Notifier(bad / "alerts.jsonl", bad / "ALERT.md")
    result = n2.send("壞了", "x", severity="error")
    assert result.recorded is False   # 誠實回報寫不進去
    # 沒有丟例外出來 —— 這就是這個測試要證明的


def test_summarise_failures_builds_one_message_not_twenty(tmp_path):
    """一次跑壞五條序列應該是一則通知，不是五則 —— 不然通知本身變成雜訊。"""
    msg = notify.summarise_failures([
        ("vix", "HTTP 429", dt.date(2026, 8, 20)),
        ("cpi", "連線逾時", dt.date(2026, 7, 1)),
    ])
    assert msg.count("\n") >= 1
    assert "vix" in msg and "cpi" in msg
    assert "2026-08-20" in msg and "2026-07-01" in msg


def test_summarise_empty_is_empty():
    assert notify.summarise_failures([]) == ""
