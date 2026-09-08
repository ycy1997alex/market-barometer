"""發布閘門：資料沒變就不動 docs/（ToDo §1 第 6 條、§9 Day 28 第 3 項）。

**閘門看的是明文的指紋，不是密文。**

因為 §5.4 第 1 條要求每次發布重新產生 salt / IV / CEK，密文**每次都不一樣**
是刻意的、也是不能讓步的（IV 重用是 AES-GCM 的致命傷）。拿 `docs/index.html`
去比「有沒有變」永遠會說「變了」，於是每天都會多一筆內容相同、只有隨機數
不同的 commit —— 兩條硬規定就在這裡對撞。

把判斷移到封裝之前，兩條就都成立了：明文一樣就整個跳過，該換的隨機數在
真的要發的時候還是每次都換。

順帶解掉的是交易日曆：不必知道今天是不是颱風假、是不是美國勞動節，
資料沒變就是沒變（§1 第 6 條）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Decision:
    publish: bool
    reason: str
    fingerprint: str


def fingerprint(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()[:16]


class Gate:
    def __init__(self, state_path: str | Path) -> None:
        self.path = Path(state_path)

    def _last(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("fingerprint")
        except (json.JSONDecodeError, OSError):
            # 狀態檔壞掉 → **發布**。漏發一天畫面會停在昨天而且沒有人知道；
            # 多發一天只是多一筆 commit。兩種錯的代價差很多。
            return None

    def should_publish(self, plaintext: str, force: bool = False) -> Decision:
        fp = fingerprint(plaintext)
        if force:
            return Decision(True, "強制發布（--force）", fp)
        last = self._last()
        if last == fp:
            return Decision(False, f"明文沒有變（指紋 {fp}）—— 不動 docs/", fp)
        if last is None:
            return Decision(True, f"沒有上一次的紀錄，發布（指紋 {fp}）", fp)
        return Decision(True, f"明文變了：{last} → {fp}", fp)

    def record(self, plaintext: str) -> str:
        fp = fingerprint(plaintext)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"fingerprint": fp}, ensure_ascii=False), encoding="utf-8"
        )
        return fp
