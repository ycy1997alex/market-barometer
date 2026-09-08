"""憑證讀取（ToDo §5.1、§12 紅線第 5 條）。

金鑰全留本機。這是為什麼排程用 Windows 工作排程器而不是 GitHub Actions cron ——
CI 不抓資料就不需要任何 Key（§1 第 3 條）。

**加密方式沿用既有專案 Stock_Tracker_Shioaji 的機器綁定 SecretBox**：
金鑰由 主機名稱:使用者:MAC 衍生，所以密文換一台機器就解不開。
好處是磁碟上永遠沒有明文金鑰；代價是換機器要重新輸入 —— 對單機單使用者
的專案這個取捨划算。

金鑰分級（Day 28 的內容之一）：
  讀取型 —— FRED，免費、唯讀、可撤銷，而且這個專案根本不需要它（走免金鑰端點）
  交易型 —— Shioaji，**有下單能力**，不進 CI、不進 repo、不進 run log
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import uuid as _uuid
from pathlib import Path

from barometer import config

_ENC_PREFIX = "ENC:"


def _machine_key() -> bytes:
    """從主機名稱、使用者、MAC 位址衍生 32 bytes 機器金鑰。"""
    user = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
    material = f"{platform.node()}:{user}:{_uuid.getnode()}"
    return hashlib.sha256(material.encode("utf-8")).digest()


def encrypt(text: str) -> str:
    if not text:
        return text
    import nacl.secret

    box = nacl.secret.SecretBox(_machine_key())
    return _ENC_PREFIX + base64.b64encode(
        box.encrypt(text.encode("utf-8"))
    ).decode("ascii")


def decrypt(text: str) -> str:
    """非加密格式直接回傳；換機器後回傳空字串（觸發重新輸入，不是靜默用錯的值）。"""
    if not text or not text.startswith(_ENC_PREFIX):
        return text
    try:
        import nacl.secret

        box = nacl.secret.SecretBox(_machine_key())
        return box.decrypt(
            base64.b64decode(text[len(_ENC_PREFIX):])
        ).decode("utf-8")
    except Exception:  # noqa: BLE001 — 解不開就是解不開，不要猜
        return ""


def _load(name: str) -> dict:
    path: Path = config.secrets_dir() / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def shioaji_credentials() -> tuple[str, str, bool]:
    """回 (api_key, secret_key, simulation)。缺任一項就回空字串，呼叫端自己跳過。"""
    cfg = _load("shioaji.json")
    return (
        decrypt(cfg.get("api_key", "")),
        decrypt(cfg.get("secret_key", "")),
        bool(cfg.get("simulation", True)),
    )


def has_shioaji() -> bool:
    api_key, secret_key, _ = shioaji_credentials()
    return bool(api_key and secret_key)
