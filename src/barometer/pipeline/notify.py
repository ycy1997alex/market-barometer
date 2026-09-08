"""失敗通知（ToDo §9 Day 28 第 4 項）。

**通知是附屬品，管線是主體。** 這一層的每一個錯誤路徑都吞掉例外 ——
為了送不出一則通知而讓當天的資料整批沒抓到，是本末倒置。
（同 §5.6 遙測那條「掛掉不得影響解鎖」，而且這裡更嚴重：遙測掛了只是少一筆
統計，管線掛了是那一天的資料就沒了，而且明天不會回頭補。）

兩個落地處：

    alerts.jsonl   一行一則，append-only，是歷史
    ALERT.md       只留最新一則，是**一眼看得到的東西**

為什麼要第二個：排程是無人值守的，18:00 跑完沒有人在看終端機。躺在 jsonl
第 47 行的一則錯誤等於沒有發生過。

**外部管道用環境變數 `BAROMETER_NOTIFY_CMD` 注入**，不寫進 repo ——
任何 API Key 只放在本機（§9 Day 28）。要接 LINE Notify、Telegram、寄信都行，
這一層只負責「跑那個命令，跑壞了也不吭聲」。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

ENV_CMD = "BAROMETER_NOTIFY_CMD"
EXTERNAL_TIMEOUT = 15


@dataclass(frozen=True, slots=True)
class NotifyResult:
    recorded: bool
    external_ok: bool
    external_error: str | None = None


def summarise_failures(
    failures: list[tuple[str, str, dt.date | None]]
) -> str:
    """把一輪的所有失敗收成**一則**訊息。

    一次跑壞五條序列送五則通知，第二天就沒有人會看通知了。

    每一行都要說「停在哪一天」—— 只說「vix 失敗」看不出是今天剛壞，
    還是壞了三週沒人發現。
    """
    if not failures:
        return ""
    lines = []
    for key, reason, last_date in failures:
        stopped = f"停在 {last_date}" if last_date else "沒有任何既有資料"
        lines.append(f"- {key}：{reason}（{stopped}）")
    return f"{len(failures)} 條序列沒有更新：\n" + "\n".join(lines)


class Notifier:
    def __init__(
        self,
        history_path: str | Path,
        marker_path: str | Path,
        external_cmd: str | None = None,
    ) -> None:
        self.history = Path(history_path)
        self.marker = Path(marker_path)
        self.external_cmd = external_cmd or os.environ.get(ENV_CMD) or None

    def send(self, title: str, body: str, severity: str = "error") -> NotifyResult:
        recorded = self._record(title, body, severity)
        ok, err = self._external(title, body)
        return NotifyResult(recorded=recorded, external_ok=ok, external_error=err)

    def clear(self) -> None:
        """問題排除之後把顯眼的那個拿掉。**歷史留著**，不然就沒有紀錄可回顧。"""
        try:
            self.marker.unlink(missing_ok=True)
        except OSError:
            pass

    # ---------------- 內部 ----------------

    def _record(self, title: str, body: str, severity: str) -> bool:
        event = {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "severity": severity,
            "title": title,
            "body": body,
        }
        try:
            self.history.parent.mkdir(parents=True, exist_ok=True)
            with self.history.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.marker.write_text(
                f"# {title}\n\n{body}\n\n（{event['ts']}，severity={severity}）\n"
                f"\n問題排除後刪掉這個檔案，或跑 tools/show_runlog.py 看歷史。\n",
                encoding="utf-8",
            )
            return True
        except OSError:
            # 連本機檔案都寫不了也不准丟出去 —— 管線比通知重要
            return False

    def _external(self, title: str, body: str) -> tuple[bool, str | None]:
        if not self.external_cmd:
            return True, None
        try:
            subprocess.run(
                shlex.split(self.external_cmd) + [title, body],
                capture_output=True, timeout=EXTERNAL_TIMEOUT, check=True,
            )
            return True, None
        except Exception as exc:
            return False, f"{self.external_cmd}：{exc}"
