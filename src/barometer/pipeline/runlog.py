"""執行紀錄（ToDo §9 Day 24 第 9 項）。

每次跑完 append 一筆到 runlog\\<YYYY-MM>.jsonl，欄位含
run_id / task / status / counts / quota。

為什麼 quota 是必要欄位而不是好心提供：**Shioaji 超流量的後果不是報錯，
是行情查詢直接回空值** —— 程式會以為「那天沒資料」。不記 remaining_bytes
就不知道離上限多遠（§6）。

run log 也是 Day 28 回顧的主體之一 —— 價格可以事後回補，管線自己的執行紀錄
補不回來。
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from barometer import config


@dataclass
class RunLog:
    task: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: dt.datetime = field(default_factory=dt.datetime.now)
    ended_at: dt.datetime | None = None
    status: str = "running"
    counts: dict = field(default_factory=dict)
    quota: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def count(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def set_count(self, key: str, value) -> None:
        self.counts[key] = value

    def finish(self, status: str = "ok") -> "RunLog":
        self.ended_at = dt.datetime.now()
        self.status = status
        return self

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "ended_at": self.ended_at.isoformat(timespec="seconds")
            if self.ended_at
            else None,
            "status": self.status,
            "counts": self.counts,
            "quota": self.quota,
            "notes": self.notes,
        }

    def append(self) -> Path:
        """寫進 runlog\\<YYYY-MM>.jsonl。一行一筆，append-only。"""
        if self.ended_at is None:
            self.finish()
        path = config.runlog_path(self.started_at.strftime("%Y-%m"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
        return path


def read_runs(year_month: str) -> list[dict]:
    path = config.runlog_path(year_month)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
