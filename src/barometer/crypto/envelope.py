"""信封加密：多組密碼共用一份密文（ToDo §5.3）。

**為什麼不是每組密碼各加密一份內容**：體積會 ×N，而且同一份明文的多份密文
本身就是線索。信封加密只加密內容一次，再用每組密碼各自包一次那把內容金鑰。

    cek                      內容金鑰，**每次發布重新產生**
    ct  = AESGCM(cek)(明文)   全部憑證共用這一份
    kek_i = PBKDF2(material_i, salt_i)    每組憑證各自導出
    wrapped_i = AESGCM(kek_i)(cek)        用 kek 把 cek 包起來

瀏覽器那側拿到密碼 → 導出 kek → 逐一試著解開 `keys[i].wrapped` → 拿到 cek →
解 ct。AES-GCM 是認證加密，密碼錯就是驗證失敗，**不會吐出半段明文**。

---

**§5.4 第 1 條是這支檔案存在的全部理由：每次發布都要重新產生隨機 salt、IV、
CEK。** AES-GCM 在同一把 key 下重用 IV，機密性與完整性會**同時**崩掉 ——
不是理論弱化，是可以直接還原明文。手動做一次不會踩到，寫成每天跑的腳本很
容易踩到，因為 salt 與 iv 是最容易被順手寫死的東西。

所以這裡**沒有任何常數 salt 或 iv**，一個都沒有，而且 tests/test_envelope.py
會比對連續兩次發布的每一個 salt 與 iv 都不同。

---

**密碼永遠不進這支檔案。** 它只收「材料」（bytes），從哪來是呼叫端的事 ——
真的憑證在 `_stockdata\\secrets\\publish.json`，那個檔案在兩個 repo 之外
（§5.1、§12 第 1 條）。
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

VERSION = 1

# PBKDF2 是 WebCrypto 裡唯一可用的 KDF（沒有 Argon2、沒有 scrypt），
# 所以迭代數就是防線的上限。310,000 是 2026 年的**下限**，不是上限（§5.4 第 5 條）。
ITERATIONS = 310_000
DKLEN = 32

AAD_CONTENT = b"barometer-v1"
AAD_KEK = b"kek-v1"

SALT_BYTES = 16
IV_BYTES = 12
CEK_BYTES = 32


class WrongCredential(ValueError):
    """沒有任何一組 wrapped 解得開 —— 就是密碼錯，沒有別的可能。"""


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


# ---------------- 憑證材料（§5.3 第 4 點） ----------------

def material_one_lock(password: str) -> bytes:
    """market-barometer：一層鎖，材料就是密碼本身。"""
    return password.encode("utf-8")


def material_two_lock(key: str, password: str) -> bytes:
    """stock-research：兩層鎖。

    **NUL 分隔是必要的**，不是裝飾：沒有它，`("ab", "c")` 與 `("a", "bc")`
    會導出同一把 kek，兩層鎖就在這裡破一個洞。
    """
    return key.encode("utf-8") + b"\x00" + password.encode("utf-8")


def _derive(material: bytes, salt: bytes) -> bytes:
    return PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=DKLEN,
        salt=salt,
        iterations=ITERATIONS,
    ).derive(material)


# ---------------- 封裝 ----------------

def seal(
    plaintext: str,
    materials: list[bytes],
    slot_ids: list[str] | None = None,
) -> dict:
    """把明文封成一份密文 + 每組憑證各一個 wrapped CEK。

    `slot_ids` 是 §5.6 的槽位代號 —— **不透明且跨發布穩定**，用來認出是哪一組
    憑證解開的。不給就每次隨機產生（等於不做遙測）。它對應到哪一組憑證只記在
    本機的 publish.json，密文頁面上看不出來。
    """
    if not materials:
        raise ValueError(
            "沒有任何憑證 —— 這會產生一份誰都打不開的密文，一定是呼叫端出錯了"
        )
    if slot_ids is not None and len(slot_ids) != len(materials):
        raise ValueError("slot_ids 的數量要跟憑證數量一致，不然遙測會對錯人")

    cek = os.urandom(CEK_BYTES)
    iv_content = os.urandom(IV_BYTES)
    ct = AESGCM(cek).encrypt(iv_content, plaintext.encode("utf-8"), AAD_CONTENT)

    slots = slot_ids or [secrets.token_hex(2) for _ in materials]

    keys = []
    for material, slot in zip(materials, slots):
        salt = os.urandom(SALT_BYTES)
        iv = os.urandom(IV_BYTES)
        wrapped = AESGCM(_derive(material, salt)).encrypt(iv, cek, AAD_KEK)
        keys.append(
            {"t": slot, "salt": _b64(salt), "iv": _b64(iv), "wrapped": _b64(wrapped)}
        )

    # §5.3 第 5 點：每次發布重新洗牌，讓位置不洩漏哪一組是哪一組。
    # 洗的是陣列順序，`t` 綁在憑證上不動 —— 兩件事不衝突。
    secrets.SystemRandom().shuffle(keys)

    return {
        "v": VERSION,
        "pub_id": hashlib.sha256(ct).hexdigest()[:16],
        "kdf": {"alg": "PBKDF2-SHA256", "iter": ITERATIONS, "dklen": DKLEN},
        "content": {"iv": _b64(iv_content), "ct": _b64(ct)},
        "keys": keys,
    }


# ---------------- 解封（給發布前的自我驗收用） ----------------

def _unwrap(env: dict, material: bytes) -> tuple[bytes, str]:
    """逐一試每個槽位。回 (cek, 槽位代號)。

    瀏覽器那側做的是同一件事，這裡有一份 Python 版，是為了讓 §5.5 那句
    「每一組有效憑證都能解開，逐一測過」能夠自動跑，而不是每次發布用眼睛看。
    """
    for k in env["keys"]:
        try:
            cek = AESGCM(_derive(material, _unb64(k["salt"]))).decrypt(
                _unb64(k["iv"]), _unb64(k["wrapped"]), AAD_KEK
            )
        except Exception:
            continue
        return cek, k["t"]
    raise WrongCredential("沒有任何一組憑證吻合")


def open_envelope(env: dict, material: bytes) -> str:
    cek, _ = _unwrap(env, material)
    return AESGCM(cek).decrypt(
        _unb64(env["content"]["iv"]), _unb64(env["content"]["ct"]), AAD_CONTENT
    ).decode("utf-8")


def which_slot(env: dict, material: bytes) -> str:
    """這組憑證落在哪個槽位。發布後驗證 `t` 沒有錯位用（§5.5 最後一項）。"""
    return _unwrap(env, material)[1]
