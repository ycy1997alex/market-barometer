"""把 Shioaji 憑證複製進 STOCKDATA_ROOT/secrets/（ToDo §5.1、§12 紅線第 5 條）。

來源是既有專案 D:\\Research\\Stock_Tracker_Shioaji\\config.json。

**secrets/ 在兩個 repo 之外，且兩個 repo 的 .gitignore 都擋掉 secrets/。**
同一把 Shioaji 金鑰有下單能力 —— 不進 CI、不進 repo、不進 run log。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from barometer import config  # noqa: E402

SOURCE = Path(r"D:\Research\Stock_Tracker_Shioaji\config.json")


def main() -> int:
    if not SOURCE.exists():
        print(f"FAIL 找不到來源 {SOURCE}")
        return 1

    src = json.loads(SOURCE.read_text(encoding="utf-8"))
    api_key = (src.get("shioaji_api_key") or "").strip()
    secret_key = (src.get("shioaji_secret_key") or "").strip()
    if not api_key or not secret_key:
        print("FAIL 來源沒有 shioaji 金鑰")
        return 1

    config.ensure_dirs()
    target = config.secrets_dir() / "shioaji.json"
    target.write_text(
        json.dumps(
            {
                "api_key": api_key,
                "secret_key": secret_key,
                # 沿用來源的模擬模式設定；正式環境有下單能力，預設保守
                "simulation": bool(src.get("use_simulation", True)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"已寫入 {target}")
    print(f"  api_key    = {api_key[:4]}…{api_key[-2:]}（{len(api_key)} 字元）")
    print(f"  secret_key = {secret_key[:4]}…{secret_key[-2:]}（{len(secret_key)} 字元）")
    print(f"  simulation = {src.get('use_simulation', True)}")
    print("\n提醒：這個路徑在兩個 repo 之外，且 .gitignore 已擋 secrets/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
