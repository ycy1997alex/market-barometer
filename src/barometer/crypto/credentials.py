"""發布憑證的載入（ToDo §5.1、§5.6）。

**這支檔案裡沒有任何密碼。** 它只知道去哪裡讀 ——
`STOCKDATA_ROOT\\secrets\\publish.json`，那個路徑在兩個 repo 之外。

為什麼要這麼囉唆：兩個 repo 都是 **public**。密碼清單一旦跟著 `tools/publish.py`
進版控，整套加密就等於沒做，而且 git history 撤不回來（§5.1、§12 第 1 條）。
所以憑證與程式的距離必須是「不同的磁碟位置」，不是「不同的檔案」。

publish.json 的形狀：

```json
{
  "market-barometer": {
    "mode": "one",
    "credentials": [{"t": "a3f9", "label": "iThome 讀者用", "password": "..."}]
  },
  "stock-research": {
    "mode": "two",
    "credentials": [{"t": "b71c", "label": "…", "key": "...", "password": "..."}]
  }
}
```

`t` 是**不透明且跨發布穩定**的槽位代號（§5.6）—— 產生一次就不再變，
`keys[]` 每次發布洗牌，所以位置洩漏不了資訊，而 `t` 認得出是哪一組。
它對應到哪一組憑證只記在這個檔案裡，密文頁面上看不出來。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from barometer import config
from barometer.crypto import envelope

MARKET_BAROMETER = "market-barometer"
STOCK_RESEARCH = "stock-research"


class MissingCredentials(RuntimeError):
    """publish.json 不在 —— 發布必須中止，不能退而求其次發一份沒鎖的。"""


@dataclass(frozen=True, slots=True)
class SiteCredentials:
    site: str
    mode: str                 # "one" = 只有 Password；"two" = Key + Password
    materials: list[bytes]
    slot_ids: list[str]
    labels: dict[str, str]    # t → 人看得懂的標籤（只留在本機）

    def __len__(self) -> int:
        return len(self.materials)


def publish_path() -> Path:
    return config.secrets_dir() / "publish.json"


def load(site: str) -> SiteCredentials:
    path = publish_path()
    if not path.exists():
        raise MissingCredentials(
            f"找不到 {path} —— 憑證不在任何 repo 裡（§5.1），"
            f"請先跑 tools/setup_publish_secrets.py 建立它"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if site not in data:
        raise MissingCredentials(f"{path} 裡沒有 {site} 這一站")

    block = data[site]
    mode = block["mode"]
    materials, slots, labels = [], [], {}

    for c in block["credentials"]:
        if mode == "two":
            materials.append(envelope.material_two_lock(c["key"], c["password"]))
        else:
            materials.append(envelope.material_one_lock(c["password"]))
        slots.append(c["t"])
        labels[c["t"]] = c.get("label", "")

    if len(set(slots)) != len(slots):
        raise MissingCredentials(
            f"{site} 的槽位代號有重複 —— 遙測會對錯人（§5.6 第 2 點）"
        )

    return SiteCredentials(site, mode, materials, slots, labels)


def raw_secret_strings(site: str) -> list[str]:
    """這一站用到的所有密碼字串。

    **只給 tools/verify_publish.py 用**，用途是反過來確認這些字串
    grep 不到於產出的密文裡（§5.5）。除此之外不要呼叫它。
    """
    data = json.loads(publish_path().read_text(encoding="utf-8"))
    out: list[str] = []
    for c in data[site]["credentials"]:
        out.extend(v for k, v in c.items() if k in ("key", "password"))
    return out
