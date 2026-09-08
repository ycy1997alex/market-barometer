"""信封加密（ToDo §5.3、§5.4、§5.5）。**這是本專案風險最高的一節。**

§5.5 的驗收清單直接翻成測試 —— 尤其是這一句：

  > 連續兩次發布的 `content.iv`、每個 `keys[i].salt`、`keys[i].iv` 全都不同
  > —— **寫成自動測試，不要靠肉眼**

為什麼非測不可：AES-GCM 在同一把 key 下重用 IV，機密性與完整性會**同時**
崩掉，不是理論弱化，是可以直接還原明文。手動發布一次不會踩到，**寫成每天跑
的腳本很容易踩到**，因為 salt/iv 是最容易被順手寫死的東西（§5.4 第 1 條）。

這裡用的是假憑證。真的那組在 `_stockdata\\secrets\\publish.json`，
**絕不進任何 repo**（§5.1、§12 第 1 條）—— 有一個測試守著這件事。
"""
from __future__ import annotations

import json

import pytest

from barometer.crypto import envelope

# 正式的迭代數 —— 在任何 patch 之前先抓下來，下面那條守門測試要用真的值
REAL_ITERATIONS = envelope.ITERATIONS


@pytest.fixture(autouse=True)
def _fast_kdf(monkeypatch):
    """把 PBKDF2 迭代數降到跑得動的程度。

    310,000 次 × 每次測試好幾組憑證，整包會從兩秒變成半分鐘 —— 而
    「每天收工前 pytest 全綠」（§3.3）只有在它跑得快的時候才會真的被執行。

    **降的只有測試裡的迭代數，正式路徑一個字沒動** —— 下面
    test_kdf_iterations_meet_the_2026_floor 對照的是 patch 之前抓下來的
    REAL_ITERATIONS，所以 §5.4 第 5 條那條下限仍然有人守。
    """
    monkeypatch.setattr(envelope, "ITERATIONS", 1_000)


# 測試用的假憑證。**不是** §5.1 那組真的
FAKE_ONE_LOCK = ["pw-alpha", "pw-beta", "pw-gamma"]
FAKE_TWO_LOCK = [("key-a", "pw-1"), ("key-a", "pw-2"),
                 ("key-b", "pw-1"), ("key-b", "pw-2")]

PLAINTEXT = "<h1>總經評分 68.8</h1><p>資料日期 2026-09-06</p>"


def _materials_one(passwords):
    return [envelope.material_one_lock(p) for p in passwords]


def _materials_two(pairs):
    return [envelope.material_two_lock(k, p) for k, p in pairs]


# ---------------- 基本往返 ----------------

def test_every_credential_opens_the_same_content():
    """§5.5：每一組有效憑證都能解開，**逐一測過**。"""
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    for pw in FAKE_ONE_LOCK:
        assert envelope.open_envelope(env, envelope.material_one_lock(pw)) == PLAINTEXT


def test_two_lock_needs_both_halves_right():
    env = envelope.seal(PLAINTEXT, _materials_two(FAKE_TWO_LOCK))
    for k, p in FAKE_TWO_LOCK:
        assert envelope.open_envelope(
            env, envelope.material_two_lock(k, p)
        ) == PLAINTEXT
    # 對的 key 配錯的 password
    with pytest.raises(envelope.WrongCredential):
        envelope.open_envelope(env, envelope.material_two_lock("key-a", "pw-9"))
    # 錯的 key 配對的 password
    with pytest.raises(envelope.WrongCredential):
        envelope.open_envelope(env, envelope.material_two_lock("key-z", "pw-1"))


def test_wrong_credential_yields_nothing_not_partial_plaintext():
    """AES-GCM 是認證加密 —— 密碼錯就是驗證失敗，不會吐出半段明文。"""
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    with pytest.raises(envelope.WrongCredential):
        envelope.open_envelope(env, envelope.material_one_lock("nope"))


def test_nul_separator_prevents_concatenation_collisions():
    """§5.3 第 4 點：`"ab"+"c"` 與 `"a"+"bc"` 不得撞在一起。"""
    assert envelope.material_two_lock("ab", "c") != envelope.material_two_lock("a", "bc")


# ---------------- §5.4 第 1 條：每次發布都要換 ----------------

def test_two_publishes_share_no_salt_or_iv():
    a = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    b = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))

    assert a["content"]["iv"] != b["content"]["iv"]
    assert a["content"]["ct"] != b["content"]["ct"]  # CEK 也換了

    salts_a = {k["salt"] for k in a["keys"]}
    salts_b = {k["salt"] for k in b["keys"]}
    ivs_a = {k["iv"] for k in a["keys"]}
    ivs_b = {k["iv"] for k in b["keys"]}
    assert not (salts_a & salts_b)
    assert not (ivs_a & ivs_b)


def test_no_salt_or_iv_repeats_within_one_publish():
    env = envelope.seal(PLAINTEXT, _materials_two(FAKE_TWO_LOCK))
    salts = [k["salt"] for k in env["keys"]]
    ivs = [k["iv"] for k in env["keys"]] + [env["content"]["iv"]]
    assert len(set(salts)) == len(salts)
    assert len(set(ivs)) == len(ivs)


def test_pub_id_changes_between_publishes():
    """pub_id 換掉，隔天瀏覽器裡的舊 CEK 才會自動失效（§5.3 時效行為）。"""
    a = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    b = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    assert a["pub_id"] != b["pub_id"]
    assert len(a["pub_id"]) == 16


# ---------------- §5.3 第 5 點：keys[] 洗牌，但 t 不動 ----------------

def test_slot_ids_are_stable_across_publishes():
    """`t` 跨發布穩定 —— 洗的是陣列順序，t 綁在憑證上不動（§5.6 第 2 點）。"""
    slots = ["a3f9", "b71c", "c2d8"]
    a = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK), slot_ids=slots)
    b = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK), slot_ids=slots)
    assert {k["t"] for k in a["keys"]} == set(slots)
    assert {k["t"] for k in b["keys"]} == set(slots)


def test_slot_id_still_maps_to_the_same_credential_after_shuffling():
    """洗牌不得讓 t 錯位 —— §5.5 最後一項驗收。"""
    slots = ["a3f9", "b71c", "c2d8"]
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK), slot_ids=slots)
    for pw, expected_slot in zip(FAKE_ONE_LOCK, slots):
        assert envelope.which_slot(
            env, envelope.material_one_lock(pw)
        ) == expected_slot


def test_key_order_is_shuffled_at_least_sometimes():
    """位置不該洩漏哪一組是哪一組。連發二十次總會洗出不同順序。"""
    slots = [f"{i:04x}" for i in range(6)]
    mats = _materials_one([f"pw{i}" for i in range(6)])
    orders = {
        tuple(k["t"] for k in envelope.seal(PLAINTEXT, mats, slot_ids=slots)["keys"])
        for _ in range(20)
    }
    assert len(orders) > 1


# ---------------- §5.5 其餘驗收 ----------------

def test_ciphertext_contains_no_credential_string():
    """密文 HTML 裡 grep 不到任何密碼字串。"""
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    blob = json.dumps(env)
    for pw in FAKE_ONE_LOCK:
        assert pw not in blob


def test_ciphertext_contains_no_plaintext_fragment():
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    blob = json.dumps(env)
    assert "總經評分" not in blob
    assert "68.8" not in blob


def test_kdf_iterations_meet_the_2026_floor():
    """310,000 是 2026 年的**下限**不是上限（§5.4 第 5 條）。

    對照的是 patch 之前抓下來的正式值 —— 測試自己把迭代數調低，不代表
    正式發布也可以。
    """
    assert REAL_ITERATIONS >= 310_000
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    assert env["kdf"]["alg"] == "PBKDF2-SHA256"
    assert env["kdf"]["iter"] == envelope.ITERATIONS


def test_envelope_shape_matches_the_spec():
    env = envelope.seal(PLAINTEXT, _materials_one(FAKE_ONE_LOCK))
    assert set(env) == {"v", "pub_id", "kdf", "content", "keys"}
    assert set(env["content"]) == {"iv", "ct"}
    assert all(set(k) == {"t", "salt", "iv", "wrapped"} for k in env["keys"])


def test_sealing_without_credentials_is_refused():
    """零組憑證 = 一份誰都打不開的密文。這一定是呼叫端出錯了。"""
    with pytest.raises(ValueError):
        envelope.seal(PLAINTEXT, [])
