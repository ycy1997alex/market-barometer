"""建立 `STOCKDATA_ROOT\secrets\publish.json`（ToDo §5.1）。

**憑證從命令列或既有檔案來，不寫死在這支腳本裡。** 兩個 repo 都是 public，
密碼一旦進版控就撤不回來（§12 第 1 條）—— 所以這支腳本自己也不能認得任何
一組密碼。

用法（互動輸入，不會留在 shell history）：

    python tools/setup_publish_secrets.py

已經有檔案時預設不覆寫；要重建加 --force。**重建會產生新的槽位代號**，
§5.6 的遙測對照表會跟舊資料對不起來，所以預設會沿用既有的 `t`。
"""
from __future__ import annotations

import getpass
import json
import secrets
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE / "src"))

from barometer import config  # noqa: E402
from barometer.crypto import credentials  # noqa: E402


def _ask_many(prompt: str) -> list[str]:
    print(f"\n{prompt}（一行一組，空行結束；輸入不會顯示）")
    out = []
    while True:
        v = getpass.getpass(f"  [{len(out) + 1}] ")
        if not v:
            return out
        out.append(v)


def _slot(existing: dict, label: str) -> str:
    """沿用既有的槽位代號，沒有才新產生 —— t 必須跨發布穩定（§5.6 第 2 點）。"""
    return existing.get(label) or secrets.token_hex(2)


def main(argv: list[str]) -> int:
    force = "--force" in argv
    path = credentials.publish_path()
    config.ensure_dirs()

    old_slots: dict[str, str] = {}
    if path.exists():
        if not force:
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"{path} 已存在：")
            for site, block in data.items():
                print(f"  {site}（{block['mode']} 層鎖）"
                      f"{len(block['credentials'])} 組憑證")
            print("\n要重建請加 --force（會沿用既有的槽位代號）")
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        for site, block in data.items():
            for c in block["credentials"]:
                old_slots[f"{site}:{c.get('label', '')}"] = c["t"]

    print("=== market-barometer（一層鎖：Password ×N）===")
    passwords = _ask_many("Password")
    mb = [
        {"t": _slot(old_slots, f"market-barometer:mb{i}"),
         "label": f"mb{i}", "password": p}
        for i, p in enumerate(passwords, 1)
    ]

    print("\n=== stock-research（兩層鎖：Key ×N 配 Password ×M）===")
    keys = _ask_many("Key")
    pws = _ask_many("Password")
    sr = [
        {"t": _slot(old_slots, f"stock-research:k{i}p{j}"),
         "label": f"k{i}p{j}", "key": k, "password": p}
        for i, k in enumerate(keys, 1)
        for j, p in enumerate(pws, 1)
    ]

    if not mb or not sr:
        print("\n沒有輸入任何憑證，中止 —— 不寫出一份空的 publish.json")
        return 1

    path.write_text(
        json.dumps(
            {
                "market-barometer": {"mode": "one", "credentials": mb},
                "stock-research": {"mode": "two", "credentials": sr},
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n寫出 {path}")
    print(f"  market-barometer：{len(mb)} 組（一層鎖）")
    print(f"  stock-research  ：{len(sr)} 組（兩層鎖，{len(keys)} × {len(pws)}）")
    print("\n這個檔案在兩個 repo 之外，且 .gitignore 也擋著 —— 不要複製進任何 repo。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
